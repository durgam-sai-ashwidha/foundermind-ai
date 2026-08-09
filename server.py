from __future__ import annotations

import os
import json
import uuid
import time
import sqlite3
import datetime
import urllib.request
import urllib.parse
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from dotenv import load_dotenv

import asyncio

# Hindsight Python SDK
from hindsight_client import Hindsight

# Cascadeflow Python SDK
from cascadeflow import CascadeAgent, ModelConfig, CascadeResult
from groq import Groq

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_FILENAME = "index.html"
DB_PATH = os.path.join(BASE_DIR, "foundermind.db")

app = Flask(__name__, static_folder=None)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "foundermind_super_secret_key_123")
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Required for http://localhost / 127.0.0.1
app.config['SESSION_PERMANENT'] = True
app.secret_key = app.config['SECRET_KEY']
CORS(app, supports_credentials=True)

try:
    from flask_bcrypt import Bcrypt
    bcrypt = Bcrypt(app)
    def hash_password(password: str) -> str:
        return bcrypt.generate_password_hash(password).decode("utf-8")
    def check_password(password_hash: str, password: str) -> bool:
        return bcrypt.check_password_hash(password_hash, password)
except ImportError:
    print("[Auth Warning]: flask_bcrypt not installed. Falling back to hashlib.sha256")
    import hashlib
    bcrypt = None
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()
    def check_password(password_hash: str, password: str) -> bool:
        return hashlib.sha256(password.encode("utf-8")).hexdigest() == password_hash

# Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY")
HINDSIGHT_PIPELINE_ID = os.getenv("HINDSIGHT_PIPELINE_ID", "foundermind")
HINDSIGHT_BASE_URL = os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io")

print(f"[Groq Key]:      {'[OK]' if GROQ_API_KEY else '[MISSING]'}")
print(f"[Hindsight Key]: {'[OK]' if HINDSIGHT_API_KEY else '[MISSING]'}")
print(f"[Pipeline ID]:   {'[OK]' if HINDSIGHT_PIPELINE_ID else '[MISSING]'}")

def run_async(coro_or_func, *args, **kwargs):
    """Safely execute async function or coroutine in synchronous Flask contexts."""
    async def _runner():
        if asyncio.iscoroutine(coro_or_func):
            return await coro_or_func
        elif asyncio.iscoroutinefunction(coro_or_func):
            return await coro_or_func(*args, **kwargs)
        elif callable(coro_or_func):
            res = coro_or_func(*args, **kwargs)
            if asyncio.iscoroutine(res):
                return await res
            return res
        return coro_or_func

    try:
        return asyncio.run(_runner())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_runner())
        finally:
            loop.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized", "authenticated": False}), 401
        return f(*args, **kwargs)
    return decorated_function

# DB
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, text TEXT NOT NULL, priority TEXT DEFAULT 'med', done INTEGER DEFAULT 0, created_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS meetings (id TEXT PRIMARY KEY, title TEXT NOT NULL, date TEXT DEFAULT '', time TEXT DEFAULT '', with_ TEXT DEFAULT '', created_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT DEFAULT 'Other', icon TEXT DEFAULT 'doc', created_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, text TEXT NOT NULL, tag TEXT DEFAULT 'decision', saved_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, event TEXT NOT NULL, model_used TEXT DEFAULT '', model_alias TEXT DEFAULT '', rationale TEXT DEFAULT '', cost_usd REAL DEFAULT 0.0, cost_saved_usd REAL DEFAULT 0.0, latency_ms REAL DEFAULT 0.0, is_fast_model INTEGER DEFAULT 0, cascaded INTEGER DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, role TEXT NOT NULL, message TEXT NOT NULL, timestamp TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS chat_sessions (id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))""")

        # Schema migrations
        c.execute("PRAGMA table_info(audit_logs)")
        existing_cols = {row["name"] for row in c.fetchall()}
        if "model_alias" not in existing_cols:
            c.execute("ALTER TABLE audit_logs ADD COLUMN model_alias TEXT DEFAULT ''")
        if "model_used" not in existing_cols:
            c.execute("ALTER TABLE audit_logs ADD COLUMN model_used TEXT DEFAULT ''")
        if "rationale" not in existing_cols:
            c.execute("ALTER TABLE audit_logs ADD COLUMN rationale TEXT DEFAULT ''")
        if "cost_saved_usd" not in existing_cols:
            c.execute("ALTER TABLE audit_logs ADD COLUMN cost_saved_usd REAL DEFAULT 0.0")
        # Migrate chat_messages to include session_id
        try:
            c.execute("ALTER TABLE chat_messages ADD COLUMN session_id TEXT DEFAULT NULL")
        except Exception:
            pass  # Column already exists
        # Migrate memories to include user_id
        try:
            c.execute("ALTER TABLE memories ADD COLUMN user_id INTEGER DEFAULT NULL")
        except Exception:
            pass  # Column already exists
        conn.commit()

init_db()

# SDK Clients
hindsight_client = None
if HINDSIGHT_API_KEY:
    try:
        hindsight_client = Hindsight(base_url=HINDSIGHT_BASE_URL, api_key=HINDSIGHT_API_KEY)
        print("[Hindsight SDK] [OK] Client initialized")
    except Exception as e:
        print(f"[Hindsight Init Warning]: {e}")

low_cost_model = ModelConfig(name="llama-3.1-8b-instant", provider="groq", api_key=GROQ_API_KEY, cost=0.08, speed_ms=500, quality_score=0.6, keywords=["hi","hello","hey","task","meeting","todo","done","list","schedule","thanks","bye","ok"])
high_capacity_model = ModelConfig(name="llama-3.3-70b-versatile", provider="groq", api_key=GROQ_API_KEY, cost=0.79, speed_ms=1500, quality_score=0.95, keywords=["fundraising","investor","pitch","strategy","decision","prep","revenue","mrr","burn","runway","founder","architecture","complex"])

cascade_agent = None
if GROQ_API_KEY:
    try:
        cascade_agent = CascadeAgent(models=[low_cost_model, high_capacity_model], enable_cascade=True)
        print("[Cascadeflow] [OK] CascadeAgent initialized")
    except Exception as e:
        print(f"[Cascadeflow Init Warning]: {e}")

# State
conversation_history = []
analytics_store = {
    "total_messages": 0, "total_tokens": 0, "memories_saved": 0, "sessions": 1,
    "budget_used": 0.0, "budget_limit": 100.0,
    "routing": {"fast_8b": 0, "heavy_70b": 0, "groq_llama_low": 0, "groq_llama_high": 0, "cascaded": 0, "hindsight_recall": 0, "hindsight_save": 0},
    "last_execution": {"model_used": None, "model_alias": None, "cost_usd": 0.0, "cost_saved_usd": 0.0, "latency_ms": 0.0, "is_fast_model": False, "cascaded": False}
}

def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def now_iso():
    return datetime.datetime.now().isoformat()

def get_json_body():
    return request.get_json(silent=True) or {}

def log_audit(event, model_used="", model_alias="", rationale="", cost_usd=0.0, cost_saved_usd=0.0, latency_ms=0.0, is_fast_model=False, cascaded=False):
    ts = datetime.datetime.now().strftime("%I:%M %p")
    try:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO audit_logs (timestamp,event,model_used,model_alias,rationale,cost_usd,cost_saved_usd,latency_ms,is_fast_model,cascaded) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ts, event, model_used, model_alias, rationale, cost_usd, cost_saved_usd, latency_ms, 1 if is_fast_model else 0, 1 if cascaded else 0))
            conn.commit()
    except Exception as e:
        print(f"[Audit Log DB Error]: {e}")

def save_memory_hindsight(content):
    if not HINDSIGHT_API_KEY or not HINDSIGHT_PIPELINE_ID:
        return False
    async def _async_retain():
        client = Hindsight(base_url=HINDSIGHT_BASE_URL, api_key=HINDSIGHT_API_KEY)
        try:
            return await client.aretain(bank_id=HINDSIGHT_PIPELINE_ID, content=content)
        finally:
            await client.aclose()
    try:
        run_async(_async_retain)
        log_audit("Memory retain via Hindsight SDK")
        analytics_store["routing"]["hindsight_save"] += 1
        return True
    except Exception as e:
        print(f"[Hindsight Save Error]: {e}")
        return False

def recall_memories_hindsight(query):
    if not HINDSIGHT_API_KEY or not HINDSIGHT_PIPELINE_ID:
        return ""
    async def _async_recall():
        client = Hindsight(base_url=HINDSIGHT_BASE_URL, api_key=HINDSIGHT_API_KEY)
        try:
            return await client.arecall(bank_id=HINDSIGHT_PIPELINE_ID, query=query)
        finally:
            await client.aclose()
    try:
        response = run_async(_async_recall)
        mems = []
        if hasattr(response, 'results') and response.results:
            for item in response.results:
                text = getattr(item, 'text', '') or (item.get('text') if isinstance(item, dict) else '')
                if text:
                    mems.append(text)
        if mems:
            log_audit(f"Memory recall -- {len(mems)} memories retrieved")
            analytics_store["routing"]["hindsight_recall"] += 1
            return "\n---\n".join(mems)
        return ""
    except Exception as e:
        print(f"[Hindsight Recall Error]: {e}")
        return ""

def classify_intent(message):
    low_msg = message.lower().strip()
    greetings = {"hi","hello","hey","yo","ok","okay","thanks","bye","good morning","good evening"}
    if low_msg in greetings or len(low_msg) < 15:
        return "simple"
    complex_kw = ["investor","funding","pitch","vc","seed","series","strategy","decision","revenue","mrr","arr","churn","runway","burn","architecture","prep","founder","fundraising","financial","valuation","term sheet","cap table"]
    if any(k in low_msg for k in complex_kw):
        return "complex"
    return "simple"

def ask_cascadeflow(user_message, long_term_memories="", current_user="Founder"):
    global conversation_history
    if cascade_agent is None and groq_client is None:
        log_audit("Cascadeflow call skipped -- no API key")
        return {"reply": "Groq/Cascadeflow API Error: GROQ_API_KEY missing. Add it to .env and restart.", "tokens": 0, "cost_usd": 0.0, "cost_saved_usd": 0.0, "latency_ms": 0.0, "model_used": "none", "model_alias": "none", "is_fast_model": False, "cascaded": False, "error": True}

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT priority, text FROM tasks WHERE done = 0 ORDER BY created_at DESC LIMIT 10")
        open_tasks = c.fetchall()
        c.execute("SELECT title, date, time, with_ FROM meetings ORDER BY created_at DESC LIMIT 3")
        upcoming_meetings = c.fetchall()

    complexity_hint = classify_intent(user_message)

    if complexity_hint == "simple":
        task_ctx = ""
        meeting_ctx = ""
        mem_text = "No past session memories needed for simple queries."
    else:
        task_ctx = ("\n\nOPEN TASKS:\n" + "\n".join(f"- [{t['priority'].upper()}] {t['text']}" for t in open_tasks)) if open_tasks else ""
        meeting_ctx = ("\n\nUPCOMING MEETINGS:\n" + "\n".join(f"- {m['title']} on {m['date'] or 'TBD'} at {m['time'] or 'TBD'} with {m['with_'] or '--'}" for m in upcoming_meetings)) if upcoming_meetings else ""
        mem_text = long_term_memories[:3000] if long_term_memories else "No past session memories yet."

    system_prompt = f"""You are FounderMind, an intelligent, helpful, and direct AI assistant assisting {current_user}, the Founder & CEO. Deliver clear, concise, accurate, and direct responses matching standard ChatGPT/Gemini behavior. Never hallucinate random corporate scenarios, investor briefing templates, or fictional meeting contexts (e.g. Sequoia Capital, ACV, 2-minute timers) unless explicitly provided in the user prompt or relevant context.

You have TWO sources of memory:
1. LONG-TERM MEMORIES (from past sessions):
{mem_text}
2. CURRENT SESSION HISTORY (included in this conversation).
{task_ctx}
{meeting_ctx}

YOUR RULES:
- The user's name is {current_user}. If asked "What is my name?" or "Who am I?", explicitly tell them their name is {current_user}.
- DO NOT forcefully inject past corporate templates or default memory buffers into simple everyday queries, basic greetings, or quick math questions (e.g. "what is 2+2").
- Match response length to prompt complexity: simple questions get direct, concise answers without extra conversational fluff.
- If context is provided, reference past context naturally in every response.
- When asked about tasks or meetings, reference the live data above."""

    history_str = ""
    if conversation_history:
        history_str = "\nRecent Conversation:\n" + "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in conversation_history[-6:])

    full_query = f"{system_prompt}\n{history_str}\n\nUser: {user_message}"

    start_time = time.time()
    try:
        result = None
        if cascade_agent:
            result = run_async(cascade_agent.run, query=full_query, max_tokens=600, temperature=0.1, complexity_hint=complexity_hint)
        
        latency_ms = round((time.time() - start_time) * 1000, 2)
        raw_reply = getattr(result, "content", "") if result else ""
        reply = raw_reply if isinstance(raw_reply, str) else ""

        # Fallback to direct Groq client if cascade agent returned empty response or failed
        if not reply.strip() and groq_client:
            try:
                groq_resp = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                    max_tokens=600,
                    temperature=0.1,
                )
                reply = groq_resp.choices[0].message.content or ""
            except Exception as fe:
                print(f"[Groq Direct Fallback Error]: {fe}")

        model_used = getattr(result, "model_used", "groq/llama-3.3-70b-versatile") if result else "groq/llama-3.3-70b-versatile"
        cost_usd = getattr(result, "total_cost", None) or getattr(result, "draft_cost", 0.0001) or 0.0001
        cascaded = bool(getattr(result, "cascaded", False)) if result else False

        tokens = len(reply.split()) * 2
        conversation_history.append({"role": "user", "content": user_message})
        conversation_history.append({"role": "assistant", "content": reply})
        if len(conversation_history) > 20:
            conversation_history[:] = conversation_history[-20:]

        is_fast_model = "8b" in model_used.lower() or "instant" in model_used.lower()
        if is_fast_model:
            model_alias = "8B Fast Model"
            heavy_cost = round(tokens * 0.0007 / 1000, 6)
            cost_saved_usd = max(round(heavy_cost - cost_usd, 6), 0.0016)
            analytics_store["routing"]["fast_8b"] += 1
            analytics_store["routing"]["groq_llama_low"] += 1
        else:
            model_alias = "70B Heavy Model"
            cost_saved_usd = 0.0
            analytics_store["routing"]["heavy_70b"] += 1
            analytics_store["routing"]["groq_llama_high"] += 1

        if cascaded:
            analytics_store["routing"]["cascaded"] += 1

        analytics_store["total_messages"] += 1
        analytics_store["total_tokens"] += tokens
        analytics_store["budget_used"] = round(analytics_store["budget_used"] + cost_usd, 6)
        analytics_store["last_execution"] = {"model_used": model_used, "model_alias": model_alias, "cost_usd": cost_usd, "cost_saved_usd": cost_saved_usd, "latency_ms": latency_ms, "is_fast_model": is_fast_model, "cascaded": cascaded}

        rationale = f"Routed to {model_alias}: {'Operational query -- fast model' if is_fast_model else 'Complex analysis -- heavy model'}"
        log_audit(f"Cascadeflow -> {model_alias} ({tokens} tokens, {latency_ms}ms, ${cost_usd:.6f})", model_used=model_used, model_alias=model_alias, rationale=rationale, cost_usd=cost_usd, cost_saved_usd=cost_saved_usd, latency_ms=latency_ms, is_fast_model=is_fast_model, cascaded=cascaded)

        return {"reply": reply, "tokens": tokens, "cost_usd": cost_usd, "cost_saved_usd": cost_saved_usd, "latency_ms": latency_ms, "model_used": model_used, "model_alias": model_alias, "is_fast_model": is_fast_model, "cascaded": cascaded, "error": False}

    except Exception as e:
        err_text = str(e)
        latency_ms = round((time.time() - start_time) * 1000, 2)
        print(f"[Cascadeflow Error]: {err_text}")
        # Try direct Groq fallback on error
        if groq_client:
            try:
                groq_resp = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                    max_tokens=600,
                    temperature=0.1,
                )
                reply = groq_resp.choices[0].message.content
                tokens = len(reply.split()) * 2
                conversation_history.append({"role": "user", "content": user_message})
                conversation_history.append({"role": "assistant", "content": reply})
                log_audit(f"Groq Direct Fallback (70b) ({tokens} tokens)", model_used="llama-3.3-70b-versatile", model_alias="70B Heavy Model", rationale="Direct Groq API call", cost_usd=0.0001, latency_ms=latency_ms, is_fast_model=False, cascaded=False)
                return {"reply": reply, "tokens": tokens, "cost_usd": 0.0001, "cost_saved_usd": 0.0, "latency_ms": latency_ms, "model_used": "groq/llama-3.3-70b-versatile", "model_alias": "70B Heavy Model", "is_fast_model": False, "cascaded": False, "error": False}
            except Exception as ge:
                err_text = f"{err_text} | Fallback Error: {ge}"
        log_audit(f"Cascadeflow call failed -- {err_text[:80]}")
        return {"reply": f"Cascadeflow Error: {err_text}", "tokens": 0, "cost_usd": 0.0, "cost_saved_usd": 0.0, "latency_ms": latency_ms, "model_used": "error", "model_alias": "error", "is_fast_model": False, "cascaded": False, "error": True}





# ══════════════════════════════════════════════════════════
# AUTHENTICATION ENDPOINTS
# ══════════════════════════════════════════════════════════
@app.route("/api/register", methods=["POST"])
def register():
    data = get_json_body()
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not email or not password:
        return jsonify({"error": "Username, email, and password are required"}), 400

    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters"}), 400

    password_hash = hash_password(password)

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, password_hash)
            )
            conn.commit()
            user_id = cursor.lastrowid

        session["user_id"] = user_id
        session["username"] = username
        session.modified = True
        log_audit(f"User registered -- {username}")

        return jsonify({
            "status": "registered",
            "authenticated": True,
            "user": {"id": user_id, "username": username, "email": email}
        }), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username or email already exists"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/login", methods=["POST"])
def login():
    data = get_json_body()
    identifier = (data.get("username") or data.get("email") or "").strip()
    password = (data.get("password") or "").strip()

    if not identifier or not password:
        return jsonify({"error": "Username/Email and password are required"}), 400

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, email, password_hash FROM users WHERE username = ? OR email = ?",
            (identifier, identifier)
        )
        user = cursor.fetchone()

    if not user or not check_password(user["password_hash"], password):
        return jsonify({"error": "Invalid username/email or password"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session.modified = True
    log_audit(f"User logged in -- {user['username']}")

    return jsonify({
        "status": "logged_in",
        "authenticated": True,
        "user": {"id": user["id"], "username": user["username"], "email": user["email"]}
    })


@app.route("/api/logout", methods=["POST"])
def logout():
    username = session.get("username", "user")
    session.clear()
    session.modified = True
    log_audit(f"User logged out -- {username}")
    return jsonify({"status": "logged_out", "authenticated": False})


@app.route("/api/me", methods=["GET"])
def get_current_user():
    if "user_id" in session:
        return jsonify({
            "authenticated": True,
            "user_id": session["user_id"],
            "username": session.get("username")
        })
    return jsonify({"authenticated": False})


@app.route("/")
def index():
    if os.path.exists(os.path.join(BASE_DIR, FRONTEND_FILENAME)):
        return send_from_directory(BASE_DIR, FRONTEND_FILENAME)
    elif os.path.exists(os.path.join(BASE_DIR, "index.html")):
        return send_from_directory(BASE_DIR, "index.html")
    return "FounderMind backend running."


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    data = get_json_body()
    user_message = (data.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "No message"}), 400

    current_user = session.get("username") or (data.get("username") if isinstance(data, dict) else None) or "Founder"
    user_id = session.get("user_id")

    # --- Auto-create or reuse chat session ---
    req_session_id = data.get("session_id") if isinstance(data, dict) else None
    if req_session_id:
        session["chat_session_id"] = req_session_id
        session.modified = True

    chat_session_id = session.get("chat_session_id")
    if not chat_session_id:
        # Fallback to user's most recent session if available
        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT id FROM chat_sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (user_id,))
                row = c.fetchone()
                if row:
                    chat_session_id = row["id"]
                    session["chat_session_id"] = chat_session_id
                    session.modified = True
        except Exception as e:
            print(f"[DB Session Fallback Lookup Error]: {e}")

    if not chat_session_id:
        chat_session_id = str(uuid.uuid4())
        session_title = user_message[:40] + ("..." if len(user_message) > 40 else "")
        session_created_at = now_str()
        try:
            with get_db_connection() as conn:
                conn.execute(
                    "INSERT INTO chat_sessions (id, user_id, title, created_at) VALUES (?, ?, ?, ?)",
                    (chat_session_id, user_id, session_title, session_created_at)
                )
                conn.commit()
        except Exception as e:
            print(f"[DB Session Create Error]: {e}")
        session["chat_session_id"] = chat_session_id
        session.modified = True

    print(f"\n[{current_user}]: {user_message}")
    long_term = recall_memories_hindsight(user_message)
    result = ask_cascadeflow(user_message, long_term, current_user=current_user)
    reply, had_error = result["reply"], result["error"]
    print(f"[FounderMind]: {reply[:120]}...")

    skip_words = {"hi","hello","hey","ok","okay","thanks","bye","yo"}
    should_save = (not had_error) and (user_message.lower().strip() not in skip_words)

    if should_save:
        try:
            save_memory_hindsight(f"[{now_str()}]\nFounder: {user_message}\nFounderMind: {reply}")
        except Exception as e:
            print(f"[Hindsight Save Error - Non-fatal]: {e}")
        analytics_store["memories_saved"] += 1

        tag = "decision"
        t = user_message.lower()
        if any(k in t for k in ["investor","funding","pitch","vc","seed","series"]):
            tag = "investor"
        elif any(k in t for k in ["meeting","call","sync"]):
            tag = "meeting"
        elif any(k in t for k in ["task","deadline","todo","finish","complete"]):
            tag = "task"
        elif any(k in t for k in ["revenue","mrr","arr","churn","runway","burn"]):
            tag = "revenue"

        mem_id = str(uuid.uuid4())
        saved_at = now_str()
        try:
            with get_db_connection() as conn:
                conn.execute("INSERT INTO memories (id, text, tag, saved_at, user_id) VALUES (?, ?, ?, ?, ?)", (mem_id, user_message, tag, saved_at, user_id))
                conn.commit()
        except Exception as e:
            print(f"[DB Memory Insert Error]: {e}")

    # Always persist both user message and AI reply to chat_messages (with session_id)
    ts = now_str()
    try:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO chat_messages (user_id, role, message, timestamp, session_id) VALUES (?, ?, ?, ?, ?)", (user_id, "user", user_message, ts, chat_session_id))
            conn.execute("INSERT INTO chat_messages (user_id, role, message, timestamp, session_id) VALUES (?, ?, ?, ?, ?)", (user_id, "assistant", reply, ts, chat_session_id))
            conn.commit()
    except Exception as e:
        print(f"[DB Chat History Insert Error]: {e}")

    memory_recalled = bool(long_term)
    recalled_count = len(long_term.split("\n---\n")) if long_term else 0

    telemetry = {
        "model": result.get("model_used", ""),
        "model_alias": result.get("model_alias", ""),
        "is_fast_model": result.get("is_fast_model", False),
        "cost_usd": result.get("cost_usd", 0.0),
        "cost_saved_usd": result.get("cost_saved_usd", 0.0),
        "latency_ms": result.get("latency_ms", 0.0),
        "rationale": f"Routed to {result.get('model_alias','')}: {'Fast model -- operational' if result.get('is_fast_model') else 'Heavy model -- complex analysis'}",
        "memory_recalled": memory_recalled,
        "recalled_count": recalled_count,
    }

    return jsonify({"response": reply, "memory_saved": should_save, "memory_recalled": memory_recalled, "recalled_count": recalled_count, "tokens": result["tokens"], "cost_usd": result["cost_usd"], "cost_saved_usd": result.get("cost_saved_usd", 0.0), "latency_ms": result["latency_ms"], "model_used": result["model_used"], "model_alias": result.get("model_alias",""), "is_fast_model": result.get("is_fast_model", False), "cascaded": result["cascaded"], "telemetry": telemetry, "session_id": chat_session_id})


@app.route("/chat/sessions", methods=["GET"])
@login_required
def get_chat_sessions():
    user_id = session["user_id"]
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT id, title, created_at FROM chat_sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT 30",
                (user_id,)
            )
            rows = [{"id": r["id"], "title": r["title"], "created_at": r["created_at"]} for r in c.fetchall()]
        return jsonify(rows)
    except Exception as e:
        print(f"[Chat Sessions Fetch Error]: {e}")
        return jsonify([])


@app.route("/chat/new-session", methods=["POST"])
@login_required
def new_chat_session():
    session.pop("chat_session_id", None)
    session.modified = True
    return jsonify({"status": "ok", "message": "New session started"})


@app.route("/chat/sessions/<session_id>/messages", methods=["GET"])
@login_required
def get_session_messages(session_id):
    user_id = session["user_id"]
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT role, message, timestamp FROM chat_messages WHERE session_id = ? AND user_id = ? ORDER BY id ASC",
                (session_id, user_id)
            )
            rows = [{"role": r["role"], "message": r["message"], "timestamp": r["timestamp"]} for r in c.fetchall()]
        session["chat_session_id"] = session_id
        session.modified = True
        return jsonify({"status": "ok", "session_id": session_id, "messages": rows})
    except Exception as e:
        print(f"[Session Messages Fetch Error]: {e}")
        return jsonify({"status": "error", "messages": []}), 200


@app.route("/chat/history", methods=["GET"])
@login_required
def get_chat_history():
    user_id = session["user_id"]
    current_session_id = request.args.get("session_id") or session.get("chat_session_id")
    if not current_session_id:
        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT id FROM chat_sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (user_id,))
                row = c.fetchone()
                if row:
                    current_session_id = row["id"]
                    session["chat_session_id"] = current_session_id
                    session.modified = True
        except Exception:
            pass

    limit = min(int(request.args.get("limit", 50)), 200)
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            if current_session_id:
                c.execute(
                    "SELECT role, message, timestamp FROM chat_messages WHERE user_id = ? AND session_id = ? ORDER BY id ASC LIMIT ?",
                    (user_id, current_session_id, limit)
                )
            else:
                c.execute(
                    "SELECT role, message, timestamp FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                    (user_id, limit)
                )
                rows = [{"role": r["role"], "message": r["message"], "timestamp": r["timestamp"]} for r in c.fetchall()]
                rows.reverse()
                return jsonify(rows)
            rows = [{"role": r["role"], "message": r["message"], "timestamp": r["timestamp"]} for r in c.fetchall()]
        return jsonify(rows)
    except Exception as e:
        print(f"[Chat History Fetch Error]: {e}")
        return jsonify([])


@app.route("/reset", methods=["POST"])
@app.route("/api/reset", methods=["POST"])
def reset_session():
    global conversation_history
    conversation_history = []
    log_audit("Session reset -- conversation history cleared")
    return jsonify({"status": "Session cleared. Long-term memories preserved."})


@app.route("/api/decisions", methods=["GET"])
def get_decisions():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, text, tag, saved_at FROM memories WHERE tag = 'decision' ORDER BY saved_at DESC")
        rows = [dict(r) for r in c.fetchall()]
    return jsonify(rows)


@app.route("/api/decisions", methods=["POST"])
def add_decision():
    data = get_json_body()
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Decision text required"}), 400
    mem_id = str(uuid.uuid4())
    saved_at = now_str()
    with get_db_connection() as conn:
        conn.execute("INSERT INTO memories (id, text, tag, saved_at) VALUES (?, ?, 'decision', ?)", (mem_id, text, saved_at))
        conn.commit()
    log_audit(f"Decision logged -- {text[:40]}")
    return jsonify({"id": mem_id, "text": text, "tag": "decision", "saved_at": saved_at}), 201


@app.route("/api/insights", methods=["GET"])
def get_insights():
    with get_db_connection() as conn:
        c = conn.cursor()
        t_count = c.execute("SELECT COUNT(*) FROM tasks WHERE done = 0").fetchone()[0]
        m_count = c.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
        d_count = c.execute("SELECT COUNT(*) FROM memories WHERE tag = 'decision'").fetchone()[0]
    return jsonify([
        {"id": "ins-1", "title": "Priority Velocity", "detail": f"{t_count} open tasks pending review."},
        {"id": "ins-2", "title": "Strategic Alignment", "detail": f"{d_count} key decisions recorded in memory bank."},
        {"id": "ins-3", "title": "Calendar Load", "detail": f"{m_count} upcoming meetings scheduled."}
    ])


@app.route("/tasks", methods=["GET"])
@login_required
def get_tasks():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, text, priority, done, created_at FROM tasks ORDER BY created_at DESC")
        tasks = [{"id": r["id"], "text": r["text"], "priority": r["priority"], "done": bool(r["done"]), "created_at": r["created_at"]} for r in c.fetchall()]
    return jsonify(tasks)


@app.route("/tasks", methods=["POST"])
@login_required
def add_task():
    data = get_json_body()
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Task text required"}), 400
    task_id = str(uuid.uuid4())
    priority = data.get("priority", "med")
    created_at = now_iso()
    with get_db_connection() as conn:
        conn.execute("INSERT INTO tasks (id, text, priority, done, created_at) VALUES (?, ?, ?, 0, ?)", (task_id, text, priority, created_at))
        conn.commit()
    log_audit(f"Task added -- [{priority.upper()}] {text[:40]}")
    return jsonify({"id": task_id, "text": text, "priority": priority, "done": False, "created_at": created_at}), 201


@app.route("/tasks/<task_id>", methods=["PATCH"])
@login_required
def update_task(task_id):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, text, priority, done, created_at FROM tasks WHERE id = ?", (task_id,))
        row = c.fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        data = get_json_body()
        done = int(data["done"]) if "done" in data else row["done"]
        priority = data.get("priority", row["priority"])
        text = data.get("text", row["text"])
        conn.execute("UPDATE tasks SET done = ?, priority = ?, text = ? WHERE id = ?", (done, priority, text, task_id))
        conn.commit()
    log_audit(f"Task {'completed' if done else 'reopened'} -- {text[:40]}")
    return jsonify({"id": task_id, "text": text, "priority": priority, "done": bool(done), "created_at": row["created_at"]})


@app.route("/tasks/<task_id>", methods=["DELETE"])
@login_required
def delete_task(task_id):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if c.rowcount == 0:
            return jsonify({"error": "Not found"}), 404
        conn.commit()
    log_audit(f"Task deleted -- id {task_id[:8]}")
    return jsonify({"status": "deleted"})


@app.route("/meetings", methods=["GET"])
@login_required
def get_meetings():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, title, date, time, with_, created_at FROM meetings ORDER BY created_at DESC")
        meetings = [dict(r) for r in c.fetchall()]
    return jsonify(meetings)


@app.route("/meetings", methods=["POST"])
@login_required
def add_meeting():
    data = get_json_body()
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Meeting title required"}), 400
    meeting_id = str(uuid.uuid4())
    date = data.get("date", "")
    time_val = data.get("time", "")
    with_ = data.get("with_", "")
    created_at = now_iso()
    with get_db_connection() as conn:
        conn.execute("INSERT INTO meetings (id, title, date, time, with_, created_at) VALUES (?, ?, ?, ?, ?, ?)", (meeting_id, title, date, time_val, with_, created_at))
        conn.commit()
    log_audit(f"Meeting scheduled -- {title[:40]} on {date or 'TBD'}")
    return jsonify({"id": meeting_id, "title": title, "date": date, "time": time_val, "with_": with_, "created_at": created_at}), 201


@app.route("/meetings/<meeting_id>/prep", methods=["GET"])
@login_required
def ai_prep_meeting(meeting_id):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, title, date, time, with_, created_at FROM meetings WHERE id = ?", (meeting_id,))
        row = c.fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        meeting = dict(row)
    prompt = f'Prepare me for this meeting: "{meeting["title"]}"' + (f' with {meeting["with_"]}' if meeting.get("with_") else "") + f' on {meeting.get("date","TBD")} at {meeting.get("time","TBD")}. Key objectives, 5 smart questions, risks, outcomes.'
    long_term = recall_memories_hindsight(prompt)
    result = ask_cascadeflow(prompt, long_term)
    if not result["error"]:
        log_audit(f"AI Prep -- {meeting['title'][:40]}", model_used=result["model_used"], model_alias=result.get("model_alias",""), cost_usd=result["cost_usd"], latency_ms=result["latency_ms"], cascaded=result["cascaded"])
    return jsonify({"meeting": meeting, "prep": result["reply"]})


@app.route("/meetings/<meeting_id>", methods=["DELETE"])
@login_required
def delete_meeting(meeting_id):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
        if c.rowcount == 0:
            return jsonify({"error": "Not found"}), 404
        conn.commit()
    log_audit(f"Meeting deleted -- id {meeting_id[:8]}")
    return jsonify({"status": "deleted"})


@app.route("/documents", methods=["GET"])
@login_required
def get_documents():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, name, type, icon, created_at FROM documents ORDER BY created_at DESC")
        docs = [dict(r) for r in c.fetchall()]
    return jsonify(docs)


@app.route("/documents", methods=["POST"])
@login_required
def add_document():
    data = get_json_body()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Document name required"}), 400
    doc_type = data.get("type", "Other")
    icon = doc_type.split(" ")[0] if " " in doc_type else "doc"
    doc_id = str(uuid.uuid4())
    created_at = now_iso()
    with get_db_connection() as conn:
        conn.execute("INSERT INTO documents (id, name, type, icon, created_at) VALUES (?, ?, ?, ?, ?)", (doc_id, name, doc_type, icon, created_at))
        conn.commit()
    log_audit(f"Document added -- {name[:40]}")
    return jsonify({"id": doc_id, "name": name, "type": doc_type, "icon": icon, "created_at": created_at}), 201


@app.route("/documents/<doc_id>", methods=["DELETE"])
@login_required
def delete_document(doc_id):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        if c.rowcount == 0:
            return jsonify({"error": "Not found"}), 404
        conn.commit()
    log_audit(f"Document deleted -- id {doc_id[:8]}")
    return jsonify({"status": "deleted"})


@app.route("/memories", methods=["GET"])
@login_required
def get_memories():
    user_id = session["user_id"]
    query = request.args.get("q", "").lower().strip()
    with get_db_connection() as conn:
        c = conn.cursor()
        if query:
            c.execute("SELECT id, text, tag, saved_at FROM memories WHERE user_id = ? AND LOWER(text) LIKE ? ORDER BY saved_at DESC", (user_id, f"%{query}%"))
        else:
            c.execute("SELECT id, text, tag, saved_at FROM memories WHERE user_id = ? ORDER BY saved_at DESC", (user_id,))
        memories = [dict(r) for r in c.fetchall()]
    return jsonify(memories)


@app.route("/memories/search", methods=["GET"])
@login_required
def search_memories_route():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Query required"}), 400
    result = recall_memories_hindsight(query)
    return jsonify({"query": query, "results": result})


@app.route("/memories/hindsight", methods=["GET"])
@login_required
def sync_hindsight_memories_route():
    if not hindsight_client or not HINDSIGHT_PIPELINE_ID:
        return jsonify({"error": "Hindsight not configured", "memories": []}), 503
    try:
        response = hindsight_client.recall(bank_id=HINDSIGHT_PIPELINE_ID, query="", budget="high")
        synced = []
        if hasattr(response, "results") and response.results:
            for item in response.results:
                text = getattr(item, "text", "")
                tags = getattr(item, "tags", None) or []
                tag = tags[0] if tags else "decision"
                mem_id = getattr(item, "id", None) or str(uuid.uuid4())
                saved_at = now_str()
                if text:
                    synced.append({"id": mem_id, "text": text, "tag": tag, "saved_at": saved_at})
                    try:
                        with get_db_connection() as conn:
                            conn.execute("INSERT OR IGNORE INTO memories (id, text, tag, saved_at) VALUES (?, ?, ?, ?)", (mem_id, text, tag, saved_at))
                            conn.commit()
                    except Exception:
                        pass
        log_audit(f"Hindsight sync -- {len(synced)} memories pulled")
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id, text, tag, saved_at FROM memories ORDER BY saved_at DESC")
            all_mems = [dict(r) for r in c.fetchall()]
        return jsonify({"status": "synced", "count": len(all_mems), "memories": all_mems})
    except Exception as e:
        return jsonify({"error": str(e), "memories": []}), 500


@app.route("/memories", methods=["POST"])
@login_required
def save_memory_route():
    data = get_json_body()
    text = (data.get("text") or "").strip()
    tag = data.get("tag", "decision")
    user_id = session["user_id"]
    if not text:
        return jsonify({"error": "Text required"}), 400
    mem_id = str(uuid.uuid4())
    saved_at = now_str()
    with get_db_connection() as conn:
        conn.execute("INSERT INTO memories (id, text, tag, saved_at, user_id) VALUES (?, ?, ?, ?, ?)", (mem_id, text, tag, saved_at, user_id))
        conn.commit()
    save_memory_hindsight(f"[{saved_at}]\n{text}")
    analytics_store["memories_saved"] += 1
    return jsonify({"id": mem_id, "text": text, "tag": tag, "saved_at": saved_at}), 201


@app.route("/memories/<mem_id>", methods=["DELETE"])
@login_required
def delete_memory(mem_id):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM memories WHERE id = ?", (mem_id,))
        if c.rowcount == 0:
            return jsonify({"error": "Not found"}), 404
        conn.commit()
    log_audit(f"Memory deleted -- id {mem_id[:8]}")
    return jsonify({"status": "deleted"})


@app.route("/analytics", methods=["GET"])
@login_required
def get_analytics():
    fast_count = analytics_store["routing"]["fast_8b"]
    heavy_count = analytics_store["routing"]["heavy_70b"]
    total_model_calls = max(fast_count + heavy_count, 1)
    hindsight_calls = analytics_store["routing"]["hindsight_recall"] + analytics_store["routing"]["hindsight_save"]

    fast_pct = round(fast_count / total_model_calls * 100, 1)
    heavy_pct = round(heavy_count / total_model_calls * 100, 1)
    hindsight_pct = round(hindsight_calls / max(total_model_calls + hindsight_calls, 1) * 100, 1)

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT timestamp, event, model_used, model_alias, rationale, cost_usd, cost_saved_usd, latency_ms, is_fast_model, cascaded FROM audit_logs ORDER BY id DESC LIMIT 50")
        audit_rows = [dict(r) for r in c.fetchall()]

    return jsonify({
        "total_messages": analytics_store["total_messages"],
        "total_tokens": analytics_store["total_tokens"],
        "memories_saved": analytics_store["memories_saved"],
        "sessions": analytics_store["sessions"],
        "budget_used": round(analytics_store["budget_used"], 6),
        "budget_limit": analytics_store["budget_limit"],
        "budget_pct": round(analytics_store["budget_used"] / analytics_store["budget_limit"] * 100, 2),
        "routing": {
            "fast_8b_count": fast_count, "heavy_70b_count": heavy_count,
            "fast_8b_pct": fast_pct, "heavy_70b_pct": heavy_pct,
            "low_cost_model_pct": fast_pct, "high_capacity_model_pct": heavy_pct,
            "cascaded_count": analytics_store["routing"]["cascaded"],
            "hindsight_pct": hindsight_pct,
        },
        "last_execution": analytics_store["last_execution"],
        "audit_trail": audit_rows,
    })


@app.route("/settings", methods=["GET"])
@app.route("/api/model", methods=["GET"])
def get_settings():
    return jsonify({
        "model": "groq/llama-3.3-70b-versatile",
        "models": {"low_cost": "groq/llama-3.1-8b-instant", "high_capacity": "groq/llama-3.3-70b-versatile"},
        "max_tokens": 600, "temperature": 0.1,
        "stack": {
            "groq": {"status": "CONNECTED" if GROQ_API_KEY else "DISCONNECTED"},
            "hindsight_sdk": {"status": "CONNECTED" if HINDSIGHT_API_KEY else "DISCONNECTED"},
            "cascadeflow": {"status": "CONNECTED" if GROQ_API_KEY else "DISCONNECTED"},
            "database": {"status": "SQLITE_CONNECTED", "path": DB_PATH}
        },
    })


@app.route("/health", methods=["GET"])
def health():
    with get_db_connection() as conn:
        c = conn.cursor()
        tasks_count = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        meetings_count = c.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
        docs_count = c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        mems_count = c.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    return jsonify({"status": "ok", "models": {"low_cost": "groq/llama-3.1-8b-instant", "high_capacity": "groq/llama-3.3-70b-versatile"}, "groq": "connected" if GROQ_API_KEY else "missing-key", "hindsight_sdk": "connected" if HINDSIGHT_API_KEY else "missing-key", "cascadeflow": "connected" if GROQ_API_KEY else "missing-key", "database": "sqlite3", "session_messages": len(conversation_history), "tasks": tasks_count, "meetings": meetings_count, "documents": docs_count, "memories": mems_count})


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  FounderMind Server  --  Cascadeflow & Hindsight Edition")
    print("=" * 60)
    print("  GET   /                      - Serves the frontend")
    print("  POST  /chat                  - AI chat (cascadeflow + Hindsight SDK)")
    print("  POST  /reset                 - Clear session history")
    print("  GET   /tasks  POST /tasks    - List / add tasks")
    print("  PATCH /tasks/<id>  DEL       - Update / delete task")
    print("  GET   /meetings  POST        - List / add meetings")
    print("  GET   /meetings/<id>/prep    - AI prep for meeting")
    print("  DEL   /meetings/<id>         - Delete meeting")
    print("  GET   /documents  POST       - List / add documents")
    print("  DEL   /documents/<id>        - Delete document")
    print("  GET   /memories  POST        - List / save memories")
    print("  GET   /memories/hindsight    - Sync from Hindsight Cloud")
    print("  GET   /memories/search       - Hindsight semantic search")
    print("  DEL   /memories/<id>         - Delete memory")
    print("  GET   /analytics             - Routing & cost metadata")
    print("  GET   /settings              - Stack status + config")
    print("  GET   /health                - Health check")
    print("=" * 60 + "\n")

    log_audit("FounderMind server started with Cascadeflow & SQLite")
    analytics_store["sessions"] += 1

    app.run(host="0.0.0.0", debug=True, port=5000)

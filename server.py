from __future__ import annotations

import os
import json
import uuid
import time
import sqlite3
import datetime
import urllib.request
import urllib.parse
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

# Hindsight Python SDK
from hindsight_client import Hindsight

# Cascadeflow Python SDK
from cascadeflow import CascadeAgent, ModelConfig, CascadeResult

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_FILENAME = "FounderMind_Enhanced_fixed.html"
DB_PATH = os.path.join(BASE_DIR, "foundermind.db")

app = Flask(__name__, static_folder=None)
CORS(app)

# Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY")
HINDSIGHT_PIPELINE_ID = os.getenv("HINDSIGHT_PIPELINE_ID", "foundermind")
HINDSIGHT_BASE_URL = os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io")

print(f"[Groq Key]:      {'[OK]' if GROQ_API_KEY else '[MISSING]'}")
print(f"[Hindsight Key]: {'[OK]' if HINDSIGHT_API_KEY else '[MISSING]'}")
print(f"[Pipeline ID]:   {'[OK]' if HINDSIGHT_PIPELINE_ID else '[MISSING]'}")

# DB
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, text TEXT NOT NULL, priority TEXT DEFAULT 'med', done INTEGER DEFAULT 0, created_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS meetings (id TEXT PRIMARY KEY, title TEXT NOT NULL, date TEXT DEFAULT '', time TEXT DEFAULT '', with_ TEXT DEFAULT '', created_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT DEFAULT 'Other', icon TEXT DEFAULT 'doc', created_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, text TEXT NOT NULL, tag TEXT DEFAULT 'decision', saved_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, event TEXT NOT NULL, model_used TEXT DEFAULT '', model_alias TEXT DEFAULT '', rationale TEXT DEFAULT '', cost_usd REAL DEFAULT 0.0, cost_saved_usd REAL DEFAULT 0.0, latency_ms REAL DEFAULT 0.0, is_fast_model INTEGER DEFAULT 0, cascaded INTEGER DEFAULT 0)""")
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

low_cost_model = ModelConfig(name="groq/llama-3.1-8b-instant", provider="groq", api_key=GROQ_API_KEY, cost=0.08, speed_ms=500, quality_score=0.6, keywords=["hi","hello","hey","task","meeting","todo","done","list","schedule","thanks","bye","ok"])
high_capacity_model = ModelConfig(name="groq/llama-3.3-70b-versatile", provider="groq", api_key=GROQ_API_KEY, cost=0.79, speed_ms=1500, quality_score=0.95, keywords=["fundraising","investor","pitch","strategy","decision","prep","revenue","mrr","burn","runway","founder","architecture","complex"])

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
    if not hindsight_client or not HINDSIGHT_PIPELINE_ID:
        return False
    try:
        hindsight_client.retain(bank_id=HINDSIGHT_PIPELINE_ID, content=content)
        log_audit("Memory retain via Hindsight SDK")
        analytics_store["routing"]["hindsight_save"] += 1
        return True
    except Exception as e:
        print(f"[Hindsight Save Error]: {e}")
        return False

def recall_memories_hindsight(query):
    if not hindsight_client or not HINDSIGHT_PIPELINE_ID:
        return ""
    try:
        response = hindsight_client.recall(bank_id=HINDSIGHT_PIPELINE_ID, query=query)
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

def ask_cascadeflow(user_message, long_term_memories=""):
    global conversation_history
    if cascade_agent is None:
        log_audit("Cascadeflow call skipped -- no API key")
        return {"reply": "Groq/Cascadeflow API Error: GROQ_API_KEY missing. Add it to .env and restart.", "tokens": 0, "cost_usd": 0.0, "cost_saved_usd": 0.0, "latency_ms": 0.0, "model_used": "none", "model_alias": "none", "is_fast_model": False, "cascaded": False, "error": True}

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT priority, text FROM tasks WHERE done = 0 ORDER BY created_at DESC LIMIT 10")
        open_tasks = c.fetchall()
        c.execute("SELECT title, date, time, with_ FROM meetings ORDER BY created_at DESC LIMIT 3")
        upcoming_meetings = c.fetchall()

    task_ctx = ("\n\nOPEN TASKS:\n" + "\n".join(f"- [{t['priority'].upper()}] {t['text']}" for t in open_tasks)) if open_tasks else ""
    meeting_ctx = ("\n\nUPCOMING MEETINGS:\n" + "\n".join(f"- {m['title']} on {m['date'] or 'TBD'} at {m['time'] or 'TBD'} with {m['with_'] or '--'}" for m in upcoming_meetings)) if upcoming_meetings else ""

    system_prompt = f"""You are FounderMind -- an elite AI Chief of Staff for startup founders.
You have TWO sources of memory:
1. LONG-TERM MEMORIES (from past sessions):
{long_term_memories if long_term_memories else "No past session memories yet."}
2. CURRENT SESSION HISTORY (included in this conversation).
{task_ctx}
{meeting_ctx}
YOUR RULES:
- ALWAYS use memories to answer questions about the founder
- Be sharp, direct, strategic -- like a trusted Chief of Staff
- Reference past context naturally in every response
- When asked about tasks or meetings, reference the live data above"""

    history_str = ""
    if conversation_history:
        history_str = "\nRecent Conversation:\n" + "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in conversation_history[-6:])

    full_query = f"{system_prompt}\n{history_str}\n\nUser: {user_message}"
    complexity_hint = classify_intent(user_message)

    start_time = time.time()
    try:
        result = cascade_agent.run(query=full_query, max_tokens=600, temperature=0.1, complexity_hint=complexity_hint)
        latency_ms = round((time.time() - start_time) * 1000, 2)

        reply = getattr(result, "content", "") or str(result)
        model_used = getattr(result, "model_used", "groq/llama-3.3-70b-versatile")
        cost_usd = getattr(result, "total_cost", None) or getattr(result, "draft_cost", 0.0001) or 0.0001
        cascaded = bool(getattr(result, "cascaded", False))

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
        log_audit(f"Cascadeflow call failed -- {err_text[:80]}")
        return {"reply": f"Cascadeflow Error: {err_text}", "tokens": 0, "cost_usd": 0.0, "cost_saved_usd": 0.0, "latency_ms": latency_ms, "model_used": "error", "model_alias": "error", "is_fast_model": False, "cascaded": False, "error": True}


@app.route("/")
def index():
    if os.path.exists(os.path.join(BASE_DIR, FRONTEND_FILENAME)):
        return send_from_directory(BASE_DIR, FRONTEND_FILENAME)
    elif os.path.exists(os.path.join(BASE_DIR, "index.html")):
        return send_from_directory(BASE_DIR, "index.html")
    return "FounderMind backend running."


@app.route("/chat", methods=["POST"])
def chat():
    data = get_json_body()
    user_message = (data.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "No message"}), 400

    print(f"\n[User]: {user_message}")
    long_term = recall_memories_hindsight(user_message)
    result = ask_cascadeflow(user_message, long_term)
    reply, had_error = result["reply"], result["error"]
    print(f"[FounderMind]: {reply[:120]}...")

    skip_words = {"hi","hello","hey","ok","okay","thanks","bye","yo"}
    should_save = (not had_error) and (user_message.lower().strip() not in skip_words)

    if should_save:
        save_memory_hindsight(f"[{now_str()}]\nFounder: {user_message}\nFounderMind: {reply}")
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
                conn.execute("INSERT INTO memories (id, text, tag, saved_at) VALUES (?, ?, ?, ?)", (mem_id, user_message, tag, saved_at))
                conn.commit()
        except Exception as e:
            print(f"[DB Memory Insert Error]: {e}")

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

    return jsonify({"response": reply, "memory_saved": should_save, "memory_recalled": memory_recalled, "recalled_count": recalled_count, "tokens": result["tokens"], "cost_usd": result["cost_usd"], "cost_saved_usd": result.get("cost_saved_usd", 0.0), "latency_ms": result["latency_ms"], "model_used": result["model_used"], "model_alias": result.get("model_alias",""), "is_fast_model": result.get("is_fast_model", False), "cascaded": result["cascaded"], "telemetry": telemetry})


@app.route("/reset", methods=["POST"])
def reset_session():
    global conversation_history
    conversation_history = []
    log_audit("Session reset -- conversation history cleared")
    return jsonify({"status": "Session cleared. Long-term memories preserved."})


@app.route("/tasks", methods=["GET"])
def get_tasks():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, text, priority, done, created_at FROM tasks ORDER BY created_at DESC")
        tasks = [{"id": r["id"], "text": r["text"], "priority": r["priority"], "done": bool(r["done"]), "created_at": r["created_at"]} for r in c.fetchall()]
    return jsonify(tasks)


@app.route("/tasks", methods=["POST"])
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
def get_meetings():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, title, date, time, with_, created_at FROM meetings ORDER BY created_at DESC")
        meetings = [dict(r) for r in c.fetchall()]
    return jsonify(meetings)


@app.route("/meetings", methods=["POST"])
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
def get_documents():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, name, type, icon, created_at FROM documents ORDER BY created_at DESC")
        docs = [dict(r) for r in c.fetchall()]
    return jsonify(docs)


@app.route("/documents", methods=["POST"])
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
def get_memories():
    query = request.args.get("q", "").lower().strip()
    with get_db_connection() as conn:
        c = conn.cursor()
        if query:
            c.execute("SELECT id, text, tag, saved_at FROM memories WHERE LOWER(text) LIKE ? ORDER BY saved_at DESC", (f"%{query}%",))
        else:
            c.execute("SELECT id, text, tag, saved_at FROM memories ORDER BY saved_at DESC")
        memories = [dict(r) for r in c.fetchall()]
    return jsonify(memories)


@app.route("/memories/search", methods=["GET"])
def search_memories_route():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Query required"}), 400
    result = recall_memories_hindsight(query)
    return jsonify({"query": query, "results": result})


@app.route("/memories/hindsight", methods=["GET"])
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
def save_memory_route():
    data = get_json_body()
    text = (data.get("text") or "").strip()
    tag = data.get("tag", "decision")
    if not text:
        return jsonify({"error": "Text required"}), 400
    mem_id = str(uuid.uuid4())
    saved_at = now_str()
    with get_db_connection() as conn:
        conn.execute("INSERT INTO memories (id, text, tag, saved_at) VALUES (?, ?, ?, ?)", (mem_id, text, tag, saved_at))
        conn.commit()
    save_memory_hindsight(f"[{saved_at}]\n{text}")
    analytics_store["memories_saved"] += 1
    return jsonify({"id": mem_id, "text": text, "tag": tag, "saved_at": saved_at}), 201


@app.route("/memories/<mem_id>", methods=["DELETE"])
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
def get_settings():
    return jsonify({
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

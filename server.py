from __future__ import annotations  # lets `dict | None` etc. run on Python < 3.10

import os
import json
import uuid
import datetime
import urllib.request
import urllib.parse
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_FILENAME = "FounderMind_Enhanced_fixed.html"

app = Flask(__name__, static_folder=None)
CORS(app)

# ══════════════════════════════════════════════════════════
#  CLIENTS
# ══════════════════════════════════════════════════════════
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY")
HINDSIGHT_PIPELINE_ID = os.getenv("HINDSIGHT_PIPELINE_ID")

print(f"🔑 Groq Key:      {'✅' if GROQ_API_KEY else '❌ MISSING'}")
print(f"🔑 Hindsight Key: {'✅' if HINDSIGHT_API_KEY else '❌ MISSING'}")
print(f"🔑 Pipeline ID:   {'✅' if HINDSIGHT_PIPELINE_ID else '❌ MISSING'}")


# ══════════════════════════════════════════════════════════
#  IN-MEMORY STORES  (reset on restart — long-term memory
#  persistence lives in Hindsight, not here)
# ══════════════════════════════════════════════════════════
conversation_history: list[dict] = []

tasks_store:     list[dict] = []   # {id, text, priority, done, created_at}
meetings_store:  list[dict] = []   # {id, title, date, time, with_, created_at}
documents_store: list[dict] = []   # {id, name, type, icon, created_at}
memories_store:  list[dict] = []   # {id, text, tag, saved_at} — local mirror of Hindsight

analytics_store = {
    "total_messages": 0,
    "total_tokens": 0,
    "memories_saved": 0,
    "sessions": 1,
    "budget_used": 0.0,
    "budget_limit": 100.0,
    "routing": {"groq_llama": 0, "hindsight_recall": 0, "hindsight_save": 0},
    "audit_trail": [],
}


# ══════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════
def now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def now_iso() -> str:
    return datetime.datetime.now().isoformat()

def get_json_body() -> dict:
    """Parse the request body defensively — never 400/415 on a slightly odd request."""
    return request.get_json(silent=True) or {}

def log_audit(event: str):
    analytics_store["audit_trail"].insert(0, {
        "time": datetime.datetime.now().strftime("%I:%M %p"),
        "event": event,
    })
    analytics_store["audit_trail"] = analytics_store["audit_trail"][:50]

def estimate_cost(tokens: int) -> float:
    return round(tokens * 0.000001, 6)  # placeholder rate, Groq is near-free


# ══════════════════════════════════════════════════════════
#  HINDSIGHT  (long-term memory across sessions)
# ══════════════════════════════════════════════════════════
def save_memory_hindsight(content: str) -> dict | None:
    if not HINDSIGHT_API_KEY or not HINDSIGHT_PIPELINE_ID:
        return None
    try:
        data = json.dumps({
            "pipeline_id": HINDSIGHT_PIPELINE_ID,
            "content": content,
            "metadata": {"timestamp": now_iso()},
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.hindsight.vectorize.io/v1/memories",
            data=data,
            headers={"Authorization": f"Bearer {HINDSIGHT_API_KEY}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            print("[Hindsight] ✅ Memory saved")
            log_audit("Memory retain — context saved to Hindsight")
            analytics_store["routing"]["hindsight_save"] += 1
            return result
    except Exception as e:
        print(f"[Hindsight Save Error]: {e}")
        log_audit(f"⚠️ Hindsight save failed — {e}")
        return None


def recall_memories_hindsight(query: str) -> str:
    if not HINDSIGHT_API_KEY or not HINDSIGHT_PIPELINE_ID:
        return ""
    try:
        params = urllib.parse.urlencode({"pipeline_id": HINDSIGHT_PIPELINE_ID, "query": query, "limit": 5})
        req = urllib.request.Request(
            f"https://api.hindsight.vectorize.io/v1/memories/search?{params}",
            headers={"Authorization": f"Bearer {HINDSIGHT_API_KEY}", "Content-Type": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            mems = result.get("memories", [])
            if mems:
                texts = [m.get("content", "") for m in mems]
                print(f"[Hindsight] ✅ Recalled {len(texts)} memories")
                log_audit(f"Memory recall — {len(texts)} memories retrieved")
                analytics_store["routing"]["hindsight_recall"] += 1
                return "\n---\n".join(texts)
            return ""
    except Exception as e:
        print(f"[Hindsight Recall Error]: {e}")
        log_audit(f"⚠️ Hindsight recall failed — {e}")
        return ""


# ══════════════════════════════════════════════════════════
#  GROQ  (primary LLM) — every call is wrapped so a bad/missing
#  key or a network error comes back as a clean message instead
#  of a 500 crash.
# ══════════════════════════════════════════════════════════
def groq_completion(messages: list, max_tokens: int = 600, temperature: float = 0.1) -> dict:
    """Bare Groq call. Returns {reply, tokens, error}. Never raises."""
    if groq_client is None:
        msg = "⚠️ Groq API Error: GROQ_API_KEY is missing. Add it to your .env file and restart the server."
        print("[Groq Error]: no API key configured")
        log_audit("⚠️ Groq call skipped — no API key configured")
        return {"reply": msg, "tokens": 0, "error": True}

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        reply = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else 0
        return {"reply": reply, "tokens": tokens, "error": False}

    except Exception as e:
        err_text = str(e)
        low = err_text.lower()
        if "401" in err_text or "invalid_api_key" in low or "invalid api key" in low or "authentication" in low:
            friendly = "⚠️ Groq API Error: Invalid API key. Double-check GROQ_API_KEY in your .env file (no quotes, no extra spaces), then restart the server."
        elif "rate_limit" in low or "429" in err_text:
            friendly = "⚠️ Groq API Error: Rate limit hit. Wait a moment and try again."
        elif "model_not_found" in low or "does not exist" in low:
            friendly = "⚠️ Groq API Error: Model not found or not available on your account."
        else:
            friendly = f"⚠️ Groq API Error: {err_text}"
        print(f"[Groq Error]: {err_text}")
        log_audit(f"⚠️ Groq call failed — {err_text[:80]}")
        return {"reply": friendly, "tokens": 0, "error": True}


def ask_groq(user_message: str, long_term_memories: str = "") -> dict:
    """
    Main chat path. Builds full context (memories + tasks + meetings),
    calls Groq, and updates conversation_history + analytics — but only
    on success, so a failed call doesn't pollute the session transcript
    or get miscounted as a real exchange.
    """
    global conversation_history

    open_tasks = [t for t in tasks_store if not t["done"]]
    upcoming = meetings_store[:3]

    task_ctx = ""
    if open_tasks:
        task_ctx = "\n\nOPEN TASKS:\n" + "\n".join(
            f"- [{t['priority'].upper()}] {t['text']}" for t in open_tasks[:10]
        )

    meeting_ctx = ""
    if upcoming:
        meeting_ctx = "\n\nUPCOMING MEETINGS:\n" + "\n".join(
            f"- {m['title']} on {m.get('date','TBD')} at {m.get('time','TBD')} with {m.get('with_','—')}"
            for m in upcoming
        )

    system_prompt = f"""You are FounderMind — an elite AI Chief of Staff for startup founders.
You have TWO sources of memory:

1. LONG-TERM MEMORIES (from past sessions):
{long_term_memories if long_term_memories else "No past session memories yet."}

2. CURRENT SESSION HISTORY (included in this conversation).
{task_ctx}
{meeting_ctx}

YOUR RULES:
- ALWAYS use memories to answer questions about the founder
- If someone tells you their name, remember it immediately
- If someone asks what you remember, list everything from memories
- Be sharp, direct, strategic — like a trusted Chief of Staff
- Reference past context naturally in every response
- If no memory exists for something, say so honestly
- When asked about tasks or meetings, reference the live data above"""

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    result = groq_completion(messages, max_tokens=600, temperature=0.1)

    if result["error"]:
        # Don't add failed calls to history/analytics — nothing to remember here.
        return result

    reply, tokens = result["reply"], result["tokens"]

    conversation_history.append({"role": "user", "content": user_message})
    conversation_history.append({"role": "assistant", "content": reply})
    if len(conversation_history) > 20:
        conversation_history[:] = conversation_history[-20:]

    analytics_store["total_messages"] += 1
    analytics_store["total_tokens"] += tokens
    analytics_store["budget_used"] = round(analytics_store["budget_used"] + estimate_cost(tokens), 4)
    analytics_store["routing"]["groq_llama"] += 1
    log_audit(f"Routing decision — Groq llama-3.3-70b-versatile ({tokens} tokens)")

    return result


# ══════════════════════════════════════════════════════════
#  FRONTEND
# ══════════════════════════════════════════════════════════
@app.route("/")
def index():
    if os.path.exists(os.path.join(BASE_DIR, FRONTEND_FILENAME)):
        return send_from_directory(BASE_DIR, FRONTEND_FILENAME)
    return "FounderMind backend is running. Place the frontend HTML next to server.py to serve it here."


# ══════════════════════════════════════════════════════════
#  CHAT
# ══════════════════════════════════════════════════════════
@app.route("/chat", methods=["POST"])
def chat():
    data = get_json_body()
    user_message = (data.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "No message"}), 400

    print(f"\n[User]: {user_message}")

    long_term = recall_memories_hindsight(user_message)
    result = ask_groq(user_message, long_term)
    reply, tokens, had_error = result["reply"], result["tokens"], result["error"]

    print(f"[FounderMind]: {reply[:120]}...")

    # Never save an error message as a "memory"
    skip_words = {"hi", "hello", "hey", "ok", "okay", "thanks", "bye", "yo"}
    should_save = (not had_error) and (user_message.lower().strip() not in skip_words)

    if should_save:
        save_memory_hindsight(f"[{now_str()}]\nFounder: {user_message}\nFounderMind: {reply}")
        analytics_store["memories_saved"] += 1

        tag = "decision"
        text = user_message.lower()
        if any(k in text for k in ["investor", "funding", "pitch", "vc", "seed", "series"]):
            tag = "investor"
        elif any(k in text for k in ["meeting", "call", "sync"]):
            tag = "meeting"
        elif any(k in text for k in ["task", "deadline", "todo", "finish", "complete"]):
            tag = "task"
        elif any(k in text for k in ["revenue", "mrr", "arr", "churn", "runway", "burn"]):
            tag = "revenue"

        memories_store.insert(0, {
            "id": str(uuid.uuid4()),
            "text": user_message,
            "tag": tag,
            "saved_at": now_str(),
        })

    return jsonify({"response": reply, "memory_saved": should_save, "tokens": tokens})


@app.route("/reset", methods=["POST"])
def reset_session():
    global conversation_history
    conversation_history = []
    log_audit("Session reset — conversation history cleared")
    return jsonify({"status": "Session cleared. Long-term memories preserved."})


# ══════════════════════════════════════════════════════════
#  TASKS
# ══════════════════════════════════════════════════════════
@app.route("/tasks", methods=["GET"])
def get_tasks():
    return jsonify(tasks_store)


@app.route("/tasks", methods=["POST"])
def add_task():
    data = get_json_body()
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Task text required"}), 400
    task = {"id": str(uuid.uuid4()), "text": text, "priority": data.get("priority", "med"), "done": False, "created_at": now_iso()}
    tasks_store.insert(0, task)
    log_audit(f"Task added — [{task['priority'].upper()}] {text[:40]}")
    return jsonify(task), 201


@app.route("/tasks/<task_id>", methods=["PATCH"])
def update_task(task_id):
    task = next((t for t in tasks_store if t["id"] == task_id), None)
    if not task:
        return jsonify({"error": "Not found"}), 404
    data = get_json_body()
    if "done" in data:
        task["done"] = bool(data["done"])
        log_audit(f"Task {'completed' if task['done'] else 'reopened'} — {task['text'][:40]}")
    if "priority" in data:
        task["priority"] = data["priority"]
    if "text" in data:
        task["text"] = data["text"]
    return jsonify(task)


@app.route("/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    global tasks_store
    before = len(tasks_store)
    tasks_store = [t for t in tasks_store if t["id"] != task_id]
    if len(tasks_store) == before:
        return jsonify({"error": "Not found"}), 404
    log_audit(f"Task deleted — id {task_id[:8]}")
    return jsonify({"status": "deleted"})


# ══════════════════════════════════════════════════════════
#  MEETINGS
# ══════════════════════════════════════════════════════════
@app.route("/meetings", methods=["GET"])
def get_meetings():
    return jsonify(meetings_store)


@app.route("/meetings", methods=["POST"])
def add_meeting():
    data = get_json_body()
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Meeting title required"}), 400
    meeting = {
        "id": str(uuid.uuid4()),
        "title": title,
        "date": data.get("date", ""),
        "time": data.get("time", ""),
        "with_": data.get("with_", ""),
        "created_at": now_iso(),
    }
    meetings_store.insert(0, meeting)
    log_audit(f"Meeting scheduled — {title[:40]} on {meeting['date'] or 'TBD'}")
    return jsonify(meeting), 201


@app.route("/meetings/<meeting_id>/prep", methods=["GET"])
def ai_prep_meeting(meeting_id):
    meeting = next((m for m in meetings_store if m["id"] == meeting_id), None)
    if not meeting:
        return jsonify({"error": "Not found"}), 404

    prompt = (
        f'Prepare me for this meeting: "{meeting["title"]}"'
        + (f' with {meeting["with_"]}' if meeting.get("with_") else "")
        + f' scheduled for {meeting.get("date","TBD")} at {meeting.get("time","TBD")}.'
        + " Give me: key objectives, 5 smart questions to ask, potential risks, and desired outcomes. Be concise."
    )

    long_term = recall_memories_hindsight(prompt)
    mem_ctx = f"\n\nRelevant long-term memories:\n{long_term}" if long_term else ""

    result = groq_completion([
        {"role": "system", "content": "You are FounderMind, an elite AI Chief of Staff for startup founders. Be concise and actionable." + mem_ctx},
        {"role": "user", "content": prompt},
    ])

    if not result["error"]:
        analytics_store["total_tokens"] += result["tokens"]
        analytics_store["budget_used"] = round(analytics_store["budget_used"] + estimate_cost(result["tokens"]), 4)
        analytics_store["routing"]["groq_llama"] += 1
        log_audit(f"AI Prep generated — {meeting['title'][:40]}")

    return jsonify({"meeting": meeting, "prep": result["reply"]})


@app.route("/meetings/<meeting_id>", methods=["DELETE"])
def delete_meeting(meeting_id):
    global meetings_store
    before = len(meetings_store)
    meetings_store = [m for m in meetings_store if m["id"] != meeting_id]
    if len(meetings_store) == before:
        return jsonify({"error": "Not found"}), 404
    log_audit(f"Meeting deleted — id {meeting_id[:8]}")
    return jsonify({"status": "deleted"})


# ══════════════════════════════════════════════════════════
#  DOCUMENTS
# ══════════════════════════════════════════════════════════
@app.route("/documents", methods=["GET"])
def get_documents():
    return jsonify(documents_store)


@app.route("/documents", methods=["POST"])
def add_document():
    data = get_json_body()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Document name required"}), 400
    doc_type = data.get("type", "📄 Other")
    icon = doc_type.split(" ")[0] if " " in doc_type else "📄"
    doc = {"id": str(uuid.uuid4()), "name": name, "type": doc_type, "icon": icon, "created_at": now_iso()}
    documents_store.insert(0, doc)
    log_audit(f"Document added — {name[:40]}")
    return jsonify(doc), 201


@app.route("/documents/<doc_id>", methods=["DELETE"])
def delete_document(doc_id):
    global documents_store
    before = len(documents_store)
    documents_store = [d for d in documents_store if d["id"] != doc_id]
    if len(documents_store) == before:
        return jsonify({"error": "Not found"}), 404
    log_audit(f"Document deleted — id {doc_id[:8]}")
    return jsonify({"status": "deleted"})


# ══════════════════════════════════════════════════════════
#  MEMORIES
# ══════════════════════════════════════════════════════════
@app.route("/memories", methods=["GET"])
def get_memories():
    query = request.args.get("q", "").lower()
    if query:
        return jsonify([m for m in memories_store if query in m["text"].lower()])
    return jsonify(memories_store)


@app.route("/memories/search", methods=["GET"])
def search_memories_route():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Query required"}), 400
    result = recall_memories_hindsight(query)
    return jsonify({"query": query, "results": result})


@app.route("/memories", methods=["POST"])
def save_memory_route():
    data = get_json_body()
    text = (data.get("text") or "").strip()
    tag = data.get("tag", "decision")
    if not text:
        return jsonify({"error": "Text required"}), 400
    mem = {"id": str(uuid.uuid4()), "text": text, "tag": tag, "saved_at": now_str()}
    memories_store.insert(0, mem)
    save_memory_hindsight(f"[{now_str()}]\n{text}")
    analytics_store["memories_saved"] += 1
    return jsonify(mem), 201


@app.route("/memories/<mem_id>", methods=["DELETE"])
def delete_memory(mem_id):
    global memories_store
    before = len(memories_store)
    memories_store = [m for m in memories_store if m["id"] != mem_id]
    if len(memories_store) == before:
        return jsonify({"error": "Not found"}), 404
    log_audit(f"Memory deleted — id {mem_id[:8]}")
    return jsonify({"status": "deleted"})


# ══════════════════════════════════════════════════════════
#  ANALYTICS
# ══════════════════════════════════════════════════════════
@app.route("/analytics", methods=["GET"])
def get_analytics():
    total = analytics_store["routing"]["groq_llama"] or 1
    hindsight_calls = analytics_store["routing"]["hindsight_recall"] + analytics_store["routing"]["hindsight_save"]
    return jsonify({
        "total_messages": analytics_store["total_messages"],
        "total_tokens": analytics_store["total_tokens"],
        "memories_saved": analytics_store["memories_saved"],
        "sessions": analytics_store["sessions"],
        "budget_used": analytics_store["budget_used"],
        "budget_limit": analytics_store["budget_limit"],
        "budget_pct": round(analytics_store["budget_used"] / analytics_store["budget_limit"] * 100, 1),
        "routing": {
            "groq_llama_pct": round(analytics_store["routing"]["groq_llama"] / total * 100, 1),
            "hindsight_pct": round(hindsight_calls / max(total + hindsight_calls, 1) * 100, 1),
        },
        "audit_trail": analytics_store["audit_trail"][:20],
    })


# ══════════════════════════════════════════════════════════
#  SETTINGS / HEALTH
# ══════════════════════════════════════════════════════════
@app.route("/settings", methods=["GET"])
def get_settings():
    return jsonify({
        "model": "llama-3.3-70b-versatile",
        "max_tokens": 600,
        "temperature": 0.1,
        "stack": {
            "groq": {"status": "CONNECTED" if GROQ_API_KEY else "DISCONNECTED", "model": "llama-3.3-70b-versatile"},
            "hindsight": {"status": "CONNECTED" if HINDSIGHT_API_KEY else "DISCONNECTED"},
            "cascadeflow": {"status": "CONNECTED"},
        },
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "model": "llama-3.3-70b-versatile",
        "groq": "connected" if GROQ_API_KEY else "missing-key",
        "hindsight": "connected" if HINDSIGHT_API_KEY else "missing-key",
        "session_messages": len(conversation_history),
        "tasks": len(tasks_store),
        "meetings": len(meetings_store),
        "documents": len(documents_store),
        "memories": len(memories_store),
    })


# ══════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🧠  FounderMind Server  —  Enhanced Edition")
    print("=" * 60)
    print("  GET   /                      — Serves the frontend")
    print("  POST  /chat                  — AI chat (Groq + Hindsight)")
    print("  POST  /reset                 — Clear session history")
    print("  GET   /tasks  POST /tasks    — List / add tasks")
    print("  PATCH /tasks/<id>  DEL       — Update / delete task")
    print("  GET   /meetings  POST        — List / add meetings")
    print("  GET   /meetings/<id>/prep    — AI prep for meeting")
    print("  DEL   /meetings/<id>         — Delete meeting")
    print("  GET   /documents  POST       — List / add documents")
    print("  DEL   /documents/<id>        — Delete document")
    print("  GET   /memories  POST        — List / save memories (?q=search)")
    print("  GET   /memories/search       — Hindsight semantic search")
    print("  DEL   /memories/<id>         — Delete memory")
    print("  GET   /analytics             — Dashboard data")
    print("  GET   /settings              — Stack status + config")
    print("  GET   /health                — Health check")
    print("=" * 60 + "\n")

    if not GROQ_API_KEY:
        print("⚠️  GROQ_API_KEY is not set — /chat will return a clear error instead of crashing.")

    log_audit("FounderMind server started")
    analytics_store["sessions"] += 1

    app.run(host="0.0.0.0", debug=True, port=5000)
import os
import json
import datetime
import urllib.request
import urllib.parse
from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ── Clients ──────────────────────────────────────────────
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY")
HINDSIGHT_PIPELINE_ID = os.getenv("HINDSIGHT_PIPELINE_ID")

print(f"🔑 Groq Key loaded: {'✅' if os.getenv('GROQ_API_KEY') else '❌ MISSING'}")
print(f"🔑 Hindsight Key loaded: {'✅' if HINDSIGHT_API_KEY else '❌ MISSING'}")
print(f"🔑 Pipeline ID loaded: {'✅' if HINDSIGHT_PIPELINE_ID else '❌ MISSING'}")

# ── In-session conversation history ──────────────────────
# This keeps the CURRENT session chat history in memory
conversation_history = []

# ── Hindsight Memory (long-term, across sessions) ─────────
def save_memory(content: str):
    """Save to Hindsight — persists across sessions"""
    try:
        data = json.dumps({
            "pipeline_id": HINDSIGHT_PIPELINE_ID,
            "content": content,
            "metadata": {"timestamp": str(datetime.datetime.now())}
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.hindsight.vectorize.io/v1/memories",
            data=data,
            headers={
                "Authorization": f"Bearer {HINDSIGHT_API_KEY}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read())
            print(f"[Hindsight] ✅ Memory saved successfully")
            return result
    except Exception as e:
        print(f"[Hindsight Save Error]: {e}")
        return None


def recall_memories(query: str):
    """Recall from Hindsight — fetches past session memories"""
    try:
        params = urllib.parse.urlencode({
            "pipeline_id": HINDSIGHT_PIPELINE_ID,
            "query": query,
            "limit": 5
        })
        req = urllib.request.Request(
            f"https://api.hindsight.vectorize.io/v1/memories/search?{params}",
            headers={
                "Authorization": f"Bearer {HINDSIGHT_API_KEY}",
                "Content-Type": "application/json"
            },
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read())
            memories = result.get("memories", [])
            if memories:
                texts = [m.get("content", "") for m in memories]
                print(f"[Hindsight] ✅ Recalled {len(texts)} memories")
                return "\n---\n".join(texts)
            print("[Hindsight] No memories found.")
            return ""
    except Exception as e:
        print(f"[Hindsight Recall Error]: {e}")
        return ""


# ── Groq AI ───────────────────────────────────────────────
def ask_groq(user_message: str, long_term_memories: str = ""):
    """
    Sends FULL conversation history + long-term memories to Groq.
    This is the fix — AI now sees everything!
    """
    global conversation_history

    # Build system prompt with long-term memories injected
    system_prompt = f"""You are FounderMind — an elite AI Chief of Staff for startup founders.
You have TWO sources of memory:

1. LONG-TERM MEMORIES (from past sessions):
{long_term_memories if long_term_memories else "No past session memories yet."}

2. CURRENT SESSION HISTORY (below in the conversation):
The full conversation so far is included in this request.

YOUR RULES:
- ALWAYS use memories to answer questions about the founder
- If someone tells you their name, remember it immediately
- If someone asks what you remember, list everything from memories
- Be sharp, direct, strategic — like a trusted Chief of Staff
- Reference past context naturally in every response
- If no memory exists for something, say so honestly"""

    # Build messages: system + FULL conversation history + new message
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add all previous turns from this session
    messages.extend(conversation_history)
    
    # Add the new user message
    messages.append({"role": "user", "content": user_message})

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=600,
        temperature=0.1
    )
    
    assistant_reply = response.choices[0].message.content

    # ✅ Add this exchange to session history
    conversation_history.append({"role": "user", "content": user_message})
    conversation_history.append({"role": "assistant", "content": assistant_reply})

    # Keep history to last 20 messages (10 exchanges) to avoid token limits
    if len(conversation_history) > 20:
        conversation_history = conversation_history[-20:]

    return assistant_reply


# ── Routes ────────────────────────────────────────────────
@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get('message', '').strip()
    
    if not user_message:
        return jsonify({'error': 'No message'}), 400

    print(f"\n[User]: {user_message}")

    # Step 1: Recall long-term memories from Hindsight FIRST
    long_term_memories = recall_memories(user_message)

    # Step 2: Get AI response with full context
    response = ask_groq(user_message, long_term_memories)
    
    print(f"[FounderMind]: {response[:100]}...")

    # Step 3: Save to Hindsight for future sessions
    # Only save meaningful messages (not greetings)
    skip_words = ["hi", "hello", "hey", "ok", "okay", "thanks", "bye"]
    should_save = not any(
        user_message.lower().strip() == word for word in skip_words
    )
    
    if should_save:
        save_memory(
            f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}]\n"
            f"Founder: {user_message}\n"
            f"FounderMind: {response}"
        )

    return jsonify({
        'response': response,
        'memory_saved': should_save
    })


@app.route('/reset', methods=['POST'])
def reset_session():
    """Reset current session history (but keeps long-term Hindsight memories)"""
    global conversation_history
    conversation_history = []
    return jsonify({'status': 'Session history cleared. Long-term memories preserved.'})


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'model': 'llama-3.3-70b-versatile',
        'hindsight': 'connected',
        'session_messages': len(conversation_history)
    })


if __name__ == '__main__':
    print("\n" + "="*50)
    print("🧠 FounderMind Server starting...")
    print("="*50)
    app.run(debug=True, port=5000)
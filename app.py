import os
import json
import datetime
from groq import Groq
from dotenv import load_dotenv

# Load the environment variables from the .env file
load_dotenv()

# ── API Keys & Verification ──────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY")
HINDSIGHT_PIPELINE_ID = os.getenv("HINDSIGHT_PIPELINE_ID")

# VS Code Environment Sanity Check
if not GROQ_API_KEY or not HINDSIGHT_API_KEY:
    print("❌ ERROR: Keys not detected! VS Code terminal is looking in the wrong folder.")
    print("👉 FIX: In VS Code, right-click your project folder and select 'Open in Integrated Terminal', then run the file.")
    exit(1)

# ── Groq Client ───────────────────────────────────────────
client = Groq(api_key=GROQ_API_KEY)

# ── Hindsight Memory Functions ────────────────────────────
def save_memory(content: str):
    """Save a memory to Hindsight"""
    try:
        import urllib.request
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
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"[Memory Save Error]: {e}")
        return None


def recall_memories(query: str):
    """Recall relevant memories from Hindsight"""
    try:
        import urllib.request
        import urllib.parse
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
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read())
            memories = result.get("memories", [])
            if memories:
                return "\n".join([m.get("content", "") for m in memories])
            return "No previous memories found."
    except Exception as e:
        print(f"[Memory Recall Error]: {e}")
        return "No previous memories found."


# ── cascadeflow Budget Control ────────────────────────────
try:
    from cascadeflow import CascadeFlow
    cf = CascadeFlow(budget_usd=1.0)
    USE_CASCADEFLOW = True
    print("✅ cascadeflow budget control active ($1.00 limit)")
except Exception:
    USE_CASCADEFLOW = False


# ── AI Brain (Groq) ───────────────────────────────────────
def ask_groq(user_message: str, memory_context: str = ""):
    """Send message to Groq with memory context"""
    system_prompt = f"""You are FounderMind — an elite AI Chief of Staff for startup founders.
You remember everything about the founder's startup journey.

Your personality:
- Sharp, direct, and strategic
- You speak like a trusted advisor, not a chatbot
- You always reference past context when relevant

Previous memories about this founder:
{memory_context if memory_context else "No previous context yet. This may be the first session."}

Your job:
1. Help the founder with investor meetings, tasks, and decisions
2. Always remind them of relevant past information
3. Give strategic advice based on their startup history
4. Track important tasks and follow-ups

Always end responses with: "💾 Memory saved." when you save something important."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    # FIX: Corrected model ID from "qwen-qwen3-32b" to "qwen/qwen3-32b"
    response = client.chat.completions.create(
        model="qwen/qwen3-32b", 
        messages=messages,
        max_tokens=500
    )
    return response.choices[0].message.content


# ── Morning Briefing ──────────────────────────────────────
def morning_briefing():
    """Generate a morning briefing from memories"""
    print("\n" + "="*50)
    print("☀️  FOUNDERMIND MORNING BRIEFING")
    print("="*50)
    memories = recall_memories("tasks deadlines investors follow-up")
    briefing = ask_groq(
        "Give me a quick morning briefing. What are my most important tasks, investor follow-ups, and deadlines based on what you know?",
        memories
    )
    print(f"\n{briefing}\n")
    print("="*50 + "\n")


# ── Main Chat Loop ────────────────────────────────────────
def main():
    print("\n" + "="*50)
    print("🧠 FOUNDERMIND — AI that remembers your startup")
    print("        better than you do.")
    print("="*50)
    print("Commands:")
    print("  'brief'  → Get morning briefing")
    print("  'quit'   → Exit")
    print("="*50 + "\n")

    # Auto morning briefing on startup
    morning_briefing()

    while True:
        try:
            user_input = input("You: ").strip()
        except KeyboardInterrupt:
            print("\n\nGoodbye! FounderMind is always here. 🧠")
            break

        if not user_input:
            continue

        if user_input.lower() == "quit":
            print("Goodbye! FounderMind is always here. 🧠")
            break

        if user_input.lower() == "brief":
            morning_briefing()
            continue

        # Recall relevant memories
        memories = recall_memories(user_input)

        # Get AI response
        print("\nFounderMind: thinking...\n")
        response = ask_groq(user_input, memories)
        print(f"FounderMind: {response}\n")

        # Auto-save important information to memory
        important_keywords = [
            "investor", "meeting", "task", "deadline", "decision",
            "revenue", "user", "feature", "pitch", "follow-up",
            "problem", "launch", "hire", "fund", "partner"
        ]
        if any(word in user_input.lower() for word in important_keywords):
            save_memory(f"Founder said: {user_input}\nFounderMind responded: {response}")
            print("💾 Saved to memory.\n")


if __name__ == "__main__":
    main()
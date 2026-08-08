"""
test_hindsight_timeline.py
===========================
Synthetic Timeline Test Script simulating a 5-Session Startup Founder Story Arc.

Session Arc:
  • Session 1 [investor]: Founder logs Sequoia pitch meeting where investors raised concerns
    over high Customer Acquisition Cost (CAC = $350) and long payback period (14 months).
  • Session 2 [revenue / task]: Founder sets a $50k MRR milestone target and plans to hire a VP of Sales.
  • Session 3 [decision / revenue]: Founder launches a pricing experiment (raising enterprise tier
    from $99/mo to $299/mo and eliminating low-converting free tiers).
  • Session 4 [revenue / decision]: Founder reviews early pricing experiment results: payback period
    dropped to 3.5 months, ACV increased 3x, unit economics stabilized.
  • Session 5 [investor update]: Founder prompts: "Draft an investor update email to Sequoia."

Verification Criteria:
  1. Hindsight semantic search retrieves Session 1 CAC concerns, Session 2 $50k MRR goal, and Session 3/4 pricing data.
  2. Automatic injection into system prompt ensures the LLM addresses Sequoia's CAC objections directly without explicit prompting.
"""

from __future__ import annotations
import os
import sys
import json
import time
import datetime
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

# Import hindsight_manager and server groq wrapper
from hindsight_manager import HindsightManager, classify_memory_tag
from server import ask_cascadeflow


def run_timeline_test():
    print("\n" + "═" * 70)
    print("🧠 FOUNDERMIND — HINDSIGHT 5-SESSION TIMELINE DEMO & TEST")
    print("═" * 70)

    # Use pipeline ID from env or default FounderMind10
    pipeline_id = os.getenv("HINDSIGHT_PIPELINE_ID", "FounderMind10")
    hindsight_mgr = HindsightManager(pipeline_id=pipeline_id)

    if not hindsight_mgr.is_connected():
        print("❌ ERROR: HINDSIGHT_API_KEY is not set or client connection failed.")
        sys.exit(1)

    print(f"✅ Hindsight SDK Connected | Pipeline/Bank: '{pipeline_id}'\n")

    # -------------------------------------------------------------------------
    # SESSION 1: Sequoia Pitch & CAC Objections
    # -------------------------------------------------------------------------
    print("── SESSION 1: Investor Pitch with Sequoia Capital ──")
    s1_timestamp = "2026-07-01 10:00"
    s1_content = (
        f"[{s1_timestamp}] Investor Pitch Note: Had a key pitch meeting with Sequoia Capital. "
        "Partners were interested in our market size but raised major concerns about our high "
        "Customer Acquisition Cost (CAC = $350) and long CAC payback period of 14 months."
    )
    s1_tag = classify_memory_tag(s1_content)
    print(f"Logging Session 1 [Tag: {s1_tag}]...")
    res1 = hindsight_mgr.retain_memory(s1_content, tag=s1_tag)
    print(f"Session 1 saved: {res1.get('success') if res1 else 'Failed'}\n")

    # -------------------------------------------------------------------------
    # SESSION 2: $50k MRR Target & VP of Sales Hiring
    # -------------------------------------------------------------------------
    print("── SESSION 2: Growth Strategy & Targets ──")
    s2_timestamp = "2026-07-08 14:30"
    s2_content = (
        f"[{s2_timestamp}] Strategic Goal: Set our Q3 target to hit $50k MRR. "
        "Decided to kick off hiring for a VP of Sales to build out our outbound enterprise motion."
    )
    s2_tag = classify_memory_tag(s2_content)
    print(f"Logging Session 2 [Tag: {s2_tag}]...")
    res2 = hindsight_mgr.retain_memory(s2_content, tag=s2_tag)
    print(f"Session 2 saved: {res2.get('success') if res2 else 'Failed'}\n")

    # -------------------------------------------------------------------------
    # SESSION 3: Pricing Experiment Launch
    # -------------------------------------------------------------------------
    print("── SESSION 3: Pricing Experiment Launch ──")
    s3_timestamp = "2026-07-15 09:15"
    s3_content = (
        f"[{s3_timestamp}] Pricing Experiment: Launched a major pricing experiment to fix unit economics. "
        "Increased enterprise subscription tier from $99/mo to $299/mo and eliminated self-serve free trials."
    )
    s3_tag = classify_memory_tag(s3_content)
    print(f"Logging Session 3 [Tag: {s3_tag}]...")
    res3 = hindsight_mgr.retain_memory(s3_content, tag=s3_tag)
    print(f"Session 3 saved: {res3.get('success') if res3 else 'Failed'}\n")

    # -------------------------------------------------------------------------
    # SESSION 4: Pricing Experiment Results
    # -------------------------------------------------------------------------
    print("── SESSION 4: Pricing Experiment Results ──")
    s4_timestamp = "2026-07-25 16:00"
    s4_content = (
        f"[{s4_timestamp}] Experiment Results: Initial data from pricing experiment shows ACV increased 3x, "
        "CAC payback period dropped drastically from 14 months to 3.5 months, and overall LTV/CAC ratio improved to 4.2x."
    )
    s4_tag = classify_memory_tag(s4_content)
    print(f"Logging Session 4 [Tag: {s4_tag}]...")
    res4 = hindsight_mgr.retain_memory(s4_content, tag=s4_tag)
    print(f"Session 4 saved: {res4.get('success') if res4 else 'Failed'}\n")

    # Short pause to let indexing stabilize in Hindsight Cloud
    print("⏳ Waiting 3 seconds for Hindsight semantic index sync...")
    time.sleep(3)

    # -------------------------------------------------------------------------
    # SESSION 5: Investor Update Email Prompt to Sequoia
    # -------------------------------------------------------------------------
    print("── SESSION 5: Founder Request (Memory Retrieval & Generation) ──")
    user_prompt = "Draft an investor update email to Sequoia."
    print(f"User Prompt: '{user_prompt}'\n")

    # Step 4a: Semantic recall via Hindsight SDK with expanded query context
    print("🔍 Recalling relevant memories from Hindsight Cloud...")
    recall_query = "Sequoia pitch CAC investor objections pricing experiment MRR target"
    recalled_memories = hindsight_mgr.recall_memories(recall_query, limit=10)
    formatted_context = hindsight_mgr.get_formatted_memory_context(recall_query, limit=10)

    print("\nRecalled Context Injected into Prompt:")
    print("─" * 60)
    print(formatted_context if formatted_context else "(No memories returned)")
    print("─" * 60 + "\n")

    # Step 4b: Pass prompt + recalled memories into Groq LLM
    print("🤖 Generating AI Response via Groq (with Hindsight context injection)...")
    ai_response_dict = ask_cascadeflow(user_prompt, long_term_memories=formatted_context)
    reply_text = ai_response_dict.get("reply", "")

    print("\nFounderMind Drafted Response:")
    print("═" * 70)
    print(reply_text)
    print("═" * 70 + "\n")

    # -------------------------------------------------------------------------
    # VERIFICATION CHECKS
    # -------------------------------------------------------------------------
    print("── VERIFICATION REPORT ──")
    recalled_text_combined = " ".join([m["text"] for m in recalled_memories]).lower()
    reply_lowered = reply_text.lower()

    # Check 1: Session 1 CAC concern retrieved
    has_cac_memory = any(w in recalled_text_combined for w in ["cac", "acquisition cost", "sequoia", "350"])
    print(f"1. Semantic Recall of Session 1 CAC Concern: {'✅ PASS' if has_cac_memory else '❌ FAIL'}")

    # Check 2: Session 3/4 Pricing Experiment data retrieved
    has_pricing_memory = any(w in recalled_text_combined for w in ["pricing", "299", "experiment", "3.5", "payback"])
    print(f"2. Semantic Recall of Session 3/4 Pricing Data: {'✅ PASS' if has_pricing_memory else '❌ FAIL'}")

    # Check 3: LLM response addresses Sequoia investor objections (CAC / payback / pricing)
    addresses_cac_objection = any(w in reply_lowered for w in ["cac", "acquisition cost", "payback", "unit economics"])
    addresses_pricing_solution = any(w in reply_lowered for w in ["pricing", "299", "tier", "mrr", "50k", "acv"])

    print(f"3. AI Addressed Investor CAC Objections:     {'✅ PASS' if addresses_cac_objection else '❌ FAIL'}")
    print(f"4. AI Incorporated Pricing Experiment Data:   {'✅ PASS' if addresses_pricing_solution else '❌ FAIL'}")

    all_passed = has_cac_memory and has_pricing_memory and addresses_cac_objection and addresses_pricing_solution
    print("\n" + "═" * 70)
    if all_passed:
        print("🎉 MULTI-SESSION MEMORY TIMELINE DEMO SUCCESSFUL!")
    else:
        print("⚠️ TIMELINE DEMO COMPLETED WITH PARTIAL VERIFICATION MATCHES.")
    print("═" * 70 + "\n")

    return all_passed


if __name__ == "__main__":
    run_timeline_test()

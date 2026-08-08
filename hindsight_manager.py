"""
hindsight_manager.py
====================
Dedicated Memory Module for FounderMind using the official `hindsight_client` SDK.

Provides structured memory storage, taxonomy schema classification (investor, decision,
revenue, task, meeting), semantic recall, prompt injection context formatting,
and synchronization for local UI memory mirrors.
"""

from __future__ import annotations
import sys
import os
import json
import uuid
import datetime
from typing import Any, List, Dict, Optional
from dotenv import load_dotenv

# Ensure UTF-8 output formatting on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Official Hindsight Client SDK
from hindsight_client import Hindsight

load_dotenv()

import asyncio

def run_async(coro):
    """Safely run an async coroutine inside synchronous contexts/Flask requests."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# ══════════════════════════════════════════════════════════
#  STARTUP MEMORY TAXONOMY & SCHEMA
# ══════════════════════════════════════════════════════════
VALID_TAGS = {"investor", "decision", "revenue", "task", "meeting"}

TAXONOMY_KEYWORDS: Dict[str, List[str]] = {
    "investor": [
        "investor", "sequoia", "pitch", "vc", "seed", "series", "cap table",
        "valuation", "term sheet", "due diligence", "investors", "angel",
        "partner", "fundraise", "fundraising", "objection", "cac concern"
    ],
    "revenue": [
        "revenue", "mrr", "arr", "pricing", "price", "cac", "ltv", "burn",
        "runway", "$50k", "$", "financial", "economics", "acv", "payback",
        "margin", "cost", "conversion", "sales target", "tier"
    ],
    "decision": [
        "decision", "pricing experiment", "experiment", "pivot", "strategy",
        "agreed", "decided", "choose", "plan", "roadmap", "approved", "launch"
    ],
    "task": [
        "task", "deadline", "todo", "finish", "complete", "hire", "hiring",
        "vp of sales", "vp", "action item", "follow-up", "followup", "deliverable"
    ],
    "meeting": [
        "meeting", "call", "sync", "demo", "discussion", "presentation", "prep"
    ],
}


def classify_memory_tag(text: str) -> str:
    """
    Auto-classify a memory content string into the FounderMind startup schema:
    'investor', 'decision', 'revenue', 'task', 'meeting' (defaulting to 'decision').
    """
    lowered = text.lower()
    scores: Dict[str, int] = {tag: 0 for tag in VALID_TAGS}

    for tag, keywords in TAXONOMY_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                scores[tag] += 1

    # Find highest scoring tag if score > 0
    best_tag = max(scores, key=lambda k: scores[k])
    if scores[best_tag] > 0:
        return best_tag
    return "decision"


# ══════════════════════════════════════════════════════════
#  HINDSIGHT MANAGER CLASS
# ══════════════════════════════════════════════════════════
class HindsightManager:
    """
    Encapsulates memory management with the official `hindsight_client` SDK.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        pipeline_id: Optional[str] = None,
        base_url: str = "https://api.hindsight.vectorize.io",
    ):
        self.api_key = api_key or os.getenv("HINDSIGHT_API_KEY")
        self.pipeline_id = pipeline_id or os.getenv("HINDSIGHT_PIPELINE_ID") or "FounderMind10"
        self.base_url = base_url

        if self.api_key:
            try:
                self.client = Hindsight(base_url=self.base_url, api_key=self.api_key)
                print(f"[HindsightManager] ✅ Initialized Hindsight SDK (Pipeline: {self.pipeline_id})")
            except Exception as e:
                print(f"[HindsightManager] ⚠️ Error initializing Hindsight client: {e}")
                self.client = None
        else:
            print("[HindsightManager] ⚠️ HINDSIGHT_API_KEY is missing. Operating in fallback mode.")
            self.client = None

    def is_connected(self) -> bool:
        return self.client is not None and bool(self.api_key) and bool(self.pipeline_id)

    def retain_memory(
        self,
        content: str,
        tag: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        bank_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retains durable long-term memory in Hindsight Cloud using the SDK.
        Automatically classifies tag if not specified.
        """
        if not self.is_connected():
            print("[HindsightManager] ⚠️ Cannot retain memory — SDK client disconnected.")
            return None

        target_bank = bank_id or self.pipeline_id
        resolved_tag = tag if (tag and tag in VALID_TAGS) else classify_memory_tag(content)
        timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        iso_str = datetime.datetime.now().isoformat()

        meta = {"timestamp": iso_str, "tag": resolved_tag, "source": "foundermind"}
        if metadata:
            for k, v in metadata.items():
                meta[str(k)] = str(v)

        async def _async_retain():
            client = Hindsight(base_url=self.base_url, api_key=self.api_key)
            try:
                return await client.aretain(
                    bank_id=target_bank,
                    content=content,
                    tags=[resolved_tag],
                    metadata=meta,
                )
            finally:
                await client.aclose()

        try:
            response = run_async(_async_retain())
            print(f"[HindsightManager] ✅ Saved memory under tag '{resolved_tag}' to bank '{target_bank}'")
            return {
                "success": getattr(response, "success", True),
                "bank_id": target_bank,
                "tag": resolved_tag,
                "content": content,
                "saved_at": timestamp_str,
                "raw_response": str(response),
            }
        except Exception as e:
            print(f"[HindsightManager Save Error]: {e}")
            return None

    def recall_memories(
        self,
        query: str,
        limit: int = 10,
        tags: Optional[List[str]] = None,
        bank_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Recalls semantically relevant memories from Hindsight Cloud using the SDK.
        """
        if not self.is_connected():
            print("[HindsightManager] ⚠️ Cannot recall memories — SDK client disconnected.")
            return []

        target_bank = bank_id or self.pipeline_id
        async def _async_recall():
            client = Hindsight(base_url=self.base_url, api_key=self.api_key)
            try:
                return await client.arecall(
                    bank_id=target_bank,
                    query=query,
                    tags=tags,
                )
            finally:
                await client.aclose()

        try:
            response = run_async(_async_recall())
            results = getattr(response, "results", []) or []

            recalled_list = []
            for item in results[:limit]:
                text = getattr(item, "text", "") or ""
                item_tags = getattr(item, "tags", []) or []
                item_meta = getattr(item, "metadata", {}) or {}
                item_id = getattr(item, "id", str(uuid.uuid4()))

                tag = item_tags[0] if item_tags else classify_memory_tag(text)

                recalled_list.append({
                    "id": item_id,
                    "text": text,
                    "tag": tag,
                    "tags": item_tags,
                    "metadata": item_meta,
                    "type": getattr(item, "type", "memory"),
                })

            print(f"[HindsightManager] ✅ Recalled {len(recalled_list)} relevant memories for query: '{query}'")
            return recalled_list

        except Exception as e:
            print(f"[HindsightManager Recall Error]: {e}")
            return []

    def get_formatted_memory_context(
        self,
        query: str,
        limit: int = 10,
        bank_id: Optional[str] = None,
    ) -> str:
        """
        Retrieves memories and formats them into a clean string ready for system prompt injection.
        """
        memories = self.recall_memories(query, limit=limit, bank_id=bank_id)
        if not memories:
            return ""

        formatted_texts = [f"• [{m['tag'].upper()}] {m['text']}" for m in memories]
        return "\n".join(formatted_texts)

    def sync_to_local_mirror(
        self,
        query: str = "startup founder investor decision revenue task meeting",
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        Pull durable memories from Hindsight Cloud to populate the UI local memory mirror.
        """
        memories = self.recall_memories(query, limit=limit)
        mirror_items = []
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        for m in memories:
            mirror_items.append({
                "id": m["id"],
                "text": m["text"],
                "tag": m["tag"],
                "saved_at": m.get("metadata", {}).get("timestamp", now_str),
                "hindsight_synced": True,
            })
        return mirror_items


# Global Default Manager Singleton Instance
hindsight_mgr = HindsightManager()

from __future__ import annotations
"""Smart query router: classifies questions into KG or text-search strategies."""

import json
import re
import time
import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4.1-mini"

# Route types
KG_DIRECT = "KG_DIRECT"
KG_RELATIONSHIP = "KG_RELATIONSHIP"
KG_TEMPORAL = "KG_TEMPORAL"
TEXT_SEARCH = "TEXT_SEARCH"
ADVERSARIAL = "ADVERSARIAL"
OPEN_DOMAIN = "OPEN_DOMAIN"


def _llm_call(api_key: str, messages: list[dict], temperature: float = 0.0, max_tokens: int = 100) -> str:
    for attempt in range(3):
        try:
            resp = httpx.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise


def classify_route(api_key: str, question: str, category: int | None = None) -> str:
    """Classify a question into a routing strategy."""
    # Hard routes based on category
    if category == 5:
        return ADVERSARIAL
    if category == 3:
        return OPEN_DOMAIN
    
    # For category 1 (single-hop) and 2 (temporal), use LLM to pick KG vs text
    prompt = f"""Classify this question into ONE retrieval route:

KG_DIRECT — Simple fact about one entity (job, hobby, pet name, favorite X, relationship status)
  Examples: "What is Sarah's job?", "What is Emma's favorite color?", "What is Daniel's dog's name?"
KG_RELATIONSHIP — Relationship between two specific entities
  Examples: "How does Emma know John?", "What gift did Sarah give Emma?"
KG_TEMPORAL — Question about when something happened or timeline
  Examples: "When did Emma start yoga?", "What happened in March?"
TEXT_SEARCH — Complex question needing full conversation context, multi-hop reasoning, or listing multiple events
  Examples: "What activities did they do during the road trip?", "How has Emma's career evolved?"

Question: {question}

Reply with ONLY one of: KG_DIRECT, KG_RELATIONSHIP, KG_TEMPORAL, TEXT_SEARCH"""

    result = _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=20).strip().upper()
    
    for route in [KG_DIRECT, KG_RELATIONSHIP, KG_TEMPORAL, TEXT_SEARCH]:
        if route in result:
            return route
    
    # Fallback based on category hints
    if category == 1:
        return KG_DIRECT
    if category == 2:
        return KG_TEMPORAL
    if category == 4:
        return TEXT_SEARCH
    return KG_DIRECT


# Re-export v10 helpers needed by core
def is_confident(answer: str) -> bool:
    uncertain_phrases = [
        "not mentioned", "no information", "i don't know", "i don't have",
        "not specified", "not clear", "cannot determine", "no evidence",
        "not enough information", "unclear", "not available", "no record",
        "not discussed", "not provided", "unable to determine", "no data",
        "doesn't mention", "does not mention", "no mention",
        "not explicitly", "cannot be determined", "isn't mentioned",
    ]
    answer_lower = answer.lower()
    return not any(phrase in answer_lower for phrase in uncertain_phrases)

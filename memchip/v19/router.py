from __future__ import annotations
"""Query classifier + adaptive strategy router + confidence escalation (v19 — same as v18)."""

import json
import time
import re
import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4.1-mini"


def _llm_call(api_key: str, messages: list[dict], temperature: float = 0.0, max_tokens: int = 200) -> str:
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


STRATEGIES = ["A", "B", "C", "D"]


def classify_query(api_key: str, question: str, category: int | None = None) -> str:
    prompt = f"""Classify this question into ONE retrieval strategy:
A = Simple fact about a person (who/what is X, what does X like)
B = Temporal or event-based (when did X happen, what happened in July)
C = Complex/multi-hop (requiring multiple facts or reasoning across sessions)
D = Only if absolutely unclear

Question: {question}

Reply with ONLY the letter: A, B, C, or D"""

    messages = [{"role": "user", "content": prompt}]
    result = _llm_call(api_key, messages, max_tokens=16).strip().upper()
    for s in STRATEGIES:
        if s in result:
            return s
    if category == 1: return "A"
    elif category == 2: return "B"
    elif category in (3, 4): return "C"
    elif category == 5: return "B"
    return "B"


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


def escalate(current_strategy: str) -> str | None:
    idx = STRATEGIES.index(current_strategy)
    if idx < len(STRATEGIES) - 1:
        return STRATEGIES[idx + 1]
    return None


def decompose_multihop(api_key: str, question: str) -> list[str]:
    prompt = f"""Break this complex question into 2-3 simpler sub-questions that can be answered independently.

Question: {question}

Output ONLY the sub-questions, one per line, numbered 1-3. No explanations."""

    messages = [{"role": "user", "content": prompt}]
    result = _llm_call(api_key, messages, max_tokens=150)
    lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
    sub_qs = []
    for line in lines:
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
        if cleaned and len(cleaned) > 5:
            sub_qs.append(cleaned)
    return sub_qs[:3] if sub_qs else [question]

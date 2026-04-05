"""v25 category-specific answerers."""
from __future__ import annotations
import time
import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4.1-mini"


def _llm_call(api_key: str, messages: list[dict], temperature: float = 0.0,
              max_tokens: int = 200, model: str = None) -> str:
    use_model = model or MODEL
    for attempt in range(3):
        try:
            resp = httpx.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": use_model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                timeout=90,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise


def answer_single_hop(api_key: str, question: str, passages: str) -> str:
    prompt = f"""Answer this question using ONLY the conversation excerpts below.

RULES:
- Be MAXIMALLY CONCISE — answer like a trivia quiz (2-10 words ideal)
- Use EXACT words from the passages — do not paraphrase or elaborate
- ONLY include facts that DIRECTLY answer the specific question
- For "how many": exact number only
- For "what does X do": only the specific activity asked about
- For "recently"/"latest": ONLY the single most recent item
- For lists: comma-separated, no bullets, no explanations
- NEVER start with "Based on..." or add context
- If not in passages: "Not mentioned"
- NEVER correct the question

Conversation excerpts:
{passages}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=100)


def answer_temporal(api_key: str, question: str, context: str) -> str:
    prompt = f"""Answer this time-related question using the information below.

RULES:
- Be CONCISE — dates, durations, or short phrases only
- Convert relative dates to absolute using session dates:
  "yesterday" in May 25 session = May 24, 2023
  "last Saturday" in May 25 session = May 20, 2023
  "last year" in May 2023 session = 2022
  "next month" in May 2023 session = June 2023
- For "how long": give the duration (e.g., "six months", "4 years")
- Use the Timeline of Events as primary source for temporal facts
- NEVER say "Based on..."
- NEVER correct the question

{context}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=100)


def answer_multihop(api_key: str, question: str, context: str) -> str:
    prompt = f"""Answer this question by combining information from multiple conversation passages.

RULES:
- Be CONCISE — shortest possible answer
- You may need to connect facts from different sessions/passages
- Use EXACT words from passages for specific items
- If the answer requires combining "Person A did X" + "X happened at Y" → give the combined answer
- NEVER correct the question
- NEVER add context or explanations

{context}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=150)


def answer_open_domain(api_key: str, question: str, passages: str) -> str:
    prompt = f"""Answer this question using the conversation excerpts AND your general knowledge.

RULES:
- Be CONCISE
- For personal facts: use the excerpts
- For world/general knowledge: you may supplement with known facts
- No long explanations

Conversation excerpts:
{passages}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=150)


def answer_adversarial(api_key: str, question: str, passages: str) -> str:
    prompt = f"""Answer this question using ONLY the passages below.

CRITICAL: Answer exactly as asked. Do NOT say "Actually, it was someone else."
Just answer the content question directly using the name from the question.

RULES:
- Be MAXIMALLY CONCISE
- Use EXACT words from passages
- NEVER say "did not" or "it was actually"

Passages:
{passages}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=100)

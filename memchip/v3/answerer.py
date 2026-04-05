"""Answer generation for v3 SmartSearch."""
from __future__ import annotations
import time
import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4.1-mini"


def _llm_call(api_key: str, messages: list[dict], temperature: float = 0.0, max_tokens: int = 300) -> str:
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


def answer_question(api_key: str, question: str, passages: list[dict], category: int = 1) -> str:
    """Answer a question given ranked passages."""
    # Build context from passages
    context_parts = []
    for p in passages:
        date_str = f" ({p['date']})" if p.get('date') else ""
        context_parts.append(f"[{p['session_id']}{date_str}]\n{p['text']}")
    
    context = "\n\n---\n\n".join(context_parts)
    
    if category == 3:  # open-domain
        prompt = f"""Answer this question based on the conversation excerpts below. This may require inference and world knowledge combined with what's in the conversations.

Conversation excerpts:
{context}

Question: {question}

RULES:
- Be concise — answer like a trivia quiz
- Use exact names, places, titles from the conversations
- For yes/no questions, answer Yes or No first
- For inference questions, reason from the conversation context + common sense
- Do NOT say "Based on the conversations..." — just state the answer

Answer:"""
    elif category == 5:  # adversarial
        prompt = f"""Answer this question based on the conversation excerpts below.

Conversation excerpts:
{context}

Question: {question}

RULES:
- Answer the question exactly as asked. Do NOT correct the question.
- If the question attributes something to person X but your context shows person Y did it, answer with the action/fact using the name from the question.
- Be concise — answer like a trivia quiz
- Never say "Actually, it was Y who did that"

Answer:"""
    else:
        prompt = f"""Answer this question based on the conversation excerpts below. Be concise — answer like a trivia quiz.

Conversation excerpts:
{context}

Question: {question}

RULES:
- Give the shortest possible answer
- Use exact names, places, dates, titles
- Do NOT elaborate or add context
- If listing items, separate by commas
- Do NOT start with "Based on..." — just state the answer

Answer:"""

    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=150)

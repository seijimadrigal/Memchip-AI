"""Reading-comprehension-style answerer for v23.

Key insight: single-hop answers come from ONE dialogue turn (95% of cases).
Treat it as reading comprehension, not knowledge aggregation.
"""
from __future__ import annotations
import time
import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4.1-mini"


def _llm_call(api_key: str, messages: list[dict], temperature: float = 0.0,
              max_tokens: int = 200) -> str:
    for attempt in range(3):
        try:
            resp = httpx.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                timeout=90,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise


# Reading comprehension prompt — answer from passages, not from world knowledge
SINGLE_HOP_PROMPT = """You are answering a factual question about a conversation between two people.
You are given relevant conversation passages. Answer ONLY from these passages.

RULES:
- Be MAXIMALLY CONCISE — answer like a trivia quiz (2-10 words ideal)
- Use the EXACT words from the passages — do not paraphrase
- If the passage says "sunset", answer "sunset", NOT "a painting of a sunset"
- If asked "how many", give JUST the number
- If asked "who", give JUST the name
- If asked "what does X do", give the specific activity mentioned
- Do NOT list everything you know — only what directly answers this specific question
- Do NOT add context, explanations, or "Based on..."
- If the answer isn't in the passages, say "Not mentioned in the conversations"
- NEVER correct the question or say "Actually, it was Y who..."

PASSAGES:
{context}

QUESTION: {question}

ANSWER:"""


MULTI_HOP_PROMPT = """You are answering a question that may require combining information from multiple conversation passages.

RULES:
- Be CONCISE — answer in as few words as possible
- Use EXACT words from the passages
- Combine information from different passages if needed
- Do NOT add information not in the passages
- NEVER correct the question or say "Actually, it was Y who..."

PASSAGES:
{context}

QUESTION: {question}

ANSWER:"""


TEMPORAL_PROMPT = """You are answering a time-related question about conversations. Each passage is tagged with its session date.

RULES:
- Be CONCISE — dates, durations, or short phrases only
- Convert relative dates to absolute using the session date tags
- If "yesterday" was said in a session on "May 25, 2023", the answer is "May 24, 2023"
- Use EXACT words from passages for non-date answers
- NEVER correct the question

PASSAGES:
{context}

QUESTION: {question}

ANSWER:"""


ADVERSARIAL_PROMPT = """You are answering a question about a conversation. Answer the question EXACTLY as asked.

CRITICAL: Do NOT question the premise. Do NOT say "Actually, it was someone else." 
Just answer the question using the information in the passages, applying it to whoever the question asks about.

RULES:
- Be MAXIMALLY CONCISE
- Use EXACT words from passages
- Answer about the person mentioned in the question, even if the passages attribute the info to someone else
- NEVER say "did not" or "it was actually" — just answer

PASSAGES:
{context}

QUESTION: {question}

ANSWER:"""


OPEN_DOMAIN_PROMPT = """You are answering a question that may require both conversation context and general knowledge.

RULES:
- Be CONCISE
- Use conversation passages for personal facts
- You MAY use general knowledge for factual/world knowledge parts
- Do NOT over-explain

PASSAGES:
{context}

QUESTION: {question}

ANSWER:"""


def format_context(passages: list[dict]) -> str:
    """Format reranked passages as context string."""
    parts = []
    for i, p in enumerate(passages):
        date_tag = f" [Session: {p.get('date', 'unknown')}]" if p.get('date') else ""
        score = f" (relevance: {p.get('rrf_score', 0):.4f})" if 'rrf_score' in p else ""
        parts.append(f"[Passage {i+1}]{date_tag}\n{p['text']}")
    return "\n\n".join(parts)


def answer_question(api_key: str, question: str, passages: list[dict], 
                    category: int = 4) -> str:
    """Answer question using reading comprehension over passages."""
    context = format_context(passages)
    
    prompts = {
        1: MULTI_HOP_PROMPT,
        2: TEMPORAL_PROMPT,
        3: OPEN_DOMAIN_PROMPT,
        4: SINGLE_HOP_PROMPT,
        5: ADVERSARIAL_PROMPT,
    }
    
    prompt_template = prompts.get(category, SINGLE_HOP_PROMPT)
    prompt = prompt_template.format(context=context, question=question)
    
    answer = _llm_call(api_key, [{"role": "user", "content": prompt}])
    
    # Clean up common prefixes
    for prefix in ["Answer:", "A:", "Based on the passages,"]:
        if answer.startswith(prefix):
            answer = answer[len(prefix):].strip()
    
    return answer.strip()

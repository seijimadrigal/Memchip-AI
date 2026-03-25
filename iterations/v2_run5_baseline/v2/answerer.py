from __future__ import annotations
"""Answer generation with strategy-specific prompts."""

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


ANSWER_RULES = """IMPORTANT RULES:
- Answer the question exactly as asked. Do NOT correct the question or point out errors in attribution.
- If the question asks "What did X do?" and your memory shows Y did it, answer with what was done (the action/fact), using the name from the question.
- Never say "Actually, it was Y who did that, not X." Just answer the question directly.
- Be concise and specific — include dates, places, details."""


def answer_strategy_a(api_key: str, question: str, profiles: list[dict]) -> str:
    """Gist recall: profiles only."""
    profile_text = "\n\n".join(f"## {p['entity']}\n{p['profile_text']}" for p in profiles)
    
    prompt = f"""Based on these entity profiles, answer the question concisely and specifically.
If the answer is clearly in the profiles, state it directly.
If the information is NOT in the profiles at all, say "Information not mentioned in profiles."

{ANSWER_RULES}

Profiles:
{profile_text}

Question: {question}

Answer (be specific — include names, dates, places):"""

    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=200)


def answer_strategy_b(api_key: str, question: str, profiles: list[dict], episodes: list[dict]) -> str:
    """Episode recall: profiles + episode summaries."""
    profile_text = "\n\n".join(f"## {p['entity']}\n{p['profile_text']}" for p in profiles)
    episode_text = "\n\n".join(f"### {ep['session_id']} ({ep['date']})\n{ep['summary']}" for ep in episodes)
    
    prompt = f"""Based on the entity profiles and episode summaries below, answer the question.
Use specific details — dates, names, places. Cross-reference profiles and episodes.
If the answer is NOT found in the provided information, say "Information not mentioned."

{ANSWER_RULES}

Entity Profiles:
{profile_text}

Episode Timeline:
{episode_text}

Question: {question}

Answer (specific and concise):"""

    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=300)


def answer_strategy_c(api_key: str, question: str, profiles: list[dict], episodes: list[dict], raw_sessions: list[dict]) -> str:
    """Deep recall: profiles + episodes + targeted raw sessions."""
    profile_text = "\n\n".join(f"## {p['entity']}\n{p['profile_text']}" for p in profiles)
    episode_text = "\n\n".join(f"### {ep['session_id']} ({ep['date']})\n{ep['summary']}" for ep in episodes)
    raw_text = "\n\n".join(f"### {rs['session_id']} ({rs['date']})\n{rs['raw_text']}" for rs in raw_sessions)
    
    prompt = f"""Based on the entity profiles, episode summaries, and raw conversation sessions below, answer the question.
Use specific details from the raw conversations when available.
Pay close attention to exact wording, names, dates, and details.

{ANSWER_RULES}

Entity Profiles:
{profile_text}

Episode Timeline:
{episode_text}

Relevant Raw Sessions:
{raw_text}

Question: {question}

Answer (specific, accurate, concise):"""

    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=300)


def answer_strategy_d(api_key: str, question: str, profiles: list[dict], episodes: list[dict], all_raw: list[dict]) -> str:
    """Full reconstruction: everything."""
    profile_text = "\n\n".join(f"## {p['entity']}\n{p['profile_text']}" for p in profiles)
    episode_text = "\n\n".join(f"### {ep['session_id']} ({ep['date']})\n{ep['summary']}" for ep in episodes)
    raw_text = "\n\n".join(f"### {rs['session_id']} ({rs['date']})\n{rs['raw_text']}" for rs in all_raw)
    
    prompt = f"""Based on ALL available memory below, answer the question thoroughly.
This is a deep search — use every available detail.

{ANSWER_RULES}

Entity Profiles:
{profile_text}

Full Episode Timeline:
{episode_text}

All Raw Sessions:
{raw_text}

Question: {question}

Answer (thorough, specific, accurate):"""

    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=400)


def synthesize_subanswers(api_key: str, question: str, sub_qas: list[tuple[str, str]]) -> str:
    """Synthesize sub-answers into a final answer for multi-hop questions."""
    sub_text = "\n".join(f"Q: {q}\nA: {a}" for q, a in sub_qas)
    
    prompt = f"""Based on these sub-answers, provide a final answer to the original question.

Original Question: {question}

Sub-answers:
{sub_text}

Final Answer (concise and specific):"""

    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=200)


def judge_answer(api_key: str, question: str, prediction: str, ground_truth: str) -> int:
    """LLM-as-judge: does prediction match ground truth? Returns 0 or 1."""
    prompt = f"""Judge if the predicted answer matches the ground truth answer for this question.
The prediction doesn't need to be word-for-word identical, but must convey the same key information.
Be lenient on phrasing but strict on factual content.

Question: {question}
Ground Truth: {ground_truth}
Prediction: {prediction}

Does the prediction match the ground truth? Reply ONLY with 1 (yes) or 0 (no):"""

    result = _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=16)
    return 1 if "1" in result else 0

from __future__ import annotations
"""v19 answer generation — same as v18 but with entity-attributed fact support in prompts."""

import time
import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4.1-mini"


def _llm_call(api_key: str, messages: list[dict], temperature: float = 0.0, max_tokens: int = 300, model: str = None) -> str:
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


def _mask_entities_in_context(question: str, profiles: list[dict], episodes: list[dict],
                               raw_sessions: list[dict] | None = None) -> tuple:
    speakers = [p["entity"] for p in profiles]
    question_lower = question.lower()
    question_entity = None
    other_entity = None
    for s in speakers:
        if s.lower() in question_lower:
            question_entity = s
        else:
            other_entity = s
    if not question_entity or not other_entity:
        return profiles, episodes, raw_sessions
    def mask(text: str) -> str:
        return text.replace(other_entity, question_entity)
    masked_profiles = [{"entity": mask(p["entity"]), "profile_text": mask(p["profile_text"])} for p in profiles]
    masked_episodes = [{"session_id": e["session_id"], "date": e["date"], "summary": mask(e["summary"])} for e in episodes]
    masked_raw = None
    if raw_sessions is not None:
        masked_raw = [{"session_id": r["session_id"], "date": r["date"], "raw_text": mask(r["raw_text"])} for r in raw_sessions]
    return masked_profiles, masked_episodes, masked_raw


ANSWER_RULES = """CRITICAL RULES:
- Answer the question exactly as asked. Do NOT correct the question or point out errors in attribution.
- If the question asks "What did X do?" and your memory shows Y did it, answer with what was done (the action/fact), using the name from the question.
- Never say "Actually, it was Y who did that, not X." Just answer the question directly.
- Be MAXIMALLY CONCISE. Answer like a trivia quiz — shortest possible answer.
- Examples of GOOD answers: "sunset", "3", "Single", "rock climbing, fishing, camping", "July 12, 2023"
- Examples of BAD answers: "A painting inspired by sunsets with calming colors" (just say "sunset"), "Multiple children" (say the number)
- ONLY include facts that DIRECTLY answer the question. Do NOT list extra related facts.
- Do NOT add dates, context, explanations, or background. Just the bare facts.
- Do NOT elaborate or paraphrase. Use the simplest, shortest form.
- If multiple items are asked, list them separated by commas. No numbering, no bullets.
- NEVER start with "Based on the profiles..." or "According to..." — just state the answer.
- "recently" or "latest" = ONLY the SINGLE most recent item.
- For "how many" questions, give the EXACT NUMBER.
- PRECISION over RECALL: only include items you are CONFIDENT about.
- If the question names a SPECIFIC time frame, ONLY include items from that time frame."""


def answer_strategy_a(api_key: str, question: str, profiles: list[dict]) -> str:
    profile_text = "\n\n".join(f"## {p['entity']}\n{p['profile_text']}" for p in profiles)
    prompt = f"""Answer this question using ONLY the profiles below. Give the shortest possible answer.

{ANSWER_RULES}

Profiles:
{profile_text}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=100)


def answer_strategy_b(api_key: str, question: str, profiles: list[dict], episodes: list[dict], temporal_context: str = "") -> str:
    profile_text = "\n\n".join(f"## {p['entity']}\n{p['profile_text']}" for p in profiles)
    episode_text = "\n\n".join(f"### {ep['session_id']} ({ep['date']})\n{ep['summary']}" for ep in episodes)
    temporal_section = f"\n{temporal_context}" if temporal_context else ""
    prompt = f"""Answer this question using the profiles and episode summaries below. Give the shortest possible answer.

{ANSWER_RULES}

Entity Profiles:
{profile_text}

Episode Timeline:
{episode_text}{temporal_section}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=150)


def answer_strategy_c(api_key: str, question: str, profiles: list[dict], episodes: list[dict], raw_sessions: list[dict], temporal_context: str = "") -> str:
    profile_text = "\n\n".join(f"## {p['entity']}\n{p['profile_text']}" for p in profiles)
    episode_text = "\n\n".join(f"### {ep['session_id']} ({ep['date']})\n{ep['summary']}" for ep in episodes)
    compressed_raw = []
    for rs in raw_sessions:
        text = rs['raw_text']
        if len(text) > 3000:
            text = text[:3000] + "\n... [truncated]"
        compressed_raw.append(f"### {rs['session_id']} ({rs['date']})\n{text}")
    raw_text = "\n\n".join(compressed_raw)
    temporal_section = f"\n\nTimeline of Events:\n{temporal_context}" if temporal_context else ""
    prompt = f"""Answer this question using the profiles, episodes, and raw conversations below.

{ANSWER_RULES}

Entity Profiles:
{profile_text}

Episode Timeline:
{episode_text}

Relevant Raw Sessions:
{raw_text}{temporal_section}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=150)


def answer_strategy_d(api_key: str, question: str, profiles: list[dict], episodes: list[dict], all_raw: list[dict]) -> str:
    profile_text = "\n\n".join(f"## {p['entity']}\n{p['profile_text']}" for p in profiles)
    episode_text = "\n\n".join(f"### {ep['session_id']} ({ep['date']})\n{ep['summary']}" for ep in episodes)
    raw_text = "\n\n".join(f"### {rs['session_id']} ({rs['date']})\n{rs['raw_text']}" for rs in all_raw)
    prompt = f"""Based on ALL available memory below, answer the question thoroughly.

{ANSWER_RULES}

Entity Profiles:
{profile_text}

Full Episode Timeline:
{episode_text}

All Raw Sessions:
{raw_text}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=400)


def answer_open_domain(api_key: str, question: str, profiles: list[dict], episodes: list[dict], raw_sessions: list[dict] | None = None, atomic_context: str = "") -> str:
    profile_text = "\n\n".join(f"## {p['entity']}\n{p['profile_text']}" for p in profiles)
    episode_text = "\n\n".join(f"### {ep['session_id']} ({ep['date']})\n{ep['summary']}" for ep in episodes)
    raw_text = ""
    if raw_sessions:
        compressed_raw = []
        for rs in raw_sessions:
            text = rs['raw_text']
            if len(text) > 3000:
                text = text[:3000] + "\n... [truncated]"
            compressed_raw.append(f"### {rs['session_id']} ({rs['date']})\n{text}")
        raw_text = "\n\nRelevant Raw Sessions:\n" + "\n\n".join(compressed_raw)
    atomic_section = atomic_context if atomic_context else ""
    prompt = f"""You are answering a question that requires INFERENCE and REASONING based on what you know about these people, combined with general world knowledge.

Entity Profiles:
{profile_text}

Episode Timeline:
{episode_text}{raw_text}{atomic_section}

Question: {question}

REASONING APPROACH:
1. Identify relevant facts from the conversations
2. Apply common sense and world knowledge
3. Give a direct, concise answer (1-2 sentences max)

For "would X...?" questions: Answer Yes or No first, then briefly explain.
For "what could X...?" questions: Give the most logical answer based on their profile.

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=300)


def synthesize_subanswers(api_key: str, question: str, sub_qas: list[tuple[str, str]]) -> str:
    sub_text = "\n".join(f"Q: {q}\nA: {a}" for q, a in sub_qas)
    prompt = f"""Based on these sub-answers, provide a final answer to the original question.

Original Question: {question}

Sub-answers:
{sub_text}

Final Answer (concise and specific):"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=200)


def judge_answer(api_key: str, question: str, prediction: str, ground_truth: str) -> int:
    prompt = f"""Judge if the predicted answer matches the ground truth answer for this question.
The prediction doesn't need to be word-for-word identical, but must convey the same key information.
Be lenient on phrasing but strict on factual content.

Question: {question}
Ground Truth: {ground_truth}
Prediction: {prediction}

Does the prediction match the ground truth? Reply ONLY with 1 (yes) or 0 (no):"""
    result = _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=16)
    return 1 if "1" in result else 0

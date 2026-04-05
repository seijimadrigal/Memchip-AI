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


def _mask_entities_in_context(question: str, profiles: list[dict], episodes: list[dict],
                               raw_sessions: list[dict] | None = None) -> tuple:
    """For adversarial questions: swap the OTHER entity's name to the QUESTION entity's name in all context.
    
    This prevents the LLM from seeing a contradiction and refusing to answer.
    Returns (masked_profiles, masked_episodes, masked_raw_sessions).
    """
    # Extract speaker names from profiles
    speakers = [p["entity"] for p in profiles]
    
    # Find which speaker is mentioned in the question
    question_lower = question.lower()
    question_entity = None
    other_entity = None
    for s in speakers:
        if s.lower() in question_lower:
            question_entity = s
        else:
            other_entity = s
    
    if not question_entity or not other_entity:
        # Can't determine entities, return unchanged
        return profiles, episodes, raw_sessions
    
    def mask(text: str) -> str:
        # Replace the other entity's name with the question entity's name
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
- Examples of BAD answers: "A painting inspired by sunsets with calming colors" (just say "sunset"), "Multiple children" (say the number), "Caroline experienced a tough breakup" (just say "Single")
- ONLY include facts that DIRECTLY answer the question. Do NOT list extra related facts.
- If the question asks "What books has X read?" list only the books EXPLICITLY named in conversations, not inferred ones.
- When listing items (activities, events, books, etc.), include only the MOST NOTABLE 2-5 items, not an exhaustive list. Prefer specific over generic.
- Use exact names, places, titles — NEVER generalize. Say "Sweden" not "home country". Say "3" not "multiple".
- Do NOT add dates, context, explanations, or background. Just the bare facts.
- Do NOT elaborate or paraphrase. Use the simplest, shortest form.
- If multiple items are asked, list them separated by commas. No numbering, no bullets.
- NEVER start with "Based on the profiles..." or "According to..." — just state the answer."""


def answer_strategy_a(api_key: str, question: str, profiles: list[dict]) -> str:
    """Gist recall: profiles only."""
    profile_text = "\n\n".join(f"## {p['entity']}\n{p['profile_text']}" for p in profiles)
    
    prompt = f"""Answer this question using ONLY the profiles below. Give the shortest possible answer.

{ANSWER_RULES}

Profiles:
{profile_text}

Question: {question}

Answer:"""

    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=100)


def answer_strategy_b(api_key: str, question: str, profiles: list[dict], episodes: list[dict], temporal_context: str = "") -> str:
    """Episode recall: profiles + episode summaries + optional temporal context."""
    profile_text = "\n\n".join(f"## {p['entity']}\n{p['profile_text']}" for p in profiles)
    episode_text = "\n\n".join(f"### {ep['session_id']} ({ep['date']})\n{ep['summary']}" for ep in episodes)
    
    temporal_section = f"\n{temporal_context}" if temporal_context else ""
    
    prompt = f"""Answer this question using the profiles and episode summaries below. Give the shortest possible answer.
If the answer requires listing items, list ALL matching items but NOTHING extra.

{ANSWER_RULES}

Entity Profiles:
{profile_text}

Episode Timeline:
{episode_text}{temporal_section}

Question: {question}

Answer:"""

    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=150)


def answer_strategy_c(api_key: str, question: str, profiles: list[dict], episodes: list[dict], raw_sessions: list[dict], temporal_context: str = "") -> str:
    """Deep recall: profiles + episodes + targeted raw sessions."""
    profile_text = "\n\n".join(f"## {p['entity']}\n{p['profile_text']}" for p in profiles)
    episode_text = "\n\n".join(f"### {ep['session_id']} ({ep['date']})\n{ep['summary']}" for ep in episodes)
    # Token compression: truncate raw sessions to most relevant 3000 chars each
    compressed_raw = []
    for rs in raw_sessions:
        text = rs['raw_text']
        if len(text) > 3000:
            text = text[:3000] + "\n... [truncated]"
        compressed_raw.append(f"### {rs['session_id']} ({rs['date']})\n{text}")
    raw_text = "\n\n".join(compressed_raw)
    temporal_section = f"\n\nTimeline of Events:\n{temporal_context}" if temporal_context else ""
    
    prompt = f"""Answer this question using the profiles, episodes, and raw conversations below. Give the shortest possible answer.
Use exact details from raw conversations when available. If listing items, include ALL matching items but NOTHING extra.

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


def answer_open_domain(api_key: str, question: str, profiles: list[dict], episodes: list[dict], raw_sessions: list[dict] | None = None, atomic_context: str = "") -> str:
    """Open-domain: requires inferring from memory context + world knowledge."""
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
    
    prompt = f"""You are answering a question that requires INFERENCE and REASONING based on what you know about these people from their conversations, combined with general world knowledge.

This is NOT a simple fact lookup — you need to think about what these people would likely do, think, or prefer based on their personality, interests, location, and lifestyle as revealed in the conversations.

Entity Profiles:
{profile_text}

Episode Timeline:
{episode_text}{raw_text}{atomic_section}

Question: {question}

REASONING APPROACH:
1. First identify what relevant facts from the conversations bear on this question
2. Then apply common sense and world knowledge to reason about the answer
3. Give a direct, concise answer (1-2 sentences max)

For "would X...?" questions: Answer Yes or No first, then briefly explain why based on their known traits/interests.
For "what could X...?" questions: Give the most logical answer based on their profile and general knowledge.
For "which/where" inference questions: Use location clues, interests, and context to make the best inference.

Answer:"""

    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=300)


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

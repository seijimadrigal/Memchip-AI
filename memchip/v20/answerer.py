from __future__ import annotations
"""v20 answerer: EverMemOS-style Chain-of-Thought answering with episode narratives."""

import time
import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
ANSWER_MODEL = "openai/gpt-4.1-mini"  # Same as EverMemOS


def _llm_call(api_key: str, messages: list[dict], temperature: float = 0.0,
              max_tokens: int = 2000, model: str = None) -> str:
    use_model = model or ANSWER_MODEL
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


COT_ANSWER_PROMPT = """You are an intelligent memory assistant tasked with retrieving accurate information from episodic memories.

# CONTEXT:
You have access to episodic memories from conversations between {speakers}. These memories contain
timestamped information that may be relevant to answering the question.

# INSTRUCTIONS:
Synthesize information from all relevant memories to provide a comprehensive and accurate answer.
Follow a structured Chain-of-Thought process to ensure no details are missed.
Actively look for connections between people, places, and events.
Perform logical inference — when evidence strongly suggests a connection, state it.

# CRITICAL REQUIREMENTS:
1. NEVER omit specific names - use "Amy's colleague Rob" not "a colleague"
2. ALWAYS include exact numbers, amounts, prices, percentages, dates, times
3. PRESERVE frequencies exactly - "every Tuesday and Thursday" not "twice a week"
4. MAINTAIN all proper nouns and entities as they appear

# RESPONSE FORMAT:

## STEP 1: RELEVANT MEMORIES
[List each memory that relates to the question]

## STEP 2: KEY DETAILS
- Names: [all person/place/entity names]
- Numbers: [all quantities, counts, dates]
- Connections: [facts that span multiple memories]

## STEP 3: CROSS-MEMORY LINKING
[Combine information across memories. Make reasonable inferences.]

## STEP 4: TIME CALCULATION
[If applicable, resolve relative time references to absolute dates]

## STEP 5: DETAIL CHECK
- All names included?
- All numbers exact?
- All dates precise?

## FINAL ANSWER:
[Concise answer with ALL specific details preserved. Be brief but complete.]

---

{context}

Question: {question}

Follow the Chain-of-Thought process above:
"""


def _format_episodes_as_context(episodes: list[dict], speakers: list[str]) -> str:
    """Format episodes into context string (EverMemOS style)."""
    speaker_str = " and ".join(speakers) if speakers else "the speakers"
    
    memories = []
    for ep in episodes:
        summary = ep.get("summary", "")
        date = ep.get("date", "")
        memories.append(f"{summary}\n---")
    
    speaker_memories = "\n\n".join(memories)
    return f"Episodes memories for conversation between {speaker_str}:\n\n{speaker_memories}"


def answer_from_episodes(api_key: str, question: str, episodes: list[dict],
                          speakers: list[str]) -> str:
    """Answer using episode narratives with Chain-of-Thought prompt + conciseness post-processing."""
    context = _format_episodes_as_context(episodes, speakers)
    speaker_str = " and ".join(speakers) if speakers else "the speakers"
    
    prompt = COT_ANSWER_PROMPT.format(
        speakers=speaker_str,
        context=context,
        question=question,
    )
    
    messages = [{"role": "user", "content": prompt}]
    result = _llm_call(api_key, messages, max_tokens=1500)
    
    # Extract FINAL ANSWER
    raw_answer = result.strip()
    if "FINAL ANSWER:" in result:
        parts = result.split("FINAL ANSWER:")
        if len(parts) > 1:
            raw_answer = parts[1].strip()
    
    # Post-process: condense to shortest possible answer
    return _condense_answer(api_key, question, raw_answer)


def _condense_answer(api_key: str, question: str, verbose_answer: str) -> str:
    """Post-process: condense a verbose CoT answer into the shortest possible form."""
    prompt = f"""Condense this answer to the SHORTEST possible form. Like a trivia quiz answer.

Rules:
- ONLY the core facts that directly answer the question
- No explanations, no context, no background
- Use comma separation for lists. No bullets.
- Numbers only for "how many". Dates only for "when".
- Never start with the person's name restating the question
- Examples: "sunset", "3", "Single", "rock climbing, fishing", "July 12, 2023", "Yes"

Question: {question}
Verbose Answer: {verbose_answer}

Concise Answer:"""
    
    messages = [{"role": "user", "content": prompt}]
    return _llm_call(api_key, messages, max_tokens=100, model="openai/gpt-4.1-mini").strip()


def answer_temporal(api_key: str, question: str, relevant_episodes: list[dict],
                     all_episodes: list[dict], temporal_events: list[dict],
                     speakers: list[str]) -> str:
    """Answer temporal questions with episodes + timeline."""
    context = _format_episodes_as_context(relevant_episodes, speakers)
    
    # Add timeline
    if temporal_events:
        timeline = "\n".join(f"- {ev['date']}: {ev['entity']} — {ev['event_text']}" 
                             for ev in temporal_events)
        context += f"\n\nTimeline of Events:\n{timeline}"
    
    # Add full episode timeline as additional context
    if all_episodes and len(all_episodes) > len(relevant_episodes):
        ep_timeline = "\n".join(f"- {ep['date']}: {ep['summary'][:200]}" for ep in all_episodes)
        context += f"\n\nFull Episode Timeline:\n{ep_timeline}"
    
    speaker_str = " and ".join(speakers) if speakers else "the speakers"
    prompt = COT_ANSWER_PROMPT.format(
        speakers=speaker_str,
        context=context,
        question=question,
    )
    
    messages = [{"role": "user", "content": prompt}]
    result = _llm_call(api_key, messages, max_tokens=1500)
    
    raw_answer = result.strip()
    if "FINAL ANSWER:" in result:
        parts = result.split("FINAL ANSWER:")
        if len(parts) > 1:
            raw_answer = parts[1].strip()
    
    return _condense_answer(api_key, question, raw_answer)


def answer_adversarial(api_key: str, question: str, episodes: list[dict],
                        speakers: list[str]) -> str:
    """Answer adversarial questions with entity masking."""
    question_lower = question.lower()
    question_entity = None
    other_entity = None
    for s in speakers:
        if s.lower() in question_lower:
            question_entity = s
        else:
            other_entity = s
    
    # Mask other entity
    def mask(text: str) -> str:
        if question_entity and other_entity:
            return text.replace(other_entity, question_entity)
        return text
    
    masked_episodes = [
        {**ep, "summary": mask(ep.get("summary", "")), "date": ep.get("date", "")}
        for ep in episodes
    ]
    
    context = _format_episodes_as_context(masked_episodes, speakers)
    speaker_str = " and ".join(speakers) if speakers else "the speakers"
    
    prompt = COT_ANSWER_PROMPT.format(
        speakers=speaker_str,
        context=context,
        question=question,
    )
    
    messages = [{"role": "user", "content": prompt}]
    result = _llm_call(api_key, messages, max_tokens=1500)
    
    raw_answer = result.strip()
    if "FINAL ANSWER:" in result:
        parts = result.split("FINAL ANSWER:")
        if len(parts) > 1:
            raw_answer = parts[1].strip()
    
    return _condense_answer(api_key, question, raw_answer)


def synthesize_subanswers(api_key: str, question: str,
                           sub_qas: list[tuple[str, str]]) -> str:
    """Synthesize sub-question answers into a final answer."""
    sqa_text = "\n".join(f"Q: {sq}\nA: {sa}" for sq, sa in sub_qas)
    
    prompt = f"""Combine these sub-answers to answer the main question.
Be concise but include ALL specific details.

Main Question: {question}

Sub-answers:
{sqa_text}

FINAL ANSWER:"""

    messages = [{"role": "user", "content": prompt}]
    return _llm_call(api_key, messages, max_tokens=200).strip()


def judge_answer(prediction: str, ground_truth: str, api_key: str = None) -> int:
    """Judge if prediction matches ground truth using LLM."""
    if not prediction or not ground_truth:
        return 0
    
    pred_lower = prediction.lower().strip()
    gt_lower = str(ground_truth).lower().strip()
    
    if pred_lower == gt_lower:
        return 1
    
    if api_key:
        return _llm_judge(prediction, ground_truth, api_key)
    
    if len(gt_lower) < 100 and gt_lower in pred_lower:
        return 1
    
    return 0


def _llm_judge(prediction: str, ground_truth: str, api_key: str) -> int:
    """Use LLM to judge answer correctness (same as v19)."""
    prompt = f"""Judge if the predicted answer matches the ground truth answer.
The prediction doesn't need to be word-for-word identical, but must convey the same key information.
Be lenient on phrasing but strict on factual content.

Ground Truth: {ground_truth}
Prediction: {prediction}

Does the prediction match the ground truth? Reply ONLY with 1 (yes) or 0 (no):"""

    messages = [{"role": "user", "content": prompt}]
    try:
        result = _llm_call(api_key, messages, max_tokens=16, model="openai/gpt-4.1-mini")
        return 1 if "1" in result else 0
    except:
        return 0

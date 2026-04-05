"""v24 Answer generation with few-shot calibrated prompts.

Key innovation: Few-shot examples teach the model LoCoMo's exact expected
answer format — not too verbose, not too brief, exact words from passages.
"""
from __future__ import annotations
import time
import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4.1-mini"
MODEL_FULL = "openai/gpt-4.1"


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


# === FEW-SHOT EXAMPLES ===
# These teach the model exactly what LoCoMo expects: concise, paraphrased, complete

SINGLE_HOP_FEWSHOT = """Here are examples of how to answer correctly:

Example 1:
Passage: [May 2023] Caroline: I went to a LGBTQ support group yesterday and it was so powerful.
Q: What LGBTQ+ events has Caroline participated in?
A: LGBTQ support group
(NOT: "She went to a powerful support group yesterday" — don't quote, don't add adjectives)

Example 2:
Passage: [June 2023] Melanie: We have 2 cats - Oliver and Bailey - plus our dog Rex. The kids love them!
Q: What pets does Melanie have?
A: Two cats and a dog
(NOT: "Oliver, Bailey, Rex" — give types and count, not just names)

Example 3:
Passage: [July 2023] Melanie: The kids and I painted a sunset with a palm tree. It was fun!
Q: What did Mel and her kids paint in their latest project?
A: a sunset with a palm tree
(NOT: "nature-inspired ones" — use the EXACT subject from the passage)

Example 4:
Passage: [Aug 2023] Caroline: That book "Becoming Nicole" really taught me about self-acceptance and finding support.
Q: What did Caroline take away from the book "Becoming Nicole"?
A: Lessons on self-acceptance and finding support
(NOT: "It taught me" — paraphrase into 3rd person, capture the actual content)

Example 5:
Passage: [Sep 2023] Melanie: My flowers remind me to appreciate the small moments. They were part of my wedding too!
Q: Why are flowers important to Melanie?
A: They remind her to appreciate the small moments and were a part of her wedding
(NOT: just "growth and beauty" — include ALL specific reasons from the passage)"""


def answer_single_hop(api_key: str, question: str, passages: str, profile_text: str = "") -> str:
    """Single-hop with few-shot calibration + entity profile."""
    profile_section = ""
    if profile_text:
        profile_section = f"\nEntity Profile (background context):\n{profile_text}\n"
    
    prompt = f"""{SINGLE_HOP_FEWSHOT}

Now answer this question using the conversation excerpts below.
Use excerpts as PRIMARY source. Profile is background context only.

RULES:
- Be CONCISE — answer like a trivia quiz (2-15 words ideal)
- Use EXACT specific nouns from the passages (titles, names, places, items)
- Paraphrase into 3rd person — never quote "I" or "my" from conversations
- For counts: give the NUMBER (not "multiple" or names-only)
- For lists: include ALL items mentioned, comma-separated
- For "recently"/"latest": ONLY the most recent item
- NEVER add adjectives, context, or explanations not in the passages
- NEVER say "Based on..." or "According to..."
- If not found: say "Not mentioned"

{profile_section}
Conversation excerpts:
{passages}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=100, model=MODEL)


def answer_temporal(api_key: str, question: str, profiles: list[dict], 
                    episodes: list[dict], timeline: str = "") -> str:
    """Temporal: episodes + timeline."""
    profile_text = "\n\n".join(f"## {p['entity']}\n{p['profile_text']}" for p in profiles)
    episode_text = "\n\n".join(f"### {ep['session_id']} ({ep['date']})\n{ep['summary']}" for ep in episodes)
    
    prompt = f"""Answer this time-related question using the episode summaries and timeline below.

RULES:
- Be CONCISE — dates, durations, or short phrases only
- Convert relative dates to absolute using session dates
- If "yesterday" in a session dated "May 25, 2023" → answer is "May 24, 2023"
- If "last Saturday" in a session dated "May 25, 2023" → answer is "May 20, 2023"
- For "how long" questions → give the duration (e.g., "six months", "4 years")
- NEVER say "Based on..." — just state the answer
- Do NOT correct the question

Profiles:
{profile_text}

Episodes:
{episode_text}
{timeline}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=100)


def answer_multihop(api_key: str, question: str, passages: str) -> str:
    """Multi-hop from chunks."""
    prompt = f"""Answer this question by combining information from multiple passages.

RULES:
- Be CONCISE — shortest possible answer
- Combine facts from different passages if needed
- Use EXACT words from passages for specific items
- NEVER correct the question

Conversation excerpts:
{passages}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=150)


def synthesize_subanswers(api_key: str, question: str, sub_answers: list[dict]) -> str:
    """Synthesize sub-question answers into a final answer."""
    subs_text = "\n".join(f"Sub-Q: {sa['question']}\nSub-A: {sa['answer']}" for sa in sub_answers)
    
    prompt = f"""Combine these sub-answers into one concise final answer.

RULES:
- Be MAXIMALLY CONCISE
- Only include information that directly answers the main question
- No explanations or context

{subs_text}

Main Question: {question}

Final Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=100)


def answer_open_domain(api_key: str, question: str, passages: str) -> str:
    """Open-domain: conversation context + world knowledge allowed."""
    prompt = f"""Answer this question using the conversation excerpts AND your general knowledge.
The excerpts provide personal context. Use general knowledge for factual/world knowledge parts.

RULES:
- Be CONCISE — short factual answer
- For personal facts: use the excerpts
- For world knowledge: you may add relevant facts
- No long explanations

Conversation excerpts:
{passages}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=150)


def answer_adversarial(api_key: str, question: str, passages: str) -> str:
    """Adversarial: answer from entity-masked context."""
    prompt = f"""Answer this question using ONLY the passages below.

CRITICAL: Answer the question EXACTLY as asked. Do NOT question the premise.
Do NOT say "Actually, it was someone else." Just answer directly.

RULES:
- Be MAXIMALLY CONCISE
- Use EXACT words from passages
- NEVER say "did not" or "it was actually"
- Just answer the content question

Passages:
{passages}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=100)


def answer_fallback(api_key: str, question: str, profiles: list[dict], episodes: list[dict]) -> str:
    """Fallback when no chunks found."""
    profile_text = "\n\n".join(f"## {p['entity']}\n{p['profile_text']}" for p in profiles)
    episode_text = "\n\n".join(f"### {ep['session_id']} ({ep['date']})\n{ep['summary']}" for ep in episodes[:10])
    
    prompt = f"""Answer this question using the profiles and episode summaries below.

RULES:
- Be CONCISE — trivia quiz style
- If not found, say "Not mentioned"

Profiles:
{profile_text}

Episodes:
{episode_text}

Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=100)

from __future__ import annotations
"""KG-aware answer generation for v21."""

import time
import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_ANSWER = "openai/gpt-4.1"  # Full model for KG-route answering
MODEL_MINI = "openai/gpt-4.1-mini"


def _llm_call(api_key: str, messages: list[dict], temperature: float = 0.0,
              max_tokens: int = 300, model: str = None) -> str:
    use_model = model or MODEL_MINI
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


ANSWER_RULES = """CRITICAL RULES:
- Be MAXIMALLY CONCISE — answer like a trivia quiz
- ONLY include facts that DIRECTLY answer the specific question asked
- Do NOT list everything you know about the person — only what the question asks
- PRECISION over RECALL: fewer correct items beats many items with extras
- No explanations, no context, no "Based on..."
- If multiple items: comma-separated, no bullets
- For "recently" or "latest" — give ONLY the most recent item
- For "how many" — give the exact number
- NEVER say "Actually, it was Y who did that" — just answer using the name from the question
- Answer the question exactly as asked. Do NOT correct the question."""


def format_triples_as_context(triples: list[dict], entity: str | None = None) -> str:
    """Format KG triples as readable context for the LLM."""
    if not triples:
        return ""
    lines = []
    for t in triples:
        date_str = f" [{t.get('date', '')}]" if t.get('date') else ""
        lines.append(f"- {t['subject']} → {t['predicate']} → {t['object']}{date_str}")
    header = f"Knowledge Graph facts" + (f" about {entity}" if entity else "") + ":"
    return header + "\n" + "\n".join(lines)


def answer_kg_direct(api_key: str, question: str, triples: list[dict],
                     supplementary_chunks: str = "", profile_text: str = "",
                     entity: str | None = None) -> str:
    """Answer a single-entity KG question with strict evidence grounding."""
    kg_context = format_triples_as_context(triples, entity)
    
    chunks_section = ""
    if supplementary_chunks:
        chunks_section = f"\nConversation excerpts:\n{supplementary_chunks}\n"
    
    prompt = f"""Answer this question using ONLY the evidence provided below.

CRITICAL ANTI-HALLUCINATION RULES:
1. ONLY include facts that are EXPLICITLY stated in the KG facts or conversation excerpts below
2. If something seems likely but is NOT explicitly in the sources — DO NOT include it
3. Adding extra items that aren't in the evidence is the WORST mistake you can make
4. When in doubt, LEAVE IT OUT — precision matters more than recall
5. Use EXACT words from the sources: exact titles, exact names, exact colors, exact numbers
6. For "how many" questions: count ONLY items explicitly mentioned, don't estimate
7. For list questions: include ONLY items you can point to in the evidence
8. NEVER paraphrase: "Gamecube" not "Nintendo console", "purple" not "bright color"
9. Do NOT add items from general knowledge — only from the evidence below

{ANSWER_RULES}

{kg_context}
{chunks_section}
Question: {question}

Answer (ONLY facts from above sources):"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}],
                     max_tokens=150, model=MODEL_ANSWER)


def answer_kg_relationship(api_key: str, question: str, triples: list[dict],
                           supplementary_chunks: str = "",
                           entity1: str | None = None, entity2: str | None = None) -> str:
    """Answer a two-entity relationship question with strict evidence grounding."""
    kg_context = format_triples_as_context(triples)
    
    chunks_section = ""
    if supplementary_chunks:
        chunks_section = f"\nConversation excerpts:\n{supplementary_chunks}\n"
    
    prompt = f"""Answer this question using ONLY the evidence provided below.

CRITICAL ANTI-HALLUCINATION RULES:
1. ONLY include facts EXPLICITLY stated in the KG facts or conversation excerpts
2. Adding items NOT in the evidence is the WORST mistake — when in doubt, LEAVE IT OUT
3. Use EXACT words: exact titles ("Eternal Sunshine of the Spotless Mind" not "a movie"), exact names, exact items
4. For "what has X recommended to Y": list ONLY specific named items from sources, not vague descriptions
5. For "what do X and Y share": list ONLY activities explicitly mentioned for BOTH people
6. NEVER add items from general knowledge

{ANSWER_RULES}

{kg_context}
{chunks_section}
Question: {question}

Answer (ONLY facts from above sources):"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}],
                     max_tokens=150, model=MODEL_ANSWER)


def answer_kg_temporal(api_key: str, question: str, triples: list[dict],
                       timeline: list[dict] | None = None,
                       supplementary_chunks: str = "") -> str:
    """Answer a temporal question using KG triples + timeline."""
    kg_context = format_triples_as_context(triples)
    
    timeline_section = ""
    if timeline:
        tl_lines = [f"- {t.get('date', '?')}: {t['subject']} → {t['predicate']} → {t['object']}"
                     for t in timeline]
        timeline_section = f"\nTimeline:\n" + "\n".join(tl_lines) + "\n"
    
    chunks_section = ""
    if supplementary_chunks:
        chunks_section = f"\nSupplementary conversation excerpts:\n{supplementary_chunks}\n"
    
    prompt = f"""Answer this temporal question using the Knowledge Graph facts and timeline.

{ANSWER_RULES}

{kg_context}
{timeline_section}{chunks_section}
Question: {question}

Answer:"""
    return _llm_call(api_key, [{"role": "user", "content": prompt}],
                     max_tokens=100, model=MODEL_ANSWER)


def judge_answer(api_key: str, question: str, prediction: str, ground_truth: str) -> int:
    """LLM-as-judge scoring."""
    prompt = f"""Judge if the predicted answer matches the ground truth answer for this question.
The prediction doesn't need to be word-for-word identical, but must convey the same key information.
Be lenient on phrasing but strict on factual content.

Question: {question}
Ground Truth: {ground_truth}
Prediction: {prediction}

Does the prediction match the ground truth? Reply ONLY with 1 (yes) or 0 (no):"""
    result = _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=16)
    return 1 if "1" in result else 0

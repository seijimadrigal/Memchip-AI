from __future__ import annotations
"""v20 agentic: Multi-round retrieval with LLM sufficiency checking."""

import json
import re
import time
import httpx
from .retriever import hybrid_retrieve, rrf_fusion, rerank
from .storage import Storage

API_URL = "https://openrouter.ai/api/v1/chat/completions"
JUDGE_MODEL = "openai/gpt-4.1-mini"  # Mini is fine for judging sufficiency


def _llm_call(api_key: str, messages: list[dict], temperature: float = 0.0,
              max_tokens: int = 500, model: str = None) -> str:
    use_model = model or JUDGE_MODEL
    for attempt in range(3):
        try:
            resp = httpx.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": use_model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise


def check_sufficiency(api_key: str, question: str, facts: list[dict]) -> dict:
    """Ask LLM if the retrieved facts are sufficient to answer the question.
    
    Returns: {"is_sufficient": bool, "reasoning": str, "missing_info": [str]}
    """
    facts_text = "\n".join(f"- {f['fact_text']}" for f in facts[:10])
    
    prompt = f"""Given these retrieved facts, determine if they are SUFFICIENT to answer the question.

Question: {question}

Retrieved Facts:
{facts_text}

Analyze:
1. Does the answer exist in these facts?
2. What specific information is missing?

Output STRICT JSON:
{{"is_sufficient": true/false, "reasoning": "brief explanation", "missing_info": ["what's missing"]}}"""

    messages = [{"role": "user", "content": prompt}]
    result = _llm_call(api_key, messages, max_tokens=300)
    
    try:
        result = result.strip()
        start = result.find("{")
        end = result.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(result[start:end])
            return {
                "is_sufficient": parsed.get("is_sufficient", True),
                "reasoning": parsed.get("reasoning", ""),
                "missing_info": parsed.get("missing_info", []),
            }
    except:
        pass
    
    # Conservative fallback: assume sufficient
    return {"is_sufficient": True, "reasoning": "Parse error, assuming sufficient", "missing_info": []}


def generate_refined_queries(api_key: str, original_query: str,
                              facts: list[dict], missing_info: list[str]) -> list[str]:
    """Generate 2-3 refined queries to find missing information.
    
    Uses HyDE (Hypothetical Document Embedding) style — one query as question,
    one as hypothetical answer statement.
    """
    facts_text = "\n".join(f"- {f['fact_text']}" for f in facts[:5])
    missing_str = ", ".join(missing_info) if missing_info else "specific details"
    
    prompt = f"""Generate 2-3 alternative search queries to find missing information.

Original Question: {original_query}

Already Found:
{facts_text}

Still Missing: {missing_str}

Requirements:
1. Query 1: Rephrase the original question to target missing info
2. Query 2: A hypothetical answer statement (HyDE style) — write what the answer WOULD look like
3. Query 3 (optional): Target a specific missing detail

Keep queries under 25 words each.

Output STRICT JSON:
{{"queries": ["query1", "query2", "query3"]}}"""

    messages = [{"role": "user", "content": prompt}]
    result = _llm_call(api_key, messages, max_tokens=200, model=JUDGE_MODEL)
    
    try:
        result = result.strip()
        start = result.find("{")
        end = result.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(result[start:end])
            queries = parsed.get("queries", [])
            # Filter valid queries
            valid = [q for q in queries if isinstance(q, str) and 5 <= len(q) <= 200]
            if valid:
                return valid[:3]
    except:
        pass
    
    return [original_query]  # Fallback to original


def agentic_retrieve(api_key: str, question: str, storage: Storage,
                      entity: str | None = None) -> tuple[list[dict], dict]:
    """Multi-round agentic retrieval.
    
    Round 1: Hybrid search → top 20 → check sufficiency on top 10
    If sufficient: return top 20
    If insufficient: generate refined queries → Round 2 → merge → rerank
    
    Returns: (final_facts, metadata)
    """
    metadata = {
        "is_multi_round": False,
        "round1_count": 0,
        "round2_count": 0,
        "is_sufficient": None,
        "refined_queries": None,
    }
    
    # Round 1: Standard hybrid retrieval
    round1 = hybrid_retrieve(question, storage, entity=entity, rerank_top_n=20)
    metadata["round1_count"] = len(round1)
    
    if not round1:
        return [], metadata
    
    # Check sufficiency on top 10
    top10 = round1[:10]
    check = check_sufficiency(api_key, question, top10)
    metadata["is_sufficient"] = check["is_sufficient"]
    
    if check["is_sufficient"]:
        return round1, metadata
    
    # Round 2: Generate refined queries and retrieve again
    metadata["is_multi_round"] = True
    
    refined_queries = generate_refined_queries(
        api_key, question, top10, check["missing_info"]
    )
    metadata["refined_queries"] = refined_queries
    
    # Run hybrid retrieval for each refined query
    all_round2_results = []
    for rq in refined_queries:
        r2 = hybrid_retrieve(rq, storage, entity=entity, rerank_top_n=20)
        all_round2_results.append(r2)
    
    # Multi-RRF fusion of round 2 results
    if all_round2_results:
        round2_fused = rrf_fusion(all_round2_results)
    else:
        round2_fused = []
    
    metadata["round2_count"] = len(round2_fused)
    
    # Merge Round 1 + Round 2 (deduplicate by fact_id)
    seen_ids = {f["fact_id"] for f in round1}
    round2_unique = [f for f in round2_fused if f["fact_id"] not in seen_ids]
    
    combined = round1 + round2_unique[:20]  # Cap at 40 total
    
    # Final rerank on combined results
    if len(combined) > 20:
        final = rerank(question, combined, top_n=20)
    else:
        final = combined
    
    return final, metadata

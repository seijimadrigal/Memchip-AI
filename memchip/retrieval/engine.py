"""
Multi-stage retrieval engine.

Stage 1: Hybrid search (BM25 + vector + graph), fused with RRF
Stage 2: Agentic multi-round (if confidence < threshold, rephrase and re-search)
Stage 3: Reranking (cross-encoder or LLM-based)
Stage 4: Context assembly (pack into token budget)

Inspired by EverMemOS's agentic retrieval but with explicit temporal reasoning.
"""

from __future__ import annotations

import json
import re
import numpy as np
from typing import Optional, List, Dict, Any, Tuple

from memchip.llm import call_llm
from memchip.retrieval.prompts import (
    SUFFICIENCY_CHECK_PROMPT,
    MULTI_QUERY_PROMPT,
    ANSWER_PROMPT,
)


class RetrievalEngine:
    def __init__(
        self,
        store,
        embedding_model: str = "all-MiniLM-L6-v2",
        llm_provider: str = "openai",
        llm_model: str = "gpt-4.1-mini",
        api_key: Optional[str] = None,
    ):
        self.store = store
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.api_key = api_key
        self._embedder = None
        self._embedding_model_name = embedding_model

    @property
    def embedder(self):
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(self._embedding_model_name)
            except ImportError:
                self._embedder = None
        return self._embedder

    def recall(
        self,
        query: str,
        user_id: str,
        top_k: int = 10,
        max_tokens: int = 1500,
        agentic: bool = True,
    ) -> Dict[str, Any]:
        """Multi-stage retrieval pipeline."""

        # Stage 1: Hybrid search
        candidates = self._hybrid_search(query, user_id, top_k=top_k * 3)

        # Stage 2: Agentic multi-round (if enabled)
        if agentic and candidates:
            candidates = self._agentic_retrieval(query, candidates, user_id, top_k)

        # Stage 3: Rerank
        ranked = self._rerank(query, candidates, top_k=top_k)

        # Stage 4: Assemble context
        context = self._assemble_context(ranked, max_tokens=max_tokens)

        return {
            "memories": ranked,
            "context": context,
            "num_candidates": len(candidates),
            "num_returned": len(ranked),
        }

    def _hybrid_search(self, query: str, user_id: str, top_k: int = 30) -> List[Dict]:
        """
        Hybrid retrieval combining:
        1. BM25 full-text search (via FTS5)
        2. Entity-based graph walk
        3. Profile attribute search
        4. Temporal event search
        """
        results = {}  # content -> {score, source, ...}

        # 1. BM25 search
        fts_results = self.store.search_fts(query, user_id, limit=top_k)
        for i, r in enumerate(fts_results):
            key = r["content"]
            results[key] = {
                "content": key,
                "type": r["memory_type"],
                "bm25_rank": i + 1,
                "sources": ["bm25"],
            }

        # 2. Entity-based graph walk
        # Extract entity names from query
        entities = self._extract_query_entities(query)
        for entity in entities:
            # Direct triple lookup
            triples = self.store.get_triples(user_id, subject=entity)
            for t in triples:
                content = f"{t['subject']} {t['predicate']} {t['object']}"
                if content not in results:
                    results[content] = {"content": content, "type": "triple", "sources": []}
                results[content]["sources"].append("graph")
                results[content]["triple"] = t

            # Graph walk (2-hop)
            graph_results = self.store.graph_walk(user_id, entity, hops=2)
            for g in graph_results:
                content = f"{g['source_entity']} {g['relation']} {g['target_entity']}"
                if content not in results:
                    results[content] = {"content": content, "type": "relation", "sources": []}
                results[content]["sources"].append(f"graph_hop{g['hop']}")

        # 3. Profile search
        for entity in entities:
            profiles = self.store.get_profile(user_id, person=entity)
            for p in profiles:
                content = f"{p['person']}: {p['attribute']} = {p['value']}"
                if content not in results:
                    results[content] = {"content": content, "type": "profile", "sources": []}
                results[content]["sources"].append("profile")

        # 4. Temporal search (for time-related queries)
        if self._is_temporal_query(query):
            events = self.store.get_temporal_events(user_id)
            for e in events:
                content = f"{e['event']} ({e.get('absolute_date', e.get('timestamp_raw', 'unknown date'))})"
                if content not in results:
                    results[content] = {"content": content, "type": "temporal", "sources": []}
                results[content]["sources"].append("temporal")

        # 5. Summaries (always include for context)
        summaries = self.store.get_summaries(user_id)
        for s in summaries:
            content = s["summary"]
            if content not in results:
                results[content] = {"content": content, "type": "summary", "sources": []}
            results[content]["sources"].append("summary")

        # RRF fusion scoring
        candidates = list(results.values())
        for c in candidates:
            c["rrf_score"] = self._compute_rrf_score(c)

        # Sort by RRF score
        candidates.sort(key=lambda x: x["rrf_score"], reverse=True)
        return candidates[:top_k]

    def _agentic_retrieval(
        self, query: str, candidates: List[Dict], user_id: str, top_k: int
    ) -> List[Dict]:
        """
        Agentic multi-round retrieval (inspired by EverMemOS).
        1. Check if current results are sufficient
        2. If not, generate 2-3 complementary queries
        3. Re-search with new queries and merge results
        """
        # Format current results for sufficiency check
        docs_text = "\n".join(
            f"[{i+1}] ({c['type']}) {c['content']}" for i, c in enumerate(candidates[:15])
        )

        # Check sufficiency
        check_response = call_llm(
            prompt=SUFFICIENCY_CHECK_PROMPT.format(query=query, retrieved_docs=docs_text),
            provider=self.llm_provider,
            model=self.llm_model,
            api_key=self.api_key,
        )

        try:
            check = json.loads(self._extract_json(check_response))
            if check.get("is_sufficient", True):
                return candidates
        except (json.JSONDecodeError, TypeError):
            return candidates

        # Generate complementary queries
        missing_info = check.get("missing_information", [])
        key_info = check.get("key_information_found", [])

        query_response = call_llm(
            prompt=MULTI_QUERY_PROMPT.format(
                original_query=query,
                key_info=json.dumps(key_info),
                missing_info=json.dumps(missing_info),
                retrieved_docs=docs_text,
            ),
            provider=self.llm_provider,
            model=self.llm_model,
            api_key=self.api_key,
        )

        try:
            multi_q = json.loads(self._extract_json(query_response))
            new_queries = multi_q.get("queries", [])
        except (json.JSONDecodeError, TypeError):
            return candidates

        # Search with each new query and merge
        all_results = {c["content"]: c for c in candidates}
        for new_q in new_queries[:3]:
            new_results = self._hybrid_search(new_q, user_id, top_k=top_k)
            for r in new_results:
                if r["content"] not in all_results:
                    r["sources"].append("agentic_requery")
                    all_results[r["content"]] = r

        merged = list(all_results.values())
        # Re-score with RRF
        for c in merged:
            c["rrf_score"] = self._compute_rrf_score(c)
        merged.sort(key=lambda x: x["rrf_score"], reverse=True)

        return merged[:top_k * 2]

    def _rerank(self, query: str, candidates: List[Dict], top_k: int = 10) -> List[Dict]:
        """
        Rerank candidates using LLM-based relevance scoring.
        Cheaper than a cross-encoder but effective for small candidate sets.
        """
        if len(candidates) <= top_k:
            return candidates

        # For efficiency, only rerank top candidates
        to_rerank = candidates[:min(len(candidates), top_k * 3)]

        # Simple relevance scoring via LLM
        docs_text = "\n".join(
            f"[{i+1}] {c['content']}" for i, c in enumerate(to_rerank)
        )

        rerank_prompt = f"""Rate the relevance of each document to the query on a scale of 0-10.

Query: {query}

Documents:
{docs_text}

Return a JSON array of objects with "doc_id" (1-indexed) and "score" (0-10).
Return ONLY the JSON array. Example: [{{"doc_id": 1, "score": 9}}, {{"doc_id": 2, "score": 3}}]"""

        response = call_llm(
            prompt=rerank_prompt,
            provider=self.llm_provider,
            model=self.llm_model,
            api_key=self.api_key,
        )

        try:
            scores = json.loads(self._extract_json(response))
            score_map = {s["doc_id"]: s["score"] for s in scores if isinstance(s, dict)}
            for i, c in enumerate(to_rerank):
                c["rerank_score"] = score_map.get(i + 1, 5)
            to_rerank.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        except (json.JSONDecodeError, TypeError, KeyError):
            pass  # Fall back to RRF ordering

        return to_rerank[:top_k]

    def _assemble_context(self, memories: List[Dict], max_tokens: int = 1500) -> str:
        """Assemble memories into a context string within token budget."""
        lines = []
        char_budget = max_tokens * 4  # ~4 chars per token

        for m in memories:
            line = f"[{m['type'].upper()}] {m['content']}"
            if sum(len(l) for l in lines) + len(line) > char_budget:
                break
            lines.append(line)

        return "\n".join(lines)

    def answer(self, query: str, context: str, memories: List[Dict]) -> str:
        """Generate an answer using chain-of-thought reasoning over memories."""
        response = call_llm(
            prompt=ANSWER_PROMPT.format(context=context, question=query),
            provider=self.llm_provider,
            model=self.llm_model,
            api_key=self.api_key,
        )

        # Extract final answer if structured response
        if "FINAL ANSWER:" in response:
            return response.split("FINAL ANSWER:")[-1].strip()
        return response.strip()

    def _compute_rrf_score(self, candidate: Dict, k: int = 60) -> float:
        """Reciprocal Rank Fusion score."""
        score = 0.0
        # BM25 rank contribution
        if "bm25_rank" in candidate:
            score += 1.0 / (k + candidate["bm25_rank"])
        # Source diversity bonus
        num_sources = len(set(candidate.get("sources", [])))
        score += num_sources * 0.1
        # Graph hop penalty (further hops = less relevant)
        for s in candidate.get("sources", []):
            if s.startswith("graph_hop"):
                hop = int(s[-1])
                score += 1.0 / (k + hop * 10)
            elif s == "graph":
                score += 1.0 / (k + 1)  # Direct match
            elif s == "profile":
                score += 1.0 / (k + 2)
            elif s == "temporal":
                score += 1.0 / (k + 3)
            elif s == "summary":
                score += 1.0 / (k + 5)
        return score

    def _extract_query_entities(self, query: str) -> List[str]:
        """Extract likely entity names from a query using simple heuristics."""
        # Capitalize words are likely entities
        words = query.split()
        entities = []
        current = []
        for w in words:
            # Skip question words and common words
            if w.lower() in {"what", "when", "where", "who", "how", "why", "did", "does",
                             "is", "are", "was", "were", "the", "a", "an", "in", "on",
                             "at", "to", "for", "of", "with", "and", "or", "not", "has",
                             "have", "had", "do", "will", "would", "could", "should",
                             "about", "from", "by", "that", "this", "it", "they", "he",
                             "she", "his", "her", "their", "its", "my", "your"}:
                if current:
                    entities.append(" ".join(current))
                    current = []
                continue
            if w[0].isupper() or w.replace("'s", "").replace("'", "").isalpha():
                current.append(w.rstrip("?.,!"))
            else:
                if current:
                    entities.append(" ".join(current))
                    current = []
        if current:
            entities.append(" ".join(current))

        # Filter out very short or common entities
        return [e for e in entities if len(e) > 1]

    def _is_temporal_query(self, query: str) -> bool:
        """Check if query involves temporal reasoning."""
        temporal_keywords = {
            "when", "before", "after", "during", "since", "until", "ago",
            "last", "next", "first", "latest", "recent", "earlier", "later",
            "how long", "how often", "date", "time", "year", "month", "week",
            "day", "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        }
        query_lower = query.lower()
        return any(kw in query_lower for kw in temporal_keywords)

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        # Try to find JSON object or array
        for pattern in [r"\{.*\}", r"\[.*\]"]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return match.group()
        return text

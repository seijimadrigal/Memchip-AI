from __future__ import annotations
"""Main MemChip v2 class with add() and recall()."""

from .storage import Storage
from .consolidation import consolidate_session
from .router import classify_query, is_confident, escalate, decompose_multihop
from .answerer import (
    answer_strategy_a, answer_strategy_b, answer_strategy_c, answer_strategy_d,
    synthesize_subanswers, _mask_entities_in_context,
)


class MemChipV2:
    def __init__(self, api_key: str, db_path: str = ":memory:"):
        self.api_key = api_key
        self.storage = Storage(db_path)

    def add(self, session_id: str, date: str, conversation: list[dict], speaker_a: str, speaker_b: str):
        """Ingest a session: store raw, build episode summary, update entity profiles."""
        consolidate_session(self.api_key, self.storage, session_id, date, conversation, speaker_a, speaker_b)

    def recall(self, question: str, category: int | None = None, max_escalations: int = 3) -> dict:
        """Answer a question using adaptive recall routing with confidence escalation."""
        
        # Adversarial (category 5): use entity-masked answering
        if category == 5:
            return self._recall_adversarial(question)
        
        strategy = classify_query(self.api_key, question, category)
        
        # Force minimum strategy B for single-hop (category 1) 
        # Profiles alone miss specific details like book titles, items bought, etc.
        if category == 1 and strategy == "A":
            strategy = "B"
        
        # For multi-hop (category 4 or strategy C), try decomposition
        if category == 4 or strategy == "C":
            return self._recall_multihop(question, strategy)
        
        return self._recall_single(question, strategy, max_escalations)

    def _recall_adversarial(self, question: str) -> dict:
        """Adversarial recall: mask entity names so LLM can't detect the swap."""
        profiles = self.storage.get_all_profiles()
        episodes = self.storage.get_all_episodes()
        
        # Get relevant raw sessions
        relevant_ids = self._identify_relevant_sessions(question, episodes)
        raw_sessions = self.storage.get_engrams(relevant_ids)
        
        # Mask entities: replace OTHER entity with QUESTION entity in all context
        masked_profiles, masked_episodes, masked_raw = _mask_entities_in_context(
            question, profiles, episodes, raw_sessions
        )
        
        # Use strategy C with masked context
        answer = answer_strategy_c(self.api_key, question, masked_profiles, masked_episodes, masked_raw)
        
        return {
            "answer": answer,
            "strategy": "adversarial_masked",
            "strategies_tried": ["adversarial_masked"],
        }

    def _recall_single(self, question: str, strategy: str, max_escalations: int = 3) -> dict:
        """Single question recall with confidence escalation."""
        strategies_tried = []
        
        for _ in range(max_escalations + 1):
            answer = self._execute_strategy(question, strategy)
            strategies_tried.append(strategy)
            
            if is_confident(answer) or strategy == "D":
                return {
                    "answer": answer,
                    "strategy": strategy,
                    "strategies_tried": strategies_tried,
                }
            
            next_s = escalate(strategy)
            if next_s is None:
                break
            strategy = next_s
        
        return {
            "answer": answer,
            "strategy": strategy,
            "strategies_tried": strategies_tried,
        }

    def _recall_multihop(self, question: str, initial_strategy: str) -> dict:
        """Multi-hop recall: decompose, route each sub-q, synthesize."""
        sub_questions = decompose_multihop(self.api_key, question)
        
        if len(sub_questions) <= 1:
            # Not really decomposable, use deep strategy
            return self._recall_single(question, max(initial_strategy, "B"), 3)
        
        sub_qas = []
        all_strategies = []
        for sq in sub_questions:
            sub_strategy = classify_query(self.api_key, sq)
            result = self._recall_single(sq, sub_strategy, 2)
            sub_qas.append((sq, result["answer"]))
            all_strategies.extend(result["strategies_tried"])
        
        final_answer = synthesize_subanswers(self.api_key, question, sub_qas)
        
        # Check confidence of synthesized answer; if low, fallback to strategy C/D on full question
        if not is_confident(final_answer):
            result = self._recall_single(question, "C", 2)
            return {
                "answer": result["answer"],
                "strategy": f"multihop→{result['strategy']}",
                "strategies_tried": all_strategies + result["strategies_tried"],
            }
        
        return {
            "answer": final_answer,
            "strategy": f"multihop({','.join(all_strategies)})",
            "strategies_tried": all_strategies,
        }

    def _execute_strategy(self, question: str, strategy: str) -> str:
        """Execute a specific retrieval strategy."""
        profiles = self.storage.get_all_profiles()
        
        if strategy == "A":
            return answer_strategy_a(self.api_key, question, profiles)
        
        episodes = self.storage.get_all_episodes()
        
        if strategy == "B":
            return answer_strategy_b(self.api_key, question, profiles, episodes)
        
        if strategy == "C":
            # Identify relevant sessions from episodes
            relevant_ids = self._identify_relevant_sessions(question, episodes)
            raw_sessions = self.storage.get_engrams(relevant_ids)
            return answer_strategy_c(self.api_key, question, profiles, episodes, raw_sessions)
        
        # Strategy D: everything
        all_raw = self.storage.get_all_engrams()
        return answer_strategy_d(self.api_key, question, profiles, episodes, all_raw)

    def _identify_relevant_sessions(self, question: str, episodes: list[dict], max_sessions: int = 5) -> list[str]:
        """Identify which raw sessions are most relevant to a question."""
        # Use FTS search on episodes
        # Extract key terms from question
        import re
        words = re.findall(r'\b\w+\b', question.lower())
        stop = {'what', 'when', 'where', 'who', 'how', 'did', 'does', 'do', 'is', 'are', 'was', 'were', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'has', 'have', 'had', 'and', 'or', 'but', 'not', 'this', 'that', 'they', 'their', 'it', 'its', 'about', 'from', 'by'}
        keywords = [w for w in words if w not in stop and len(w) > 2]
        
        # Score episodes by keyword overlap
        scored = []
        for ep in episodes:
            summary_lower = ep["summary"].lower()
            score = sum(1 for kw in keywords if kw in summary_lower)
            if score > 0:
                scored.append((score, ep["session_id"]))
        
        scored.sort(reverse=True)
        return [sid for _, sid in scored[:max_sessions]]

    def close(self):
        self.storage.close()

from __future__ import annotations
"""MemChip v20: EverMemOS-inspired architecture.

Key changes from v19:
- Atomic fact extraction with individual embeddings (not chunks)
- Hybrid BM25 + Embedding retrieval with RRF fusion
- Agentic multi-round retrieval with LLM sufficiency checking
- gpt-4.1 (full) for answer generation
- 2-step extract-then-answer pipeline
"""

import re
from .storage import Storage
from .extractor import extract_atomic_facts, extract_episode_summary, extract_temporal_events
from .embedder import embed_texts
from .retriever import hybrid_retrieve
from .agentic import agentic_retrieve
from .answerer import (
    answer_from_episodes, answer_temporal, answer_adversarial,
    synthesize_subanswers, judge_answer,
)


class MemChipV20:
    def __init__(self, api_key: str, db_path: str = ":memory:"):
        self.api_key = api_key
        self.storage = Storage(db_path)
        self._speakers = []

    def add(self, session_id: str, date: str, conversation: list[dict],
            speaker_a: str, speaker_b: str):
        """Ingest a conversation session: extract atomic facts, episodes, temporal events."""
        self._speakers = [speaker_a, speaker_b]
        
        # 1. Extract atomic facts
        facts = extract_atomic_facts(
            self.api_key, session_id, date, conversation, speaker_a, speaker_b
        )
        print(f"    Extracted {len(facts)} atomic facts")
        
        # 2. Store facts
        for f in facts:
            self.storage.add_atomic_fact(
                fact_id=f["fact_id"],
                entity=f["entity"],
                fact_text=f["fact_text"],
                session_id=f["session_id"],
                date=f["date"],
                date_iso=f["date_iso"],
                related_entities=f.get("related_entities", []),
            )
        
        # 3. Embed all facts
        if facts:
            texts = [f["fact_text"] for f in facts]
            embeddings = embed_texts(texts)
            for f, emb in zip(facts, embeddings):
                self.storage.add_embedding(f["fact_id"], emb)
            print(f"    Embedded {len(facts)} facts")
        
        # 4. Extract and store rich episode narrative
        episode = extract_episode_summary(
            self.api_key, session_id, date, conversation, speaker_a, speaker_b
        )
        from .extractor import _parse_date_to_iso
        date_iso = _parse_date_to_iso(date)
        self.storage.add_episode(session_id, date, date_iso, 
                                  episode["content"], title=episode["title"])
        
        # 5. Extract and store temporal events
        events = extract_temporal_events(
            self.api_key, session_id, date, conversation, speaker_a, speaker_b
        )
        for ev in events:
            self.storage.add_temporal_event(
                entity=ev["entity"],
                event_text=ev["event_text"],
                date=ev["date"],
                date_iso=ev["date_iso"],
                session_id=session_id,
            )
        print(f"    Stored {len(events)} temporal events")

    def recall(self, question: str, category: int) -> dict:
        """Answer a question using the appropriate strategy for its category.
        
        Categories: 1=single-hop, 2=temporal, 3=open-domain, 4=multi-hop, 5=adversarial
        """
        if category == 1:
            return self._recall_single_hop(question)
        elif category == 2:
            return self._recall_temporal(question)
        elif category == 3:
            return self._recall_open_domain(question)
        elif category == 4:
            return self._recall_multihop(question)
        elif category == 5:
            return self._recall_adversarial(question)
        else:
            return self._recall_single_hop(question)

    def _recall_single_hop(self, question: str) -> dict:
        """Single-hop: agentic retrieval → find relevant episodes → CoT answer."""
        entity = self._extract_entity(question)
        facts, meta = agentic_retrieve(self.api_key, question, self.storage, entity=entity)
        
        # Use atomic facts to identify relevant sessions, then pass full episodes
        episodes = self._get_episodes_from_facts(facts)
        if not episodes:
            episodes = self.storage.get_all_episodes()
        
        answer = answer_from_episodes(self.api_key, question, episodes, self._speakers)
        return {"answer": answer, "strategy": "v20_single_hop", "meta": meta}

    def _recall_temporal(self, question: str) -> dict:
        """Temporal: agentic retrieval → relevant episodes + timeline → CoT answer."""
        entity = self._extract_entity(question)
        facts, meta = agentic_retrieve(self.api_key, question, self.storage, entity=entity)
        
        # Get relevant episodes from facts + all episodes for timeline
        relevant_episodes = self._get_episodes_from_facts(facts)
        all_episodes = self.storage.get_all_episodes()
        temporal_events = self.storage.get_temporal_events(limit=100)
        
        # Use relevant episodes if found, otherwise all
        episodes_for_answer = relevant_episodes if relevant_episodes else all_episodes
        
        answer = answer_temporal(self.api_key, question, episodes_for_answer, 
                                  all_episodes, temporal_events, self._speakers)
        return {"answer": answer, "strategy": "v20_temporal", "meta": meta}

    def _recall_multihop(self, question: str) -> dict:
        """Multi-hop: agentic retrieval → relevant episodes → CoT answer."""
        entity = self._extract_entity(question)
        facts, meta = agentic_retrieve(self.api_key, question, self.storage, entity=entity)
        
        # Get relevant episodes
        episodes = self._get_episodes_from_facts(facts)
        if not episodes:
            episodes = self.storage.get_all_episodes()
        
        # Multi-hop gets the CoT prompt which handles cross-memory linking
        answer = answer_from_episodes(self.api_key, question, episodes, self._speakers)
        return {"answer": answer, "strategy": "v20_multihop", "meta": meta}

    def _recall_adversarial(self, question: str) -> dict:
        """Adversarial: entity-masked retrieval + adversarial CoT answer."""
        entity = self._extract_entity(question)
        facts, meta = agentic_retrieve(self.api_key, question, self.storage, entity=entity)
        
        episodes = self._get_episodes_from_facts(facts)
        if not episodes:
            episodes = self.storage.get_all_episodes()
        speakers = self._get_speakers()
        
        answer = answer_adversarial(self.api_key, question, episodes, speakers)
        return {"answer": answer, "strategy": "v20_adversarial", "meta": meta}

    def _recall_open_domain(self, question: str) -> dict:
        """Open-domain: agentic retrieval → relevant episodes → CoT answer."""
        entity = self._extract_entity(question)
        facts, meta = agentic_retrieve(self.api_key, question, self.storage, entity=entity)
        
        episodes = self._get_episodes_from_facts(facts)
        if not episodes:
            episodes = self.storage.get_all_episodes()
        
        answer = answer_from_episodes(self.api_key, question, episodes, self._speakers)
        return {"answer": answer, "strategy": "v20_open_domain", "meta": meta}

    def _get_episodes_from_facts(self, facts: list[dict], max_episodes: int = 10) -> list[dict]:
        """Map retrieved atomic facts back to their source episodes."""
        if not facts:
            return []
        # Get unique session IDs from facts, ordered by relevance
        seen = set()
        session_ids = []
        for f in facts:
            sid = f.get("session_id", "")
            if sid and sid not in seen:
                seen.add(sid)
                session_ids.append(sid)
            if len(session_ids) >= max_episodes:
                break
        return self.storage.get_episodes_by_session_ids(session_ids)

    def _extract_entity(self, question: str) -> str | None:
        """Extract the target entity from a question."""
        question_lower = question.lower()
        speakers = self._get_speakers()
        
        matches = []
        for s in speakers:
            if s.lower() in question_lower:
                matches.append(s)
            else:
                first = s.split()[0]
                if first.lower() in question_lower:
                    matches.append(s)
        
        if len(matches) == 1:
            return matches[0]
        
        # Try possessive
        poss = re.search(r"(\b\w+)'s\b", question)
        if poss:
            name = poss.group(1).lower()
            for s in speakers:
                if s.lower().startswith(name) or s.split()[0].lower() == name:
                    return s
        
        return matches[0] if matches else None

    def _get_speakers(self) -> list[str]:
        """Get speaker names from stored facts."""
        if self._speakers:
            return self._speakers
        facts = self.storage.get_all_facts()
        entities = set(f["entity"] for f in facts)
        return list(entities)[:2]

    def _decompose(self, question: str) -> list[str]:
        """Decompose a multi-hop question into sub-questions."""
        from .agentic import _llm_call
        
        prompt = f"""Break this complex question into 2-3 simpler sub-questions.
Each sub-question should be independently answerable.

Question: {question}

Output numbered sub-questions only (1-3), no explanations:"""

        messages = [{"role": "user", "content": prompt}]
        result = _llm_call(self.api_key, messages, max_tokens=150, model="openai/gpt-4.1-mini")
        
        lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
        sub_qs = []
        for line in lines:
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
            if cleaned and len(cleaned) > 5:
                sub_qs.append(cleaned)
        
        return sub_qs[:3] if sub_qs else [question]

    def close(self):
        self.storage.close()

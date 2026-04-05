from __future__ import annotations
"""SQLite storage for MemChip v19 — adds entity_facts table for entity-attributed narrative facts."""

import sqlite3
import json
import os
import re
import math
from datetime import datetime, timedelta


class Storage:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        c = self.conn
        c.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                entity TEXT PRIMARY KEY,
                profile_text TEXT,
                updated_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                session_id TEXT PRIMARY KEY,
                date TEXT,
                date_iso TEXT,
                summary TEXT,
                key_entities TEXT,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS engrams (
                session_id TEXT PRIMARY KEY,
                date TEXT,
                raw_text TEXT,
                token_count INTEGER
            )
        """)
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                session_id, summary, content=episodes, content_rowid=rowid
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS temporal_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                entity TEXT,
                event_text TEXT,
                event_date_iso TEXT,
                event_type TEXT DEFAULT 'event'
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_temporal_date ON temporal_events(event_date_iso)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_temporal_entity ON temporal_events(entity)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS raw_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                chunk_idx INTEGER NOT NULL,
                text TEXT NOT NULL,
                date TEXT,
                UNIQUE(session_id, chunk_idx)
            )
        """)
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS raw_chunks_fts USING fts5(
                text, content='raw_chunks', content_rowid='id',
                tokenize='porter unicode61'
            )
        """)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS raw_chunks_ai AFTER INSERT ON raw_chunks BEGIN
                INSERT INTO raw_chunks_fts(rowid, text) VALUES (new.id, new.text);
            END
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS atomic_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                date TEXT,
                fact_text TEXT NOT NULL,
                subject TEXT,
                created_at TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_atomic_session ON atomic_facts(session_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_atomic_subject ON atomic_facts(subject)")
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS atomic_facts_fts USING fts5(
                fact_text, subject, session_id,
                tokenize='porter unicode61'
            )
        """)

        # v19: Entity-attributed narrative facts
        c.execute("""
            CREATE TABLE IF NOT EXISTS entity_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity TEXT NOT NULL,
                fact TEXT NOT NULL,
                date TEXT,
                session_id TEXT,
                related_entities TEXT,
                created_at TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_ef_entity ON entity_facts(entity)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ef_session ON entity_facts(session_id)")
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS entity_facts_fts USING fts5(
                entity, fact, session_id,
                tokenize='porter unicode61'
            )
        """)

        c.commit()

    # --- Profiles ---
    def upsert_profile(self, entity: str, profile_text: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO profiles (entity, profile_text, updated_at) VALUES (?, ?, ?)",
            (entity, profile_text, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_profile(self, entity: str) -> str | None:
        row = self.conn.execute("SELECT profile_text FROM profiles WHERE entity = ?", (entity,)).fetchone()
        return row["profile_text"] if row else None

    def get_all_profiles(self) -> list[dict]:
        rows = self.conn.execute("SELECT entity, profile_text FROM profiles").fetchall()
        return [{"entity": r["entity"], "profile_text": r["profile_text"]} for r in rows]

    # --- Episodes ---
    def upsert_episode(self, session_id: str, date: str, date_iso: str, summary: str, key_entities: list[str]):
        self.conn.execute(
            "INSERT OR REPLACE INTO episodes (session_id, date, date_iso, summary, key_entities, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, date, date_iso, summary, json.dumps(key_entities), datetime.now().isoformat()),
        )
        self.conn.execute("INSERT OR REPLACE INTO episodes_fts (session_id, summary) VALUES (?, ?)", (session_id, summary))
        self.conn.commit()

    def get_all_episodes(self) -> list[dict]:
        rows = self.conn.execute("SELECT session_id, date, date_iso, summary, key_entities FROM episodes ORDER BY date_iso").fetchall()
        return [{"session_id": r["session_id"], "date": r["date"], "summary": r["summary"], "key_entities": json.loads(r["key_entities"])} for r in rows]

    def search_episodes(self, query: str, limit: int = 5, reference_date: str | None = None) -> list[dict]:
        stop = {"what","when","where","who","how","did","does","do","is","are","was","were",
                "the","a","an","in","on","at","to","for","of","with","has","have","had",
                "and","or","but","not","this","that","they","their","it","its","about","from","by"}
        words = re.findall(r'\b\w+\b', query.lower())
        keywords = [w for w in words if w not in stop and len(w) > 2]
        if not keywords:
            return []
        fts_query = " OR ".join(keywords)
        try:
            rows = self.conn.execute(
                "SELECT session_id, summary, date_iso, rank FROM episodes_fts "
                "JOIN episodes USING(session_id) "
                "WHERE episodes_fts MATCH ? ORDER BY rank LIMIT ?",
                (fts_query, limit * 3),
            ).fetchall()
        except Exception:
            rows = self.conn.execute(
                "SELECT session_id, summary, date_iso FROM episodes WHERE 1=1 LIMIT ?", (limit,)
            ).fetchall()
            return [{"session_id": r["session_id"], "summary": r["summary"]} for r in rows]
        if not rows:
            return []
        ref = reference_date or datetime.now().strftime("%Y-%m-%d")
        try:
            ref_dt = datetime.strptime(ref, "%Y-%m-%d")
        except ValueError:
            ref_dt = datetime.now()
        scored = []
        for r in rows:
            fts_score = abs(r["rank"]) if r["rank"] else 1.0
            date_iso = r["date_iso"] or ""
            try:
                ep_dt = datetime.strptime(date_iso[:10], "%Y-%m-%d")
                days_diff = abs((ref_dt - ep_dt).days)
                decay = math.exp(-days_diff / 365.0)
            except (ValueError, TypeError):
                decay = 0.5
            final_score = fts_score * (1.0 + decay)
            scored.append((final_score, r["session_id"], r["summary"]))
        scored.sort(reverse=True)
        return [{"session_id": sid, "summary": summ} for _, sid, summ in scored[:limit]]

    # --- Temporal Events ---
    def store_temporal_event(self, session_id: str, entity: str, event_text: str, event_date_iso: str, event_type: str = "event"):
        self.conn.execute(
            "INSERT INTO temporal_events (session_id, entity, event_text, event_date_iso, event_type) VALUES (?, ?, ?, ?, ?)",
            (session_id, entity, event_text, event_date_iso, event_type),
        )
        self.conn.commit()

    def query_temporal_events(self, entity: str | None = None, date_from: str | None = None, date_to: str | None = None, limit: int = 20) -> list[dict]:
        conditions, params = [], []
        if entity:
            conditions.append("entity LIKE ?")
            params.append(f"%{entity}%")
        if date_from:
            conditions.append("event_date_iso >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("event_date_iso <= ?")
            params.append(date_to)
        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self.conn.execute(
            f"SELECT session_id, entity, event_text, event_date_iso, event_type FROM temporal_events WHERE {where} ORDER BY event_date_iso LIMIT ?",
            params + [limit],
        ).fetchall()
        return [{"session_id": r["session_id"], "entity": r["entity"], "event_text": r["event_text"], "date": r["event_date_iso"], "type": r["event_type"]} for r in rows]

    # --- Engrams ---
    def store_engram(self, session_id: str, date: str, raw_text: str, token_count: int = 0):
        self.conn.execute(
            "INSERT OR REPLACE INTO engrams (session_id, date, raw_text, token_count) VALUES (?, ?, ?, ?)",
            (session_id, date, raw_text, token_count),
        )
        self.conn.commit()

    def get_engram(self, session_id: str) -> str | None:
        row = self.conn.execute("SELECT raw_text FROM engrams WHERE session_id = ?", (session_id,)).fetchone()
        return row["raw_text"] if row else None

    def get_engrams(self, session_ids: list[str]) -> list[dict]:
        if not session_ids: return []
        placeholders = ",".join("?" for _ in session_ids)
        rows = self.conn.execute(
            f"SELECT session_id, date, raw_text FROM engrams WHERE session_id IN ({placeholders}) ORDER BY date",
            session_ids,
        ).fetchall()
        return [{"session_id": r["session_id"], "date": r["date"], "raw_text": r["raw_text"]} for r in rows]

    def get_all_engrams(self) -> list[dict]:
        rows = self.conn.execute("SELECT session_id, date, raw_text FROM engrams ORDER BY date").fetchall()
        return [{"session_id": r["session_id"], "date": r["date"], "raw_text": r["raw_text"]} for r in rows]

    # --- Raw Chunks ---
    def store_raw_chunks(self, session_id: str, date: str, chunks: list[str]):
        for i, chunk in enumerate(chunks):
            self.conn.execute(
                "INSERT OR IGNORE INTO raw_chunks (session_id, chunk_idx, text, date) VALUES (?, ?, ?, ?)",
                (session_id, i, chunk, date),
            )
        self.conn.commit()

    def search_raw_chunks(self, terms: list[str], limit: int = 80) -> list[dict]:
        if not terms: return []
        escaped = []
        for t in terms:
            t = re.sub(r'[^\w\s]', '', t.strip())
            if t:
                escaped.append(f'"{t}"')
        if not escaped: return []
        query = " OR ".join(escaped)
        try:
            rows = self.conn.execute(
                "SELECT c.id, c.session_id, c.chunk_idx, c.text, c.date "
                "FROM raw_chunks_fts "
                "JOIN raw_chunks c ON c.id = raw_chunks_fts.rowid "
                "WHERE raw_chunks_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (query, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def count_raw_chunks(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM raw_chunks").fetchone()[0]

    # --- Atomic Facts ---
    def store_atomic_facts(self, session_id: str, date: str, facts: list[dict]):
        c = self.conn
        for f in facts:
            fact_text = f.get("fact", f.get("fact_text", ""))
            subject = f.get("subject", "")
            if not fact_text: continue
            c.execute(
                "INSERT INTO atomic_facts (session_id, date, fact_text, subject, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, date, fact_text, subject, datetime.now().isoformat()),
            )
            c.execute(
                "INSERT INTO atomic_facts_fts (fact_text, subject, session_id) VALUES (?, ?, ?)",
                (fact_text, subject, session_id),
            )
        c.commit()

    def search_atomic_facts(self, query: str, limit: int = 20) -> list[dict]:
        stop = {"what","when","where","who","how","did","does","do","is","are","was","were",
                "the","a","an","in","on","at","to","for","of","with","has","have","had",
                "and","or","but","not","this","that","they","their","it","its","about","from","by"}
        words = re.findall(r'\b\w+\b', query.lower())
        keywords = [w for w in words if w not in stop and len(w) > 2]
        if not keywords: return []
        fts_query = " OR ".join(keywords)
        try:
            rows = self.conn.execute(
                "SELECT fact_text, subject, session_id, rank FROM atomic_facts_fts "
                "WHERE atomic_facts_fts MATCH ? ORDER BY rank LIMIT ?",
                (fts_query, limit),
            ).fetchall()
            return [{"fact_text": r["fact_text"], "subject": r["subject"], "session_id": r["session_id"]} for r in rows]
        except Exception:
            return []

    def get_all_atomic_facts(self) -> list[dict]:
        rows = self.conn.execute("SELECT fact_text, subject, session_id, date FROM atomic_facts ORDER BY date").fetchall()
        return [{"fact_text": r["fact_text"], "subject": r["subject"], "session_id": r["session_id"], "date": r["date"]} for r in rows]

    # --- v19: Entity Facts ---
    def store_entity_facts(self, facts: list[dict]):
        """Store entity-attributed narrative facts.
        Each fact dict: {entity, fact, date, session_id, related_entities}
        """
        c = self.conn
        for f in facts:
            entity = f.get("entity", "")
            fact = f.get("fact", "")
            if not entity or not fact:
                continue
            date = f.get("date", "")
            session_id = f.get("session_id", "")
            related = json.dumps(f.get("related_entities", []))
            c.execute(
                "INSERT INTO entity_facts (entity, fact, date, session_id, related_entities, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (entity, fact, date, session_id, related, datetime.now().isoformat()),
            )
            c.execute(
                "INSERT INTO entity_facts_fts (entity, fact, session_id) VALUES (?, ?, ?)",
                (entity, fact, session_id),
            )
        c.commit()

    def search_entity_facts(self, query: str, entity: str | None = None, limit: int = 30) -> list[dict]:
        """Search entity facts by FTS query, optionally filtered to a specific entity."""
        stop = {"what","when","where","who","how","did","does","do","is","are","was","were",
                "the","a","an","in","on","at","to","for","of","with","has","have","had",
                "and","or","but","not","this","that","they","their","it","its","about","from","by"}
        words = re.findall(r'\b\w+\b', query.lower())
        keywords = [w for w in words if w not in stop and len(w) > 2]
        if not keywords:
            return []
        fts_query = " OR ".join(keywords)
        try:
            rows = self.conn.execute(
                "SELECT ef.entity, ef.fact, ef.date, ef.session_id, ef.related_entities, rank "
                "FROM entity_facts_fts "
                "JOIN entity_facts ef ON ef.id = entity_facts_fts.rowid "
                "WHERE entity_facts_fts MATCH ? ORDER BY rank LIMIT ?",
                (fts_query, limit * 3),
            ).fetchall()
            results = []
            for r in rows:
                if entity and r["entity"].lower() != entity.lower():
                    continue
                results.append({
                    "entity": r["entity"],
                    "fact": r["fact"],
                    "date": r["date"],
                    "session_id": r["session_id"],
                    "related_entities": json.loads(r["related_entities"]) if r["related_entities"] else [],
                })
                if len(results) >= limit:
                    break
            return results
        except Exception:
            return []

    def get_entity_facts(self, entity: str, limit: int = 100) -> list[dict]:
        """Get ALL facts for a specific entity."""
        rows = self.conn.execute(
            "SELECT entity, fact, date, session_id, related_entities FROM entity_facts WHERE entity = ? ORDER BY date LIMIT ?",
            (entity, limit),
        ).fetchall()
        return [{
            "entity": r["entity"], "fact": r["fact"], "date": r["date"],
            "session_id": r["session_id"],
            "related_entities": json.loads(r["related_entities"]) if r["related_entities"] else [],
        } for r in rows]

    def count_entity_facts(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM entity_facts").fetchone()[0]

    def close(self):
        self.conn.close()

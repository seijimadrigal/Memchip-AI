from __future__ import annotations
"""SQLite storage for MemChip v20 — atomic facts with embeddings."""

import sqlite3
import json
import os
import re
import numpy as np
from datetime import datetime


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
        # Atomic facts — the core unit of knowledge
        c.execute("""
            CREATE TABLE IF NOT EXISTS atomic_facts (
                fact_id TEXT PRIMARY KEY,
                entity TEXT NOT NULL,
                fact_text TEXT NOT NULL,
                session_id TEXT,
                date TEXT,
                date_iso TEXT,
                related_entities TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # FTS5 index on atomic facts for BM25-style retrieval
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                fact_id, entity, fact_text,
                content=atomic_facts, content_rowid=rowid,
                tokenize='porter unicode61'
            )
        """)
        # Embeddings stored as blobs
        c.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                fact_id TEXT PRIMARY KEY,
                embedding BLOB NOT NULL,
                FOREIGN KEY (fact_id) REFERENCES atomic_facts(fact_id)
            )
        """)
        # Episodes — session summaries for temporal reasoning
        c.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                session_id TEXT PRIMARY KEY,
                date TEXT,
                date_iso TEXT,
                summary TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                session_id, summary,
                content=episodes, content_rowid=rowid,
                tokenize='porter unicode61'
            )
        """)
        # Temporal events for timeline queries
        c.execute("""
            CREATE TABLE IF NOT EXISTS temporal_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity TEXT,
                event_text TEXT,
                date TEXT,
                date_iso TEXT,
                session_id TEXT
            )
        """)
        c.commit()

    # === Atomic Facts ===
    
    def add_atomic_fact(self, fact_id: str, entity: str, fact_text: str,
                        session_id: str, date: str, date_iso: str,
                        related_entities: list[str] | None = None):
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO atomic_facts (fact_id, entity, fact_text, session_id, date, date_iso, related_entities) VALUES (?,?,?,?,?,?,?)",
                (fact_id, entity, fact_text, session_id, date, date_iso,
                 json.dumps(related_entities or []))
            )
            # Update FTS
            self.conn.execute(
                "INSERT OR IGNORE INTO facts_fts (fact_id, entity, fact_text) VALUES (?,?,?)",
                (fact_id, entity, fact_text)
            )
            self.conn.commit()
        except Exception as e:
            print(f"Warning: Failed to add fact {fact_id}: {e}")

    def add_embedding(self, fact_id: str, embedding: np.ndarray):
        blob = embedding.astype(np.float32).tobytes()
        self.conn.execute(
            "INSERT OR REPLACE INTO embeddings (fact_id, embedding) VALUES (?,?)",
            (fact_id, blob)
        )
        self.conn.commit()

    def get_all_facts(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM atomic_facts").fetchall()
        return [dict(r) for r in rows]

    def get_facts_by_entity(self, entity: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM atomic_facts WHERE entity = ? COLLATE NOCASE",
            (entity,)
        ).fetchall()
        return [dict(r) for r in rows]

    def search_facts_fts(self, query: str, limit: int = 50) -> list[dict]:
        """FTS5 search on atomic facts."""
        stop = {'what','when','where','who','how','did','does','do','is','are','was','were',
                'the','a','an','in','on','at','to','for','of','with','has','have','had',
                'and','or','but','not','this','that','they','their','it','its','about','from','by'}
        words = re.findall(r'\b\w+\b', query.lower())
        terms = [w for w in words if w not in stop and len(w) > 2]
        if not terms:
            terms = [w for w in words if len(w) > 1]
        if not terms:
            return []
        
        fts_query = " OR ".join(terms)
        try:
            rows = self.conn.execute(
                "SELECT af.*, facts_fts.rank FROM facts_fts JOIN atomic_facts af ON facts_fts.fact_id = af.fact_id WHERE facts_fts MATCH ? ORDER BY facts_fts.rank LIMIT ?",
                (fts_query, limit)
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_all_embeddings(self) -> list[tuple[str, np.ndarray]]:
        """Return all (fact_id, embedding) pairs for vector search."""
        rows = self.conn.execute(
            "SELECT e.fact_id, e.embedding, af.fact_text, af.entity, af.date, af.session_id "
            "FROM embeddings e JOIN atomic_facts af ON e.fact_id = af.fact_id"
        ).fetchall()
        results = []
        for r in rows:
            emb = np.frombuffer(r["embedding"], dtype=np.float32)
            results.append({
                "fact_id": r["fact_id"],
                "embedding": emb,
                "fact_text": r["fact_text"],
                "entity": r["entity"],
                "date": r["date"],
                "session_id": r["session_id"],
            })
        return results

    def count_facts(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM atomic_facts").fetchone()[0]

    # === Episodes ===

    def add_episode(self, session_id: str, date: str, date_iso: str, summary: str, title: str = ""):
        self.conn.execute(
            "INSERT OR REPLACE INTO episodes (session_id, date, date_iso, summary) VALUES (?,?,?,?)",
            (session_id, date, date_iso, f"{title}\n{summary}" if title else summary)
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO episodes_fts (session_id, summary) VALUES (?,?)",
            (session_id, f"{title} {summary}" if title else summary)
        )
        self.conn.commit()

    def get_all_episodes(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM episodes ORDER BY date_iso").fetchall()
        return [dict(r) for r in rows]

    def get_episodes_by_session_ids(self, session_ids: list[str]) -> list[dict]:
        """Get episodes for specific session IDs, preserving order."""
        if not session_ids:
            return []
        placeholders = ",".join("?" for _ in session_ids)
        rows = self.conn.execute(
            f"SELECT * FROM episodes WHERE session_id IN ({placeholders}) ORDER BY date_iso",
            session_ids
        ).fetchall()
        return [dict(r) for r in rows]

    # === Temporal Events ===

    def add_temporal_event(self, entity: str, event_text: str, date: str, date_iso: str, session_id: str):
        self.conn.execute(
            "INSERT INTO temporal_events (entity, event_text, date, date_iso, session_id) VALUES (?,?,?,?,?)",
            (entity, event_text, date, date_iso, session_id)
        )
        self.conn.commit()

    def get_temporal_events(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM temporal_events ORDER BY date_iso LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()

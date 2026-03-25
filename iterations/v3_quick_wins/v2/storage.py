from __future__ import annotations
"""SQLite storage with 3 tables + FTS5 for MemChip v2."""

import sqlite3
import json
import os


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
        # FTS5 for episode summaries
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                session_id, summary, content=episodes, content_rowid=rowid
            )
        """)
        c.commit()

    def upsert_profile(self, entity: str, profile_text: str):
        from datetime import datetime
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

    def upsert_episode(self, session_id: str, date: str, date_iso: str, summary: str, key_entities: list[str]):
        from datetime import datetime
        self.conn.execute(
            "INSERT OR REPLACE INTO episodes (session_id, date, date_iso, summary, key_entities, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, date, date_iso, summary, json.dumps(key_entities), datetime.now().isoformat()),
        )
        # Update FTS
        self.conn.execute("INSERT OR REPLACE INTO episodes_fts (session_id, summary) VALUES (?, ?)", (session_id, summary))
        self.conn.commit()

    def get_all_episodes(self) -> list[dict]:
        rows = self.conn.execute("SELECT session_id, date, date_iso, summary, key_entities FROM episodes ORDER BY date_iso").fetchall()
        return [{"session_id": r["session_id"], "date": r["date"], "summary": r["summary"], "key_entities": json.loads(r["key_entities"])} for r in rows]

    def search_episodes(self, query: str, limit: int = 5) -> list[dict]:
        rows = self.conn.execute(
            "SELECT session_id, summary FROM episodes_fts WHERE episodes_fts MATCH ? LIMIT ?",
            (query, limit),
        ).fetchall()
        return [{"session_id": r["session_id"], "summary": r["summary"]} for r in rows]

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
        if not session_ids:
            return []
        placeholders = ",".join("?" for _ in session_ids)
        rows = self.conn.execute(
            f"SELECT session_id, date, raw_text FROM engrams WHERE session_id IN ({placeholders}) ORDER BY date",
            session_ids,
        ).fetchall()
        return [{"session_id": r["session_id"], "date": r["date"], "raw_text": r["raw_text"]} for r in rows]

    def get_all_engrams(self) -> list[dict]:
        rows = self.conn.execute("SELECT session_id, date, raw_text FROM engrams ORDER BY date").fetchall()
        return [{"session_id": r["session_id"], "date": r["date"], "raw_text": r["raw_text"]} for r in rows]

    def close(self):
        self.conn.close()

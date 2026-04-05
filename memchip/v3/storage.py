"""Raw text storage with FTS5 for substring matching."""
from __future__ import annotations
import sqlite3
import re
from pathlib import Path


class RawTextStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                chunk_idx INTEGER NOT NULL,
                text TEXT NOT NULL,
                date TEXT,
                UNIQUE(session_id, chunk_idx)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text, content='chunks', content_rowid='id'
            );
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
            END;
        """)
        self.conn.commit()

    def add_chunks(self, session_id: str, date: str, chunks: list[str]):
        for i, chunk in enumerate(chunks):
            self.conn.execute(
                "INSERT OR IGNORE INTO chunks (session_id, chunk_idx, text, date) VALUES (?, ?, ?, ?)",
                (session_id, i, chunk, date),
            )
        self.conn.commit()

    def search_fts(self, terms: list[str], limit: int = 100) -> list[dict]:
        """Search using FTS5 with OR logic for maximum recall."""
        if not terms:
            return []
        # Escape FTS5 special chars and quote terms
        escaped = []
        for t in terms:
            t = t.strip()
            if t:
                # Remove FTS5 special characters
                t = re.sub(r'[^\w\s]', '', t)
                if t:
                    escaped.append(f'"{t}"')
        if not escaped:
            return []
        query = " OR ".join(escaped)
        try:
            rows = self.conn.execute(
                f"SELECT c.id, c.session_id, c.chunk_idx, c.text, c.date, "
                f"chunks_fts.rank as rank "
                f"FROM chunks_fts "
                f"JOIN chunks c ON c.id = chunks_fts.rowid "
                f"WHERE chunks_fts MATCH ? "
                f"ORDER BY rank LIMIT ?",
                (query, limit),
            ).fetchall()
        except Exception:
            return []
        return [dict(r) for r in rows]

    def get_all_chunks(self) -> list[dict]:
        rows = self.conn.execute("SELECT id, session_id, chunk_idx, text, date FROM chunks").fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def close(self):
        self.conn.close()

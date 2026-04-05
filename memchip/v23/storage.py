"""Raw text storage with FTS5 for v23."""
from __future__ import annotations
import sqlite3
import os


class RawTextStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()
    
    def _init_tables(self):
        c = self.conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            date TEXT,
            chunk_idx INTEGER,
            text TEXT NOT NULL
        )""")
        c.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts 
            USING fts5(text, content=chunks, content_rowid=id)""")
        # Triggers to keep FTS in sync
        c.execute("""CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
        END""")
        self.conn.commit()
    
    def add_chunks(self, session_id: str, date: str, chunks: list[str]):
        c = self.conn.cursor()
        for i, chunk in enumerate(chunks):
            c.execute("INSERT INTO chunks (session_id, date, chunk_idx, text) VALUES (?, ?, ?, ?)",
                      (session_id, date, i, chunk))
        self.conn.commit()
    
    def search_fts(self, terms: list[str], limit: int = 100) -> list[dict]:
        """FTS5 OR search with terms."""
        if not terms:
            return []
        
        # Build OR query — each term quoted for safety
        fts_query = " OR ".join(f'"{t}"' for t in terms if t.strip())
        if not fts_query:
            return []
        
        c = self.conn.cursor()
        try:
            rows = c.execute("""
                SELECT c.id, c.session_id, c.date, c.chunk_idx, c.text,
                       chunks_fts.rank as fts_rank
                FROM chunks_fts
                JOIN chunks c ON c.id = chunks_fts.rowid
                WHERE chunks_fts MATCH ?
                ORDER BY chunks_fts.rank
                LIMIT ?
            """, (fts_query, limit)).fetchall()
        except Exception:
            return []
        
        return [dict(r) for r in rows]
    
    def search_substring(self, term: str, limit: int = 100) -> list[dict]:
        """Case-insensitive substring search (fallback)."""
        c = self.conn.cursor()
        rows = c.execute("""
            SELECT id, session_id, date, chunk_idx, text
            FROM chunks
            WHERE text LIKE ?
            LIMIT ?
        """, (f"%{term}%", limit)).fetchall()
        return [dict(r) for r in rows]
    
    def get_all_chunks(self) -> list[dict]:
        """Get all stored chunks."""
        c = self.conn.cursor()
        rows = c.execute("SELECT id, session_id, date, chunk_idx, text FROM chunks ORDER BY session_id, chunk_idx").fetchall()
        return [dict(r) for r in rows]
    
    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    
    def close(self):
        self.conn.close()

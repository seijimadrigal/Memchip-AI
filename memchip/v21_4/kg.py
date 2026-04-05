from __future__ import annotations
"""Knowledge Graph storage and querying on SQLite with FTS5."""

import sqlite3
import re
from typing import Optional


class KnowledgeGraph:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._init_tables()

    def _init_tables(self):
        c = self.conn
        c.execute("""
            CREATE TABLE IF NOT EXISTS kg_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'person',
                canonical_name TEXT NOT NULL,
                UNIQUE(canonical_name)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS kg_aliases (
                alias TEXT NOT NULL,
                canonical_name TEXT NOT NULL,
                UNIQUE(alias)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS kg_triples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                session_id TEXT,
                date TEXT,
                confidence REAL DEFAULT 1.0
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_kg_subj ON kg_triples(subject)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_kg_obj ON kg_triples(object)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_kg_pred ON kg_triples(predicate)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_kg_date ON kg_triples(date)")
        # FTS5 for keyword search over triples
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS kg_triples_fts USING fts5(
                subject, predicate, object,
                content='kg_triples', content_rowid='id',
                tokenize='porter unicode61'
            )
        """)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS kg_triples_ai AFTER INSERT ON kg_triples BEGIN
                INSERT INTO kg_triples_fts(rowid, subject, predicate, object)
                VALUES (new.id, new.subject, new.predicate, new.object);
            END
        """)
        c.commit()

    def resolve_entity(self, name: str) -> str:
        """Resolve an entity name to its canonical form via alias table."""
        normalized = name.strip().lower()
        row = self.conn.execute(
            "SELECT canonical_name FROM kg_aliases WHERE alias = ?", (normalized,)
        ).fetchone()
        if row:
            return row[0]
        # Try exact match on canonical
        row = self.conn.execute(
            "SELECT canonical_name FROM kg_entities WHERE LOWER(canonical_name) = ?", (normalized,)
        ).fetchone()
        if row:
            return row[0]
        return name.strip()

    def add_entity(self, name: str, entity_type: str = "person", aliases: list[str] | None = None):
        """Add or update an entity with aliases."""
        canonical = name.strip()
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO kg_entities (name, type, canonical_name) VALUES (?, ?, ?)",
                (canonical, entity_type, canonical),
            )
        except Exception:
            pass
        # Always add the canonical name as an alias
        all_aliases = [canonical.lower()]
        if aliases:
            all_aliases.extend(a.strip().lower() for a in aliases if a.strip())
        # Add first name as alias
        parts = canonical.split()
        if len(parts) > 1:
            all_aliases.append(parts[0].lower())
        for alias in set(all_aliases):
            try:
                self.conn.execute(
                    "INSERT OR IGNORE INTO kg_aliases (alias, canonical_name) VALUES (?, ?)",
                    (alias, canonical),
                )
            except Exception:
                pass
        self.conn.commit()

    def add_triple(self, subject: str, predicate: str, obj: str,
                   session_id: str | None = None, date: str | None = None,
                   confidence: float = 1.0):
        """Add a triple, resolving entity names."""
        subj_resolved = self.resolve_entity(subject)
        self.conn.execute(
            "INSERT INTO kg_triples (subject, predicate, object, session_id, date, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (subj_resolved, predicate.strip(), obj.strip(), session_id, date, confidence),
        )
        self.conn.commit()

    def add_triples_batch(self, triples: list[dict], session_id: str | None = None, date: str | None = None):
        """Add multiple triples at once."""
        for t in triples:
            subj = self.resolve_entity(t.get("subject", ""))
            pred = t.get("predicate", "").strip()
            obj = t.get("object", "").strip()
            conf = t.get("confidence", 1.0)
            d = t.get("date", date)
            if subj and pred and obj:
                self.conn.execute(
                    "INSERT INTO kg_triples (subject, predicate, object, session_id, date, confidence) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (subj, pred, obj, session_id, d, conf),
                )
        self.conn.commit()

    def get_entity_facts(self, entity_name: str, limit: int = 50) -> list[dict]:
        """Get all triples where entity is subject OR object."""
        canonical = self.resolve_entity(entity_name)
        rows = self.conn.execute(
            "SELECT subject, predicate, object, session_id, date, confidence "
            "FROM kg_triples WHERE subject = ? OR object = ? "
            "ORDER BY confidence DESC, date LIMIT ?",
            (canonical, canonical, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_relationship(self, entity1: str, entity2: str, limit: int = 20) -> list[dict]:
        """Get triples connecting two entities."""
        c1 = self.resolve_entity(entity1)
        c2 = self.resolve_entity(entity2)
        rows = self.conn.execute(
            "SELECT subject, predicate, object, session_id, date, confidence "
            "FROM kg_triples WHERE "
            "(subject = ? AND object = ?) OR (subject = ? AND object = ?) "
            "ORDER BY confidence DESC LIMIT ?",
            (c1, c2, c2, c1, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_triples(self, keywords: str, limit: int = 30) -> list[dict]:
        """Search triples via FTS5."""
        stop = {"what","when","where","who","how","did","does","do","is","are","was","were",
                "the","a","an","in","on","at","to","for","of","with","has","have","had",
                "and","or","but","not","this","that","they","their","it","its","about","from","by"}
        words = re.findall(r'\b\w+\b', keywords.lower())
        terms = [w for w in words if w not in stop and len(w) > 2]
        if not terms:
            return []
        fts_query = " OR ".join(terms)
        try:
            rows = self.conn.execute(
                "SELECT t.subject, t.predicate, t.object, t.session_id, t.date, t.confidence "
                "FROM kg_triples_fts f "
                "JOIN kg_triples t ON t.id = f.rowid "
                "WHERE kg_triples_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (fts_query, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_timeline(self, entity_name: str, limit: int = 50) -> list[dict]:
        """Get temporally ordered facts about an entity."""
        canonical = self.resolve_entity(entity_name)
        rows = self.conn.execute(
            "SELECT subject, predicate, object, session_id, date, confidence "
            "FROM kg_triples WHERE (subject = ? OR object = ?) AND date IS NOT NULL "
            "ORDER BY date ASC LIMIT ?",
            (canonical, canonical, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_triples(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM kg_triples").fetchone()[0]

    def count_entities(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]

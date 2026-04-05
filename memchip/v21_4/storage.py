from __future__ import annotations
"""Storage for v21: v10 storage + KG tables (KG managed by kg.py)."""

# Re-export v10 Storage with KG initialization handled separately
from memchip.v10.storage import Storage as _V10Storage
from .kg import KnowledgeGraph


class Storage(_V10Storage):
    """Extended storage that also initializes KG tables on the same SQLite connection."""

    def __init__(self, db_path: str = ":memory:"):
        super().__init__(db_path)
        self.kg = KnowledgeGraph(self.conn)

    def count_kg_triples(self) -> int:
        return self.kg.count_triples()

    def count_kg_entities(self) -> int:
        return self.kg.count_entities()

# MemChip v21 — Knowledge Graph + Smart Query Router

## Architecture

v21 = v10 base (FTS5 + CrossEncoder + profiles) + **Knowledge Graph** + **Smart Query Router**

### New Components

1. **`kg.py`** — KG storage on SQLite with FTS5
   - Entity nodes with alias resolution (`kg_entities`, `kg_aliases`)
   - Triples: `(subject, predicate, object, session_id, date, confidence)`
   - Query methods: `get_entity_facts()`, `get_relationship()`, `search_triples()`, `get_timeline()`
   - FTS5 fallback search over triple text

2. **`kg_extractor.py`** — Triple extraction via gpt-4.1-mini
   - Batch extracts entities + triples from full conversation text
   - Resolves relative dates to absolute
   - Outputs structured JSON: `{"entities": [...], "triples": [...]}`

3. **`router.py`** — Smart query router
   - Routes: `KG_DIRECT`, `KG_RELATIONSHIP`, `KG_TEMPORAL`, `TEXT_SEARCH`, `ADVERSARIAL`, `OPEN_DOMAIN`
   - Category hints bias routing (cat 1 → KG_DIRECT, cat 2 → KG_TEMPORAL, cat 5 → ADVERSARIAL, cat 3 → OPEN_DOMAIN)
   - LLM classification for ambiguous cases

4. **`answerer.py`** — KG-aware answer generation
   - KG triples as PRIMARY source, text chunks as SUPPLEMENTARY
   - Uses gpt-4.1 (full) for KG-route answers (higher quality)
   - Falls back to v10 text search if KG yields no results or low confidence

5. **`storage.py`** — Extends v10 Storage with KG tables (via composition with `KnowledgeGraph`)

6. **`consolidation.py`** — v10 pipeline + KG triple extraction step

7. **`core.py`** — `MemChipV21` class
   - `add()`: v10 consolidation + KG extraction
   - `recall()`: Route → KG answer or v10 fallback
   - Confidence-based fallback: if KG answer is uncertain, falls back to text search

### Data Flow

```
Question → Router → KG_DIRECT?  → KG triples + top-3 chunks → gpt-4.1 → answer
                  → KG_TEMPORAL? → KG timeline + triples → gpt-4.1 → answer
                  → TEXT_SEARCH? → v10 FTS5+CrossEncoder pipeline
                  → ADVERSARIAL? → v10 entity-masked pipeline
                  → OPEN_DOMAIN? → v10 inference pipeline
```

## Running

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
python3 benchmarks/run_locomo_v21.py \
  --data locomo-benchmark/data/locomo10.json \
  --output benchmarks/results_v21 \
  --conversations sample_1  # optional: test specific conversations
```

## Key Design Decisions

- **gpt-4.1-mini** for extraction and routing (cheap, ~$0.001/call)
- **gpt-4.1** for KG-route answering (better quality for precision tasks)
- KG triples are **unambiguous** — `(Sarah, occupation, software_engineer_at_Google)` vs searching chunks
- Entity alias resolution at **extraction time**, not query time
- Confidence-based fallback ensures no regression from v10

# MemChip v20 — EverMemOS-Inspired Architecture

## Goal: 90%+ on LoCoMo (full 1986 questions, all categories including adversarial)

## Architecture Overview

```
Ingestion:  Conversation → Atomic Fact Extraction → Individual Embeddings + BM25 Index
Retrieval:  Query → Hybrid (BM25 + Embedding) → RRF Fusion → Rerank → Agentic Check
Answering:  Context + Question → gpt-4.1 (full, not mini) → Concise Answer
```

## Key Differences from v19

| Component | v19 (current) | v20 (new) |
|-----------|---------------|-----------|
| Fact storage | Chunks + entity_facts | Individual atomic facts with embeddings |
| Search | FTS5 only | BM25 + Embedding parallel, RRF fusion |
| Reranking | CrossEncoder on chunks | CrossEncoder on atomic facts |
| Retrieval rounds | Single pass | Agentic multi-round (LLM judges sufficiency) |
| Answer model | gpt-4.1-mini | gpt-4.1 (full) |
| Answer style | Single prompt | Extract-then-answer (2-step) |
| Profiles | Static text blob | Not used (atomic facts replace profiles) |

## Module Structure

```
memchip/v20/
├── __init__.py
├── core.py          # Main MemChipV20 class (add + recall)
├── extractor.py     # Atomic fact extraction from conversations
├── storage.py       # SQLite storage for facts, episodes, embeddings
├── embedder.py      # Sentence-transformer embedding + numpy index
├── retriever.py     # Hybrid BM25+Embedding, RRF fusion, reranking
├── agentic.py       # Multi-round retrieval with LLM sufficiency check
├── answerer.py      # 2-step answer generation with gpt-4.1
└── PLAN.md          # This file
```

## Phase 1: Atomic Fact Extraction (extractor.py)

Input: Session conversation (list of turns)
Output: List of atomic facts, each with:
- `fact_id`: unique ID
- `entity`: who this fact is about
- `fact_text`: self-contained factual statement
- `session_id`: source session
- `date`: when this happened
- `related_entities`: other people mentioned

Key principles:
- Each fact is SELF-CONTAINED (includes entity name, never pronouns)
- Specific details preserved (names, places, dates, numbers)
- One fact per distinct piece of information
- Batch 4-6 turns at a time for efficiency

## Phase 2: Storage + Indexing (storage.py, embedder.py)

SQLite tables:
- `atomic_facts`: fact_id, entity, fact_text, session_id, date, related_entities
- `episodes`: session_id, date, summary (kept for temporal queries)
- `embeddings`: fact_id, embedding_blob (numpy array stored as bytes)

Embedding model: `all-MiniLM-L6-v2` (fast, 384-dim, good for short facts)
BM25 index: Built from atomic_facts using rank_bm25

## Phase 3: Hybrid Retrieval + RRF (retriever.py)

1. BM25 search → top 50 facts
2. Embedding cosine similarity → top 50 facts
3. RRF fusion (k=60): merge both rankings without score normalization
4. CrossEncoder rerank → top 20 facts

RRF formula: score(doc) = Σ(1 / (k + rank_i)) across retrievers

## Phase 4: Agentic Multi-Round (agentic.py)

Round 1: Hybrid retrieval → top 20 → rerank → top 10
LLM sufficiency check: "Do these facts answer the question?"
If YES → return top 10
If NO → LLM generates 2-3 refined queries
Round 2: Run hybrid retrieval for each refined query
Multi-RRF: Fuse all round 2 results
Merge Round 1 + Round 2 (deduplicate by fact_id)
Final rerank → top 20

## Phase 5: Answer Generation (answerer.py)

Model: gpt-4.1 (full, not mini)
Strategy per category:
- Single-hop: Atomic facts only, ultra-concise prompt
- Temporal: Atomic facts + episode timeline
- Multi-hop: Decompose → retrieve per sub-question → synthesize
- Adversarial: Same entity masking as v19 (proven 83% on small scale)
- Open-domain: Atomic facts + inference prompt

2-step answering:
1. Extract: "List the specific facts from context that answer this question"
2. Answer: "Given these extracted facts, provide the shortest possible answer"

## Cost Estimate

- Ingestion: ~$1-2 (atomic fact extraction for 10 conversations)
- Per question: ~$0.01-0.02 with gpt-4.1 (vs $0.002 with mini)
- Full benchmark (1986 questions): ~$20-40
- Agentic retrieval adds ~30% more LLM calls for insufficient cases

## Test Plan

1. Build v20 infrastructure
2. Test on conv-26 (199q) — should match or beat 82%
3. Test on conv-42 (260q) — the hard conversation, target 80%+
4. If both pass, run full benchmark (1986q)
5. Compare to v10.4 baseline (81.4%) and v19 (~76%)

# MemChip Iterations Log

Each iteration saves: code snapshot, results, and what changed.

## v2_run5_baseline (2026-03-25)
- **Overall: 69.8%** (199 questions, conv-26 only)
- Temporal: 91.9% | Multi-hop: 80.0% | Open-domain: 76.9% | Single-hop: 59.4% | Adversarial: 42.6%
- Keyword-only retrieval, no semantic search
- Answerer corrects swapped names (adversarial killer)
- Run6 with prompt-only adversarial fix: adversarial DROPPED to 38% (worse)
- **Baseline for all future comparisons**

## v3_quick_wins (next)
- Planned: Entity-masking for adversarial + force strategy B for single-hop
- Expected: +6% overall → ~76%

## v4_semantic_search (planned)
- Add BM25+embedding hybrid search with RRF fusion
- Fix session selection in strategy C
- Expected: +10% overall → ~86%

## v5_full_pipeline (planned)  
- Reranker, agentic multi-round, atomic fact extraction
- Expected: +5-6% → ~92%

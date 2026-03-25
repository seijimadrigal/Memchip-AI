# MemChip Iterations Log

Each iteration saves: code snapshot, results, and what changed.

## Rules
1. Save every iteration's code + results + config to `iterations/` folder
2. Update `BEST_SCORE.md` after each benchmark run
3. Track per-category bests (different configs may peak different categories)
4. Always be able to revert to any previous version
5. Target: 93-95% overall on LoCoMo (1,540 questions, 10 conversations)
6. **Speed: < 2 seconds per query in production** — competitors (Mem0) do 0.2-1.4s. Minimize LLM calls per query (target: 1). Use local embeddings + BM25 for retrieval, not LLM-powered search. Parallel where possible.
7. Architecture must be production-ready, not just benchmark-optimized
8. **Verification required:** VPS agents (Luna etc.) propose ideas — Lyn verifies before implementing. No unverified changes go into the codebase.
9. **Team roles:** Lyn + Midus = orchestrators. VPS agents = research assistants. Cj = project owner.

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

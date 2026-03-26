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

## v5_full_pipeline (Run 9)
- **Overall: 81.6%**
- Single-hop: 72.6% | Multi-hop: 84.1% | Open-domain: 50.0% | Temporal: 92.0% | Adversarial: 81.0%
- Snapshot saved to `iterations/v5_run9/`

## v6_hyde_fewshot_rerank (Run 10)
- **Changes:**
  1. **Query Rewriting + HyDE**: Before session identification, LLM rewrites the question into a search-friendly form and generates a hypothetical answer. FTS5 searches with original + rewritten + HyDE queries, deduplicating results. Applied to single-hop, open-domain, temporal, and adversarial recall paths.
  2. **Few-Shot Examples in Answerer Prompts**: Added 2 short category-aware examples to each strategy prompt (A/B/C) showing how to extract specific facts from the context. Teaches the model the expected answer format and specificity.
  3. **LLM-based Lightweight Reranking**: After retrieving episodes/sessions, an LLM reranks evidence by relevance to the question. Only applied to single-hop (cat 1) and open-domain (cat 3) — our weakest categories. Temporal/multi-hop/adversarial skip reranking for speed.
- **Expected:** +3-5% overall, biggest gains on single-hop and open-domain
- Added methods: `_rewrite_and_hyde()`, `_rerank_evidence()` in core.py
- New few-shot constants: `FEW_SHOT_A`, `FEW_SHOT_B`, `FEW_SHOT_C`, `FEW_SHOT_ADVERSARIAL` in answerer.py
- **Result: 80.0% — REGRESSION** (reverted for v7)

## v7_scoring_improvements (2026-03-26)
- **Changes (in retrieval/engine.py only):**
  1. **Score-Adaptive Truncation**: Replace hard top-k cutoff with adaptive threshold — keep all candidates within 70% of top RRF score (capped at 20). Prevents dropping close-scoring relevant memories.
  2. **NER-Weighted Scoring**: Boost RRF scores for candidates containing query entities (3x for 1 entity match, 5x for 2). Cached from existing `_extract_query_entities()`.
  3. **Increased Context Budget**: `_assemble_context` default max_tokens 1500→3000, char_budget multiplier 4→5 for richer context.
- **No v6 changes** (HyDE, few-shot, LLM reranking all reverted/excluded)
- v5 backup saved to `iterations/v5_backup/`
- **Expected:** +3-5% over v5's 81.6%

## v8_open_domain_path (2026-03-26)
- **Changes:**
  1. **Dedicated open-domain recall path** (`_recall_open_domain()` in core.py): Category 3 questions now bypass the generic `_recall_single()` and use an inference-focused pipeline.
  2. **New `answer_strategy_open_domain()` in answerer.py**: Specialized prompt emphasizing inference from personality traits, preferences, life events, and context clues. Includes few-shot inferential reasoning examples.
  3. **Full personality context**: Open-domain path passes ALL profiles (not just matched ones) since these questions need the complete personality picture.
  4. **Strategy C minimum with escalation**: Always starts with profiles + episodes + relevant raw sessions. If answer isn't confident, escalates to D (all raw sessions).
  5. **Rewrite+HyDE+rerank**: Uses existing `_rewrite_and_hyde()` and `_rerank_evidence()` for better session identification.
- **No changes** to categories 1, 2, 4, or 5 code paths
- **Expected:** Significant improvement on open-domain (was 50.0% in v5, 76.9% in baseline)
- **Single-hop improvements (v8.1):**
  1. **FTS5 on raw engrams**: New `engrams_fts` virtual table indexed on raw_text with porter tokenizer. Populated during `store_engram()`. New `search_engrams()` and `get_engram_snippets()` methods in storage.py.
  2. **Strategy B enrichment for category 1**: Single-hop questions now search `engrams_fts` for top 3 matching raw snippets (500 chars each) and pass them as additional context to `answer_strategy_b()`. No extra LLM call — just FTS5 lookup.
  3. **Answer prompt improvements**: Added list-question rules to `ANSWER_RULES` (be exhaustive but precise). Added list-style few-shot example to `FEW_SHOT_B`.
  4. **No changes** to categories 2, 3, 4, or 5 code paths.

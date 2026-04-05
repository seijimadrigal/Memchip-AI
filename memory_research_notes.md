
## Research Notes (2026-03-28 11PM)

### Hindsight Architecture (89.6% LoCoMo)
- Open source: https://github.com/vectorize-io/hindsight
- Docs: https://hindsight.vectorize.io/
- 4 memory networks: world facts, experience facts, observations (consolidated), opinions
- TEMPR recall: 4-way parallel retrieval (semantic + BM25 + graph + temporal) → RRF → cross-encoder reranker
- CARA reflect: disposition-conditioned reasoning (skepticism, literalism, empathy)
- Priority order at answer time: Mental Models → Observations → Raw Facts
- Best score: 89.61% with Gemini-3 backbone

### Backboard (90.1% LoCoMo, 89.4% single-hop)
- Closed source commercial API
- Uses Gemini 2.5 Pro for answering
- Judge prompt is LENIENT: "as long as it touches on the same topic as the gold answer, count as CORRECT"
- Excludes adversarial (category 5) from scoring
- Their 90.1% is on categories 1-4 only

### Our Gaps (MemChip v10.3 at 81.4%)
1. No semantic vector search (only FTS5 keyword)
2. No entity graph traversal
3. No RRF fusion of multiple retrieval strategies
4. Stricter judge prompt than Backboard
5. Single answering LLM (gpt-4.1-mini) vs Gemini 2.5 Pro

### Actionable Next Steps
1. Add embedding-based retrieval (sentence-transformers, runs on M4 Max)
2. Implement RRF to merge FTS5 + semantic + entity results
3. Match Backboard's lenient judge prompt for fair comparison
4. Consider "observation" layer (consolidated entity summaries) like Hindsight

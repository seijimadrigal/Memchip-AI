# MemChip Best Score Tracker

## Current Best: Run 9 (v5) — 81.6% overall (mini benchmark)

3 conversations (conv-26, conv-30, conv-44), 461 questions.

| Category | Correct | Total | Score |
|---|---|---|---|
| Single-hop (1) | 53 | 73 | 72.6% |
| Multi-hop (2) | 80 | 87 | 92.0% |
| Open-domain (3) | 10 | 20 | 50.0% |
| Temporal (4) | 148 | 176 | 84.1% |
| Adversarial (5) | 85 | 105 | 81.0% |
| **Overall** | **376** | **461** | **81.6%** |

## History
- v2 run5 baseline: 69.8% (199q, 1 conv)
- v2 run6: 65.3% (regression)
- v3 run7: 75.2% (full 10 convs, 1,974q)
- v4 run8: 78.5% (mini 3 convs, 461q) — concise answers + anti-generalization
- v5 run9: 81.6% (mini 3 convs, 461q) — temporal context + token compression ← CURRENT BEST

## Weak spots
- Open-domain (50%) regressed — needs world knowledge fallback
- Single-hop (72.6%) — plateau, needs better retrieval

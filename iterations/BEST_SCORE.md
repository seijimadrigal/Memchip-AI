# MemChip — Best Score Tracker

## 🏆 Current Best: v2_run5_baseline — 69.8% overall

| Category | Score | Accuracy |
|---|---|---|
| Temporal | 34/37 | **91.9%** |
| Multi-hop | 56/70 | **80.0%** |
| Open-domain | 10/13 | **76.9%** |
| Single-hop | 19/32 | 59.4% |
| Adversarial | 20/47 | 42.6% |
| **Overall** | **139/199** | **69.8%** |

### Configuration
- **LLM:** OpenRouter → openai/gpt-4.1-mini
- **Extraction:** 5-type (triples, summaries, entities, temporal, profiles)
- **Storage:** SQLite + FTS5
- **Retrieval:** Keyword-based session selection, no semantic search
- **Answerer:** 4 strategies (A=profile, B=direct, C=session, D=temporal)
- **Router:** Auto-selects strategy based on question type
- **No entity masking, no embedding search, no reranker**

### Conversations tested: conv-26 only (1/10)

---

## Score History

| Version | Date | Overall | Temporal | Multi-hop | Open-domain | Single-hop | Adversarial | Key Change |
|---|---|---|---|---|---|---|---|---|
| v2_run5 | 2026-03-25 | **69.8%** | 91.9% | 80.0% | 76.9% | 59.4% | 42.6% | Baseline |
| v2_run6 | 2026-03-25 | ~65.5% | ~same | ~same | ~same | ~same | 38.1% | Prompt-only adversarial fix (WORSE) |

---

## Category Bests (track which config peaked each category)

| Category | Best Score | Version | Config Detail |
|---|---|---|---|
| Temporal | 91.9% | v2_run5 | Baseline |
| Multi-hop | 80.0% | v2_run5 | Baseline |
| Open-domain | 76.9% | v2_run5 | Baseline |
| Single-hop | 59.4% | v2_run5 | Baseline |
| Adversarial | 42.6% | v2_run5 | Baseline |

---

_Updated automatically after each benchmark run. Always compare against these numbers._

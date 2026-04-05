# MemChip — Full Improvement Plan & Test Instructions

## What Is This
MemChip is a memory-as-a-service layer for AI agents. We're targeting **#1 on the LoCoMo benchmark** (93%+). Current score: **50% (run 1) / 36% (run 3, regression)**.

## Competition
| System | LoCoMo Score |
|--------|-------------|
| EverMemOS | 92.3% (SOTA) |
| MemU | 92.09% |
| Hindsight | 89.6% |
| Zep | ~85% |
| Mem0 | 62-67% |
| **MemChip (current)** | **50%** |

## Architecture
```
Conversation Text
    → Extraction Pipeline (5 parallel LLM calls)
        → Triples (subject-predicate-object)
        → Summaries (2-4 sentences)
        → Entities (named entity recognition)
        → Temporal Events (with absolute dates)
        → Profile Attributes (preferences, habits, facts)
    → SQLite+FTS5 Storage (knowledge graph + full-text search)
    → Multi-Stage Retrieval
        → Stage 1: Hybrid Search (BM25 + graph walk + profile + temporal + raw text, RRF fusion)
        → Stage 2: Agentic Multi-Round (sufficiency check → rephrase → re-search)
        → Stage 3: Context Assembly (token budget packing with session dates)
    → Chain-of-Thought Answer Generation
```

## Project Structure
```
memchip/
├── memchip/
│   ├── __init__.py
│   ├── core.py              # 3-line API: add(), recall(), answer()
│   ├── llm.py               # LLM abstraction (OpenRouter/OpenAI/Anthropic)
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── pipeline.py      # 5-type parallel extraction
│   │   └── prompts.py       # Extraction prompts (CRITICAL — quality depends on these)
│   ├── storage/
│   │   ├── __init__.py
│   │   └── sqlite_store.py  # SQLite+FTS5, knowledge graph, contradiction detection
│   ├── retrieval/
│   │   ├── __init__.py
│   │   ├── engine.py        # 3-stage retrieval pipeline
│   │   └── prompts.py       # Sufficiency check, multi-query, answer prompt
│   ├── api/
│   │   └── __init__.py
│   ├── mcp/
│   │   └── __init__.py
│   └── cli.py
├── benchmarks/
│   └── run_locomo.py         # LoCoMo benchmark runner
├── results/
│   ├── run1/                 # Baseline: 50% (152 questions, conv-26 only)
│   ├── run2/                 # Sub-agent v2: 16% (31 questions, broke things)
│   └── run3/                 # My v2 fixes: 36% (152 questions, regression)
└── HANDOFF.md                # This file
```

## LLM Config
- **Provider:** OpenRouter
- **Model:** `openai/gpt-4.1-mini`
- **API Key:** `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`

## LoCoMo Dataset
- **Location:** `/Users/seijim/.openclaw/workspace/locomo-benchmark/data/locomo10.json`
- **Format:** 10 conversations, each with 15-20 sessions spanning months
- **Questions:** 1,540 scored (categories 1-4), category 5 (adversarial) excluded
- **Categories:** 1=multi_hop (282), 2=temporal (321), 3=open_domain (96), 4=single_hop (841)
- **⚠️ WARNING:** Many runs (v10-v24) had categories 1↔4 SWAPPED in the benchmark runner. Always use the mapping above.
- **Judging:** LLM judge (gpt-4.1-mini) compares prediction vs ground truth

## How To Run Benchmark
```bash
cd /Users/seijim/.openclaw/workspace/memchip

# Test on 1 conversation (conv-26, ~152 questions, ~90 min)
OPENROUTER_API_KEY="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" \
python3 -u benchmarks/run_locomo.py \
  --data /Users/seijim/.openclaw/workspace/locomo-benchmark/data/locomo10.json \
  --output results/run_NAME \
  --max-conv 1 \
  --no-resume

# Full benchmark (all 10 conversations, ~15 hours)
# Add --max-conv 10 or remove --max-conv
```

Results saved to `results/run_NAME/summary.json` and `results/run_NAME/full_results.json`.

Checkpoint saved after each question — can resume if interrupted (remove `--no-resume`).

## Check Progress While Running
```python
import json
with open('results/run_NAME/checkpoint.json') as f:
    r = json.load(f)['results']
cats = {}
for x in r:
    c = x.get('category_name', '?')
    cats.setdefault(c, [0, 0])
    cats[c][1] += 1
    cats[c][0] += x.get('score', 0)
for c, v in sorted(cats.items()):
    print(f'  {c}: {v[0]}/{v[1]} = {v[0]/v[1]*100:.1f}%')
tc = sum(v[0] for v in cats.values())
tt = sum(v[1] for v in cats.values())
print(f'  OVERALL: {tc}/{tt} = {tc/tt*100:.1f}%')
```

---

## DIAGNOSED FAILURE MODES (from run 1 & run 3 comparison)

### 1. TEMPORAL DATE RESOLUTION (biggest failure mode, ~20-30% of errors)
**Problem:** Memories contain relative dates ("yesterday", "last Saturday", "next month") but the answer doesn't convert them to absolute dates.
**Example:**
- Session date: 25 May 2023. Memory: "ran charity race last Saturday"
- Expected: "Saturday, 20 May 2023"
- Got: "last Saturday" (run 1) or wrong date from wrong session (run 3)

**Root cause:** Context assembly doesn't consistently tag every memory with its session date. The LLM can't convert without knowing WHICH session the memory came from.

**Fix needed:**
- Every memory in the assembled context MUST have `[session date: X]` tag
- The answer prompt must instruct explicit date conversion using per-memory session dates
- Currently only triples from graph walk get tagged; FTS results, summaries, profiles, temporal events don't

**Files:** `memchip/retrieval/engine.py` (_assemble_context, _hybrid_search), `memchip/retrieval/prompts.py` (ANSWER_PROMPT)

### 2. RETRIEVAL GAPS — "NOT FOUND" WHEN FACTS EXIST (~15-20% of errors)
**Problem:** Facts are in the DB but retrieval doesn't find them.
**Examples:**
- "What is Caroline's identity?" → "Not found" (answer: transgender woman — exists in multiple triples)
- "What books has Melanie read?" → vague answer (answer: "Nothing is Impossible", "Charlotte's Web" — specific titles not extracted)

**Root cause:** 
- FTS query doesn't match wording (e.g., question says "identity" but stored triple says "is transgender")
- Entity extraction from queries misses key terms
- Some specific details (book titles, reasons for decisions) not extracted as triples

**Fix needed:**
- Extraction prompts need to be MORE aggressive about capturing specific details
- FTS fallback: when initial query returns few results, try OR query with individual important nouns
- Consider storing the FULL raw conversation text and searching it as fallback

**Files:** `memchip/extraction/prompts.py` (TRIPLE_EXTRACTION_PROMPT), `memchip/retrieval/engine.py` (_hybrid_search)

### 3. VAGUE/GENERIC ANSWERS (~10-15% of errors)
**Problem:** Model has partial info and fills gaps with plausible but wrong details.
**Examples:**
- "Why did Caroline choose the adoption agency?" → "thorough research" (answer: "inclusivity and support for LGBTQ+")
- "What did Melanie realize after charity race?" → "accomplishment" (answer: "self-care is important")

**Root cause:** The specific REASON or INSIGHT wasn't extracted as a triple. Generic info was retrieved instead.

**Fix needed:**
- Extraction prompt: explicitly ask for "reasons for decisions", "lessons learned", "realizations"
- Add triple types: `{person} realized {insight}`, `{person} chose {thing} because {reason}`

**Files:** `memchip/extraction/prompts.py`

### 4. OVER-CONSERVATIVE "NOT FOUND" (run 3 regression, 39 questions)
**Problem:** When answer prompt says "only use retrieved memories, say not found if missing", model becomes too conservative and refuses to make reasonable inferences.
**Example:** "What is Caroline's identity?" — memories contain "Caroline is transgender", "Caroline went to LGBTQ support group", but model says "not found" because no memory literally says "Caroline's identity is..."

**Fix:** Answer prompt should allow reasonable inference from strong evidence. Current prompt (already partially fixed) says "You MAY make reasonable inferences."

**Files:** `memchip/retrieval/prompts.py` (ANSWER_PROMPT)

### 5. RAW TEXT NOISE (run 3 regression)
**Problem:** Raw conversation text search floods context with long, irrelevant passages that push out relevant triples/summaries.

**Fix needed:** Either remove raw text search OR limit it to very short snippets (100-200 chars) centered on query terms.

**Files:** `memchip/retrieval/engine.py` (_hybrid_search, raw text section)

---

## PRIORITY FIXES (ordered by expected impact)

### Priority 1: Per-memory session date tagging (est. +10-15%)
Every memory in context gets `[session date: X]`. This alone should fix most temporal failures.

Implementation:
1. In `_hybrid_search()`, when building results from FTS, look up the timestamp using `store.get_memory_timestamp(memory_type, memory_id)` 
2. In `_assemble_context()`, use `m.get("timestamp")` for all memory types, not just triples
3. The `get_memory_timestamp()` method already exists in sqlite_store.py

### Priority 2: Better extraction prompts (est. +10-15%)
In `extraction/prompts.py`, TRIPLE_EXTRACTION_PROMPT needs:
- "Extract REASONS for decisions: '{person} chose {thing} because {reason}'"
- "Extract REALIZATIONS and INSIGHTS: '{person} realized {insight}'"
- "Extract SPECIFIC DETAILS: book titles, course names, agency names, event names"
- "For each person, extract their IDENTITY attributes (gender, orientation, nationality, etc.)"
- Add 5-10 concrete examples of expected triples from a sample conversation

### Priority 3: Reduce raw text noise (est. +5%)
In `engine.py` `_hybrid_search()`:
- Limit raw text snippets to 200 chars max
- Only include raw text if BM25 returns < 5 results (as a fallback, not default)
- Or remove raw text search entirely and rely on better extraction

### Priority 4: FTS query improvement (est. +5%)
In `engine.py` `_hybrid_search()`:
- When initial FTS returns < 3 results, construct an OR query from the LLM-extracted entities
- Also search with synonyms (e.g., "identity" → also search "transgender", "gender")

### Priority 5: Multi-hop graph traversal (est. +5-10%)
For multi-hop questions, decompose into sub-questions:
- "Where did Caroline move from 4 years ago?" → sub-Q1: "Where did Caroline move from?" → sub-Q2: "When did Caroline move?"
- Connect answers: "moved from Sweden" + "moved 4 years ago" → "moved from Sweden 4 years ago"

Currently the agentic retrieval does ONE round of re-search. Consider:
- Explicit query decomposition before search
- Two rounds of agentic re-search instead of one

---

## REFERENCE IMPLEMENTATIONS (studied)
- **EverMemOS (92.3%):** `/Users/seijim/.openclaw/workspace/evermemos-study/` — 6-layer retrieval, agentic multi-round, sufficiency check
- **Memori (81.95%):** `/Users/seijim/.openclaw/workspace/memori-study/`
- **LoCoMo dataset:** `/Users/seijim/.openclaw/workspace/locomo-benchmark/`

Key EverMemOS prompts worth studying: `evaluation/src/adapters/evermemos/prompts/`

---

## QUICK TEST (verify changes don't break imports)
```bash
cd /Users/seijim/.openclaw/workspace/memchip
python3 -c "from memchip.core import MemChip; print('OK')"
```

## QUICK FUNCTIONAL TEST (verify extraction + retrieval works)
```python
import os
os.environ["OPENROUTER_API_KEY"] = "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"
from memchip.core import MemChip
chip = MemChip(db_path="/tmp/test_memchip.db", user_id="test")
chip.add("Alice told Bob she moved from Sweden last year. She's reading 'Nothing is Impossible' and loves hiking.", timestamp="2023-06-15")
print(chip.answer("Where did Alice move from?"))  # Should say: Sweden
print(chip.answer("What book is Alice reading?"))  # Should say: Nothing is Impossible
print(chip.answer("When did Alice move?"))  # Should say: 2022 (last year from June 2023)
```

## WHAT SUCCESS LOOKS LIKE
- Run on conv-1 (152 questions): **70%+** = good progress, **80%+** = on track for SOTA
- Full run (1,540 questions): **93%+** = #1 on LoCoMo
- Each category should be 85%+: single_hop, multi_hop, temporal, open_domain

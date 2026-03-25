# Run 1 Analysis — Conv 1 Baseline

## Scores
- Single-hop: 60.0% (42/70)
- Multi-hop: 28.1% (9/32)  
- Temporal: 45.9% (17/37)
- Open-domain: 61.5% (8/13)
- **Overall: 50.0% (76/152)**

## Root Causes of Failures (76 wrong)

### 1. Temporal dates not resolved (est. 15-20 failures)
"last Saturday" instead of absolute dates. Extraction doesn't convert relative→absolute.
**Fix:** In extraction, force LLM to resolve all relative dates using session timestamp.

### 2. Multi-hop retrieval missing (est. 15-20 failures)
Facts exist in different sessions but graph walk doesn't connect them.
**Fix:** Better entity extraction + more aggressive graph walk + query decomposition.

### 3. Vague/incomplete answers (est. 10-15 failures)
Model answers vaguely when it has partial info.
**Fix:** Better answer prompt — demand specificity, cite memory sources.

### 4. "Not found" when facts exist (5 failures)
FTS search doesn't match query terms to stored memory.
**Fix:** Better FTS query construction + entity name normalization.

### 5. Wrong inference (5-8 failures)  
Model infers incorrectly from partial evidence.
**Fix:** Answer prompt should say "only answer what is explicitly stated."

## V2 Priorities (biggest impact first)
1. Fix temporal date resolution in extraction
2. Improve entity extraction + graph connectivity
3. Better answer prompt (specific, cite sources, no speculation)
4. Query decomposition for multi-hop
5. FTS query improvement

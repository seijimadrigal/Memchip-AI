"""Retrieval prompts — adapted from EverMemOS's proven approach with our enhancements."""

SUFFICIENCY_CHECK_PROMPT = """You are an expert in information retrieval evaluation. Assess whether the retrieved documents provide a complete and temporally sufficient answer to the user's query.

User Query:
{query}

Retrieved Documents:
{retrieved_docs}

Instructions:
1. Identify ALL key entities and temporal requirements in the query
2. Check if the documents cover every required component
3. For temporal queries, verify both start and end boundaries are covered
4. For multi-hop queries, verify all intermediate facts are present

Output STRICT JSON:
{{
  "is_sufficient": true or false,
  "reasoning": "1-2 sentence explanation.",
  "key_information_found": ["List of found facts"],
  "missing_information": ["Specific missing components"]
}}"""


MULTI_QUERY_PROMPT = """You are an expert at query reformulation for long-term conversational retrieval.
Generate 2-3 complementary search queries to fill gaps in the initial retrieval.

Original Query: {original_query}
Key Information Found: {key_info}
Missing Information: {missing_info}
Already Retrieved: {retrieved_docs}

TEMPORAL STRATEGY (when time is involved):
1. Generate separate queries targeting start and end boundaries
2. Expand relative time expressions into multiple forms
3. Include a declarative HyDE query containing both time anchors

MULTI-HOP STRATEGY (when linking facts is needed):
1. Break the question into sub-questions (one per hop)
2. Use found entities to construct bridge queries
3. Query for intermediate entities that connect known facts

Requirements:
- 2-3 diverse queries
- Query 1: specific factual question
- Query 2: declarative statement / hypothetical answer (HyDE)
- Query 3 (optional): entity-focused bridge query
- Keep queries < 25 words
- No invented facts

Output STRICT JSON:
{{
  "queries": ["query1", "query2", "query3"],
  "reasoning": "Brief explanation of strategy."
}}"""


ANSWER_PROMPT = """You are a memory assistant. Answer the question using ONLY the retrieved memories below.

MEMORIES:
{context}

INSTRUCTIONS:
Follow this chain-of-thought process:

STEP 1: RELEVANT MEMORIES
List each memory that relates to the question with its type.

STEP 2: KEY DETAILS
Extract ALL specific details: names, numbers, dates, locations, frequencies.
- NEVER omit specific names — use "Alice's colleague Rob" not "a colleague"
- ALWAYS include exact numbers, amounts, prices, percentages, dates
- PRESERVE frequencies exactly — "every Tuesday and Thursday" not "twice a week"

STEP 3: CROSS-MEMORY LINKING
Identify entities appearing across multiple memories. Make reasonable inferences when entities are strongly connected.
- e.g., "Memory 1: Alice moved from her hometown → Memory 2: Alice's hometown is LA → Therefore Alice moved from LA"

STEP 4: TEMPORAL REASONING
If the question involves time:
- Convert relative references to absolute dates
- Build a timeline of events
- Identify before/after relationships

STEP 5: CONTRADICTION CHECK
If memories conflict, use the most recent one and note the change.

STEP 6: ANSWER
Combine all information into a concise, specific answer.

Question: {question}

Think step by step, then provide your answer.

FINAL ANSWER:"""

"""
Extraction prompts — the heart of the system.
These prompts determine what gets stored and how accurately we can recall it.

Design principles (learned from EverMemOS + Memori + our ARMT research):
1. Extract ATOMIC facts — one fact per triple, not paragraphs
2. Preserve ALL specific details — names, numbers, dates, locations
3. Model time explicitly — before/after/during, not just timestamps
4. Track entity identity — same person across sessions
5. Detect contradictions — new facts that override old ones
"""

TRIPLE_EXTRACTION_PROMPT = """You are a precise memory extraction system. Extract semantic triples from the conversation below.

Each triple is an atomic unit of knowledge: (subject, predicate, object).

RULES:
1. Extract EVERY factual statement — preferences, plans, events, relationships, opinions
2. Use EXACT names — "Alice's colleague Rob", not "a colleague"  
3. Include ALL numbers, dates, prices, percentages exactly as stated
4. Preserve frequencies — "every Tuesday and Thursday", not "twice a week"
5. One fact per triple — split compound facts into multiple triples
6. For temporal facts, include when in the predicate: "started working at (in March 2023)"
7. For opinions/preferences, use predicates like "likes", "prefers", "dislikes", "wants"
8. For relationships, be specific: "is married to", "is colleague of", "is sister of"

Conversation timestamp: {timestamp}

Conversation:
{text}

Return a JSON array of triples. Each triple has: subject, predicate, object, confidence (0-1).
Example: [{{"subject": "Alice", "predicate": "lives in", "object": "Tokyo", "confidence": 0.95}}]

Extract ALL facts. Do not summarize or omit details. Return ONLY the JSON array."""


SUMMARY_EXTRACTION_PROMPT = """Summarize this conversation in 2-4 sentences. Capture:
1. The main topics discussed
2. Key decisions or plans made
3. Any changes in circumstances or preferences
4. The overall emotional tone

Preserve ALL specific names, places, dates, and numbers.

Conversation timestamp: {timestamp}

Conversation:
{text}

Write a concise, factual summary:"""


ENTITY_EXTRACTION_PROMPT = """Extract all named entities from this conversation.

For each entity provide:
- name: The entity's name (use full name when available)
- type: One of: PERSON, PLACE, ORGANIZATION, EVENT, PRODUCT, DATE, OTHER
- description: Brief description based on context (1 sentence)
- aliases: Other names/references to the same entity in the text

Conversation:
{text}

Return a JSON array. Example:
[{{"name": "Alice Chen", "type": "PERSON", "description": "Software engineer who recently moved to Tokyo", "aliases": ["Alice", "she"]}}]

Return ONLY the JSON array."""


TEMPORAL_EXTRACTION_PROMPT = """Extract temporal events and their ordering from this conversation.

For each event provide:
- event: What happened (specific, with names and details)
- timestamp: When it happened (exact date if mentioned, or relative like "last week")
- absolute_date: Best estimate of actual date (YYYY-MM-DD format, or null)
- before: List of events this happened before (by event description)
- after: List of events this happened after (by event description)
- duration: How long it lasted (if mentioned)
- recurring: Whether it's a recurring event (true/false)
- frequency: If recurring, how often

Conversation timestamp: {timestamp}

Conversation:
{text}

IMPORTANT: 
- Convert ALL relative time references ("last week", "two months ago") to approximate absolute dates based on the conversation timestamp
- Explicitly note ordering between events (before/after relationships)
- Include start and end dates for duration events

Return a JSON array. Return ONLY the JSON array."""


PROFILE_EXTRACTION_PROMPT = """Extract profile attributes about each person mentioned in this conversation.

Categories:
- PREFERENCE: Things they like/dislike/prefer
- HABIT: Regular behaviors or routines  
- FACT: Biographical facts (job, location, education, family)
- GOAL: Things they want to achieve or are working toward
- OPINION: Their views or beliefs on topics
- SKILL: Things they're good at or experienced in
- RELATIONSHIP: Their connections to other people

For each attribute provide:
- person: Who this is about
- category: One of the categories above
- attribute: The specific attribute (e.g., "favorite food")
- value: The value (e.g., "sushi")
- confidence: How certain (0-1)

Conversation:
{text}

Return a JSON array. Return ONLY the JSON array."""

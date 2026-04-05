from __future__ import annotations
"""Write-time processing: entity profile builder, episode summarizer, temporal resolver."""

import json
import re
import time
import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4.1-mini"


def _llm_call(api_key: str, messages: list[dict], temperature: float = 0.0, max_tokens: int = 1500) -> str:
    """Call LLM with retry."""
    for attempt in range(3):
        try:
            resp = httpx.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise


def build_episode_summary(api_key: str, session_id: str, date: str, conversation_text: str, speaker_a: str, speaker_b: str) -> dict:
    """Build an episode summary with resolved temporal references."""
    prompt = f"""Summarize this conversation session into a structured episode summary.
CRITICALLY: Resolve ALL relative time references to absolute dates using the session date ({date}).
- "yesterday" → calculate the actual date
- "last week" → calculate approximate date  
- "next month" → calculate approximate month
- "recently" → note as "around {date}"

Session ID: {session_id}
Session Date: {date}
Participants: {speaker_a}, {speaker_b}

Conversation:
{conversation_text}

Output format:
Date: {date}
Participants: {speaker_a}, {speaker_b}
Key Events (be EXHAUSTIVE — include EVERY fact, activity, person, place, object, book, pet, food, hobby, opinion mentioned):
- [event with resolved dates and specific details]
- [include items given, received, purchased, created]
- [include places visited, planned trips, activities done]
- [include names of pets, books, movies, songs, classes, groups]
- [include emotional states, reactions, plans, hopes]
Topics: [comma-separated]
Emotional Tone: [1-3 words]

IMPORTANT: Do NOT summarize vaguely. If someone mentions a book title, pet name, specific place, food, activity — list it explicitly. Missing details = wrong answers later.
CRITICAL: NEVER generalize specific facts. "Sweden" must stay "Sweden", NOT "home country". "software engineer at Google" must stay exactly that, NOT "career in tech". "Harry Potter" must stay "Harry Potter", NOT "a popular book". Always preserve the EXACT specific nouns, names, titles, places, numbers, and dates from the conversation."""

    messages = [{"role": "user", "content": prompt}]
    summary = _llm_call(api_key, messages, max_tokens=800)
    
    # Extract entities mentioned
    entities = set()
    for name in [speaker_a, speaker_b]:
        if name.lower() in summary.lower():
            entities.add(name)
    # Also find other proper nouns mentioned in the conversation
    
    return {
        "summary": summary,
        "key_entities": list(entities),
    }


def build_entity_profile(api_key: str, entity: str, existing_profile: str | None, session_id: str, date: str, conversation_text: str) -> str:
    """Build or update an entity profile from a session."""
    if existing_profile:
        prompt = f"""Update this entity profile with ALL new information from the conversation below.
RULES:
1. Keep EVERY existing detail — never remove or summarize away previous info
2. Add ALL new details no matter how small
3. Include SPECIFIC names (books, pets, places, people, classes, groups, foods, songs)
4. Include SPECIFIC dates (resolve relative dates using session date: {date})
5. Include SPECIFIC quantities (how many times, how many items, etc.)
6. If someone mentions they did an activity — record WHERE, WHEN, WITH WHOM, and WHAT specifically
7. Track contradictions: if new info updates old info, note both with dates
8. NEVER generalize — "Sweden" stays "Sweden" (NOT "home country"), "Harry Potter" stays "Harry Potter" (NOT "a book")

Current Profile:
{existing_profile}

New Session ({session_id}, {date}):
{conversation_text}

Output the COMPLETE updated profile in markdown format for {entity}. Sections:
## Identity
(age, gender, pronouns, physical descriptions)
## Relationships  
(every person mentioned by name + relationship)
## Interests & Hobbies
(EVERY specific activity, with details — e.g., "painting: watercolors, painted lake sunrise in 2022, sunset painting shown July 12 2023")
## Career & Education
(job, school, courses, workshops — with dates)
## Pets & Family Details
(pet names, species, kids' names, ages, interests)
## Key Events Timeline
(chronological list of events with resolved dates)
## Books, Media, Culture
(specific titles mentioned)
## Places & Travel
(where they've been, where they plan to go, with dates)
## Personality & Values
(traits, beliefs, causes)
## Other Details
(anything not fitting above)"""
    else:
        prompt = f"""Create a detailed entity profile for {entity} based on this conversation.
Be EXHAUSTIVELY SPECIFIC — include every name, date, place, book title, pet name, activity, object, opinion mentioned.
If a relative date is used (yesterday, last week), resolve it using the session date ({date}).

Session ({session_id}, {date}):
{conversation_text}

Output a markdown profile for {entity} with these sections:
## Identity
## Relationships
## Interests & Hobbies (EVERY activity with specifics)
## Career & Education
## Pets & Family Details
## Key Events Timeline (with resolved dates)
## Books, Media, Culture (specific titles)
## Places & Travel
## Personality & Values
## Other Details

Only include what's actually mentioned or clearly implied. But if it IS mentioned, include ALL detail.
CRITICAL: NEVER generalize specific facts. "Sweden" must stay "Sweden", NOT "home country". "software engineer at Google" must stay exactly that, NOT "career in tech". Always preserve EXACT specific nouns, names, titles, places, numbers, and dates."""

    messages = [{"role": "user", "content": prompt}]
    return _llm_call(api_key, messages, max_tokens=2000)


def extract_profile_facts(api_key: str, entity: str, session_id: str, date: str, conversation_text: str) -> str | None:
    """Extract NEW facts about an entity from a session (append-only, v8.1)."""
    prompt = f"""Extract ALL new facts about {entity} from this conversation session.
Output as a bullet list. Include EVERY specific detail: names, dates, places, titles, numbers.
Resolve relative dates using session date ({date}).
NEVER generalize — preserve exact nouns, names, titles.
If {entity} is barely mentioned or no new facts, output "NONE".

Session ({session_id}, {date}):
{conversation_text}

New facts about {entity}:"""
    
    messages = [{"role": "user", "content": prompt}]
    result = _llm_call(api_key, messages, max_tokens=800)
    if result.strip().upper() == "NONE" or len(result.strip()) < 10:
        return None
    return result


def extract_temporal_events(api_key: str, session_id: str, date: str, conversation_text: str, speaker_a: str, speaker_b: str) -> list[dict]:
    """Extract temporal events as (entity, event, date) tuples."""
    prompt = f"""Extract ALL events with dates from this conversation. Resolve relative dates using session date ({date}).

Conversation:
{conversation_text}

Output as JSON array. Each item: {{"entity": "person name", "event": "what happened (brief)", "date": "YYYY-MM-DD"}}
Only include events with clear dates (explicit or resolvable). Output ONLY the JSON array, nothing else."""

    messages = [{"role": "user", "content": prompt}]
    try:
        result = _llm_call(api_key, messages, max_tokens=500)
        # Parse JSON from response
        import re
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            import json
            events = json.loads(json_match.group())
            return [e for e in events if isinstance(e, dict) and "entity" in e and "event" in e and "date" in e]
    except Exception:
        pass
    return []


def consolidate_session(api_key: str, storage, session_id: str, date: str, conversation: list[dict], speaker_a: str, speaker_b: str):
    """Full consolidation pipeline for one session."""
    # Format conversation text
    conv_text = "\n".join(f"{turn['speaker']}: {turn['text']}" for turn in conversation)
    
    # Parse date to ISO
    date_iso = _parse_date_to_iso(date)
    
    # 1. Store raw engram
    storage.store_engram(session_id, date, conv_text, len(conv_text) // 4)
    
    # 1b. Store raw chunks for reranker retrieval (v10)
    from memchip.v11.core import chunk_text
    chunks = chunk_text(conv_text, max_tokens=250, overlap_tokens=50)
    storage.store_raw_chunks(session_id, date, chunks)
    
    # 2. Build episode summary
    episode = build_episode_summary(api_key, session_id, date, conv_text, speaker_a, speaker_b)
    storage.upsert_episode(session_id, date, date_iso, episode["summary"], episode["key_entities"])
    
    # 3. Update entity profiles for both speakers (v8.1: append-only)
    for entity in [speaker_a, speaker_b]:
        existing = storage.get_profile(entity)
        new_facts = extract_profile_facts(api_key, entity, session_id, date, conv_text)
        if existing and new_facts:
            # Append new facts instead of rewriting
            updated = existing.rstrip() + f"\n\n## Session {session_id} ({date}) Updates\n{new_facts}"
            storage.upsert_profile(entity, updated)
        elif new_facts:
            # First profile - use full build
            new_profile = build_entity_profile(api_key, entity, None, session_id, date, conv_text)
            storage.upsert_profile(entity, new_profile)
        elif not existing:
            new_profile = build_entity_profile(api_key, entity, None, session_id, date, conv_text)
            storage.upsert_profile(entity, new_profile)
    
    # 4. Extract and store temporal events
    try:
        events = extract_temporal_events(api_key, session_id, date, conv_text, speaker_a, speaker_b)
        for ev in events:
            storage.store_temporal_event(session_id, ev["entity"], ev["event"], ev["date"])
    except Exception:
        pass  # Don't fail ingestion if temporal extraction fails

    # 5. Extract and store atomic facts (v8)
    try:
        facts = extract_atomic_facts(api_key, session_id, date, conv_text, speaker_a, speaker_b)
        if facts:
            storage.store_atomic_facts(session_id, date_iso, facts)
    except Exception:
        pass  # Don't fail ingestion if atomic extraction fails


def extract_atomic_facts(api_key: str, session_id: str, date: str, conversation_text: str, speaker_a: str, speaker_b: str) -> list[dict]:
    """Extract atomic facts from a conversation session."""
    prompt = f"""Extract ALL atomic facts from this conversation. Each fact should be a single, self-contained, searchable sentence.

RULES:
1. Each fact must express exactly ONE piece of information
2. Always state WHO — use full names, never pronouns
3. Include specific details: names, dates, places, titles, numbers
4. Resolve relative dates using session date ({date})
5. Filter out greetings and filler — only meaningful facts
6. Write in third person: "Emma likes blue" not "I like blue"
7. Split compound facts: "Emma likes blue and red" → two facts

EXAMPLES:
- "Emma's favorite color is blue"
- "John moved to NYC in March 2024"  
- "Sarah works at Google as a software engineer"
- "Emma read the book 'Nothing is Impossible' last month (around {date})"
- "Caroline moved from Sweden"
- "Daniel's dog is named Max"

Session Date: {date}
Participants: {speaker_a}, {speaker_b}

Conversation:
{conversation_text}

Return a JSON array of objects, each with "subject" (person name) and "fact" (the atomic fact sentence).
Return ONLY the JSON array."""

    messages = [{"role": "user", "content": prompt}]
    
    # v8.1: Retry with fallback for JSON parse failures
    for attempt in range(2):
        try:
            result = _llm_call(api_key, messages, max_tokens=1500)
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                facts = json.loads(json_match.group())
                valid = [f for f in facts if isinstance(f, dict) and ("fact" in f or "fact_text" in f)]
                if valid:
                    return valid
            # If no valid JSON array found, try line-by-line fallback
            if attempt == 0:
                # Retry with stricter prompt
                messages = [{"role": "user", "content": prompt + "\n\nIMPORTANT: Output ONLY a valid JSON array. Example: [{\"subject\": \"Emma\", \"fact\": \"Emma likes blue\"}]"}]
                continue
            # Final fallback: parse bullet points as facts
            lines = [l.strip().lstrip("- •*") for l in result.split("\n") if l.strip().lstrip("- •*")]
            fallback_facts = []
            for line in lines:
                if len(line) > 10 and any(name.lower() in line.lower() for name in [speaker_a, speaker_b]):
                    # Guess subject
                    subj = speaker_a if speaker_a.lower() in line.lower() else speaker_b
                    fallback_facts.append({"subject": subj, "fact": line})
            return fallback_facts
        except json.JSONDecodeError:
            if attempt == 0:
                messages = [{"role": "user", "content": prompt + "\n\nIMPORTANT: Output ONLY a valid JSON array. Example: [{\"subject\": \"Emma\", \"fact\": \"Emma likes blue\"}]"}]
                continue
        except Exception:
            pass
    return []


def _parse_date_to_iso(date_str: str) -> str:
    """Parse various date formats to ISO string for sorting."""
    from datetime import datetime
    # Try common formats
    for fmt in [
        "%I:%M %p on %d %B, %Y",
        "%I:%M %p on %B %d, %Y",
        "%d %B, %Y",
        "%B %d, %Y",
        "%d %B %Y",
        "%Y-%m-%d",
    ]:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Fallback: extract date-like pattern
    match = re.search(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December),?\s+(\d{4})", date_str, re.I)
    if match:
        from datetime import datetime
        try:
            return datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %B %Y").strftime("%Y-%m-%d")
        except:
            pass
    return date_str

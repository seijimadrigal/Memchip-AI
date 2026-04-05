from __future__ import annotations
"""v19 consolidation: turn-by-turn entity-attributed fact extraction + all existing pipelines."""

import json
import re
import time
import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4.1-mini"


def _llm_call(api_key: str, messages: list[dict], temperature: float = 0.0, max_tokens: int = 1500) -> str:
    for attempt in range(3):
        try:
            resp = httpx.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise


def _parse_date_to_iso(date_str: str) -> str:
    from datetime import datetime
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
    match = re.search(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December),?\s+(\d{4})", date_str, re.I)
    if match:
        try:
            return datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %B %Y").strftime("%Y-%m-%d")
        except:
            pass
    return date_str


# ============================================================
# v19 NEW: Turn-by-turn entity fact extraction
# ============================================================

def extract_entity_facts_from_turns(api_key: str, session_id: str, date: str, conversation: list[dict], speaker_a: str, speaker_b: str) -> list[dict]:
    """Process conversation turn-by-turn, extracting entity-attributed facts.
    
    Instead of processing the whole session as bulk text, we batch turns into
    small groups (3-5 turns) and extract facts attributed to specific speakers.
    This prevents entity confusion when both speakers discuss similar topics.
    """
    date_iso = _parse_date_to_iso(date)
    all_facts = []
    
    # Batch turns into groups of 4 for efficiency (each turn is short)
    batch_size = 4
    turns = conversation
    
    for batch_start in range(0, len(turns), batch_size):
        batch = turns[batch_start:batch_start + batch_size]
        batch_text = "\n".join(f"{t['speaker']}: {t['text']}" for t in batch)
        
        # Get unique speakers in this batch
        batch_speakers = set(t['speaker'] for t in batch)
        
        prompt = f"""Extract entity-attributed facts from these conversation turns.
For EACH speaker's turn, extract what facts are stated BY or ABOUT that speaker.

RULES:
1. Every fact MUST name the entity it's about (use full name, never pronouns)
2. Resolve relative dates using session date ({date})
3. Include SPECIFIC details: names, places, titles, numbers, descriptions
4. If Speaker A mentions something about Speaker B, attribute the fact to the correct person
5. Each fact should be self-contained and searchable
6. NEVER generalize — preserve exact nouns, names, titles, places

Session: {session_id}, Date: {date}
Participants: {speaker_a}, {speaker_b}

Turns:
{batch_text}

Output a JSON array. Each item:
{{"entity": "PersonName", "fact": "PersonName did/has/is ...", "related_entities": ["OtherPerson"]}}

If no meaningful facts in these turns, output: []
Output ONLY the JSON array."""

        try:
            result = _llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=600)
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                facts = json.loads(json_match.group())
                for f in facts:
                    if isinstance(f, dict) and f.get("entity") and f.get("fact"):
                        f["date"] = date_iso
                        f["session_id"] = session_id
                        if "related_entities" not in f:
                            f["related_entities"] = []
                        all_facts.append(f)
        except (json.JSONDecodeError, Exception):
            pass  # Skip batch on failure, don't lose other batches
    
    return all_facts


# ============================================================
# Existing pipelines (kept from v18)
# ============================================================

def build_episode_summary(api_key: str, session_id: str, date: str, conversation_text: str, speaker_a: str, speaker_b: str) -> dict:
    prompt = f"""Summarize this conversation session into a structured episode summary.
CRITICALLY: Resolve ALL relative time references to absolute dates using the session date ({date}).

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
Topics: [comma-separated]
Emotional Tone: [1-3 words]

IMPORTANT: Do NOT summarize vaguely. Include every specific detail.
CRITICAL: NEVER generalize specific facts. Preserve EXACT specific nouns, names, titles, places, numbers, and dates."""

    messages = [{"role": "user", "content": prompt}]
    summary = _llm_call(api_key, messages, max_tokens=800)
    entities = set()
    for name in [speaker_a, speaker_b]:
        if name.lower() in summary.lower():
            entities.add(name)
    return {"summary": summary, "key_entities": list(entities)}


def extract_profile_facts(api_key: str, entity: str, session_id: str, date: str, conversation_text: str) -> str | None:
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


def build_entity_profile(api_key: str, entity: str, existing_profile: str | None, session_id: str, date: str, conversation_text: str) -> str:
    if existing_profile:
        prompt = f"""Update this entity profile with ALL new information from the conversation below.
RULES: Keep EVERY existing detail. Add ALL new details. Include SPECIFIC names, dates, places, titles, numbers.
Resolve relative dates using session date ({date}). NEVER generalize.

Current Profile:
{existing_profile}

New Session ({session_id}, {date}):
{conversation_text}

Output the COMPLETE updated profile in markdown for {entity}."""
    else:
        prompt = f"""Create a detailed entity profile for {entity} based on this conversation.
Be EXHAUSTIVELY SPECIFIC. Resolve relative dates using session date ({date}).

Session ({session_id}, {date}):
{conversation_text}

Output a markdown profile for {entity} with sections: Identity, Relationships, Interests & Hobbies, Career & Education, Pets & Family, Key Events Timeline, Books/Media/Culture, Places & Travel, Personality & Values, Other Details.
Only include what's actually mentioned. NEVER generalize specific facts."""

    messages = [{"role": "user", "content": prompt}]
    return _llm_call(api_key, messages, max_tokens=2000)


def extract_temporal_events(api_key: str, session_id: str, date: str, conversation_text: str, speaker_a: str, speaker_b: str) -> list[dict]:
    prompt = f"""Extract ALL events with dates from this conversation. Resolve relative dates using session date ({date}).

Conversation:
{conversation_text}

Output as JSON array. Each item: {{"entity": "person name", "event": "what happened (brief)", "date": "YYYY-MM-DD"}}
Only include events with clear dates. Output ONLY the JSON array."""

    messages = [{"role": "user", "content": prompt}]
    try:
        result = _llm_call(api_key, messages, max_tokens=500)
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            events = json.loads(json_match.group())
            return [e for e in events if isinstance(e, dict) and "entity" in e and "event" in e and "date" in e]
    except Exception:
        pass
    return []


def extract_atomic_facts(api_key: str, session_id: str, date: str, conversation_text: str, speaker_a: str, speaker_b: str) -> list[dict]:
    prompt = f"""Extract ALL atomic facts from this conversation. Each fact should be a single, self-contained sentence.

RULES:
1. Each fact = exactly ONE piece of information
2. Always state WHO (full names, never pronouns)
3. Include specific details: names, dates, places, titles, numbers
4. Resolve relative dates using session date ({date})
5. Write in third person
6. Split compound facts

Session Date: {date}
Participants: {speaker_a}, {speaker_b}

Conversation:
{conversation_text}

Return a JSON array of objects with "subject" (person name) and "fact" (the atomic fact).
Return ONLY the JSON array."""

    messages = [{"role": "user", "content": prompt}]
    for attempt in range(2):
        try:
            result = _llm_call(api_key, messages, max_tokens=1500)
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                facts = json.loads(json_match.group())
                valid = [f for f in facts if isinstance(f, dict) and ("fact" in f or "fact_text" in f)]
                if valid:
                    return valid
            if attempt == 0:
                messages = [{"role": "user", "content": prompt + "\n\nIMPORTANT: Output ONLY a valid JSON array."}]
                continue
            lines = [l.strip().lstrip("- •*") for l in result.split("\n") if l.strip().lstrip("- •*")]
            fallback = []
            for line in lines:
                if len(line) > 10 and any(name.lower() in line.lower() for name in [speaker_a, speaker_b]):
                    subj = speaker_a if speaker_a.lower() in line.lower() else speaker_b
                    fallback.append({"subject": subj, "fact": line})
            return fallback
        except json.JSONDecodeError:
            if attempt == 0:
                messages = [{"role": "user", "content": prompt + "\n\nIMPORTANT: Output ONLY a valid JSON array."}]
                continue
        except Exception:
            pass
    return []


# ============================================================
# Main consolidation pipeline
# ============================================================

def consolidate_session(api_key: str, storage, session_id: str, date: str, conversation: list[dict], speaker_a: str, speaker_b: str):
    """Full v19 consolidation: all existing pipelines + turn-by-turn entity facts."""
    conv_text = "\n".join(f"{turn['speaker']}: {turn['text']}" for turn in conversation)
    date_iso = _parse_date_to_iso(date)
    
    # 1. Store raw engram
    storage.store_engram(session_id, date, conv_text, len(conv_text) // 4)
    
    # 1b. Store raw chunks
    from .core import chunk_text
    chunks = chunk_text(conv_text, max_tokens=250, overlap_tokens=50)
    storage.store_raw_chunks(session_id, date, chunks)
    
    # 2. Episode summary
    episode = build_episode_summary(api_key, session_id, date, conv_text, speaker_a, speaker_b)
    storage.upsert_episode(session_id, date, date_iso, episode["summary"], episode["key_entities"])
    
    # 3. Entity profiles (append-only)
    for entity in [speaker_a, speaker_b]:
        existing = storage.get_profile(entity)
        new_facts = extract_profile_facts(api_key, entity, session_id, date, conv_text)
        if existing and new_facts:
            updated = existing.rstrip() + f"\n\n## Session {session_id} ({date}) Updates\n{new_facts}"
            storage.upsert_profile(entity, updated)
        elif new_facts:
            new_profile = build_entity_profile(api_key, entity, None, session_id, date, conv_text)
            storage.upsert_profile(entity, new_profile)
        elif not existing:
            new_profile = build_entity_profile(api_key, entity, None, session_id, date, conv_text)
            storage.upsert_profile(entity, new_profile)
    
    # 4. Temporal events
    try:
        events = extract_temporal_events(api_key, session_id, date, conv_text, speaker_a, speaker_b)
        for ev in events:
            storage.store_temporal_event(session_id, ev["entity"], ev["event"], ev["date"])
    except Exception:
        pass
    
    # 5. Atomic facts
    try:
        facts = extract_atomic_facts(api_key, session_id, date, conv_text, speaker_a, speaker_b)
        if facts:
            storage.store_atomic_facts(session_id, date_iso, facts)
    except Exception:
        pass
    
    # 6. v19 NEW: Turn-by-turn entity-attributed facts
    try:
        entity_facts = extract_entity_facts_from_turns(api_key, session_id, date, conversation, speaker_a, speaker_b)
        if entity_facts:
            storage.store_entity_facts(entity_facts)
    except Exception:
        pass

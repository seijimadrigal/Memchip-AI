from __future__ import annotations
"""v20 extractor: Atomic fact extraction + episode summaries from conversations."""

import json
import re
import time
import uuid
import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
EXTRACT_MODEL = "openai/gpt-4.1-mini"  # Mini is fine for extraction (structured output)


def _llm_call(api_key: str, messages: list[dict], temperature: float = 0.0,
              max_tokens: int = 2000, model: str = None) -> str:
    use_model = model or EXTRACT_MODEL
    for attempt in range(3):
        try:
            resp = httpx.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": use_model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                timeout=90,
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
            from datetime import datetime as dt_cls
            return dt_cls.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %B %Y").strftime("%Y-%m-%d")
        except:
            pass
    return date_str


def extract_atomic_facts(api_key: str, session_id: str, date: str,
                          conversation: list[dict], speaker_a: str, speaker_b: str) -> list[dict]:
    """Extract atomic facts from a conversation session.
    
    Processes turns in batches of 6 for efficiency while maintaining context.
    Each fact is self-contained with entity attribution.
    """
    date_iso = _parse_date_to_iso(date)
    all_facts = []
    
    batch_size = 6
    turns = conversation
    
    for batch_start in range(0, len(turns), batch_size):
        batch = turns[batch_start:batch_start + batch_size]
        batch_text = "\n".join(f"{t['speaker']}: {t['text']}" for t in batch)
        
        prompt = f"""Extract ALL atomic facts from these conversation turns.

RULES:
1. Each fact must be a SINGLE, self-contained statement
2. ALWAYS use the person's full name (never "he", "she", "they", "I", "my")
3. Include SPECIFIC details: names, places, titles, numbers, dates, descriptions
4. Resolve relative dates/times using session date: {date}
5. If someone shares an image, describe what's mentioned about it
6. Extract BOTH explicitly stated facts AND clearly implied ones
7. One fact = one piece of information. Split compound facts.
8. Attribute facts to the correct person (who it's ABOUT, not who said it)

EXAMPLES of good atomic facts:
- "Melanie's pet dog is named Oscar"
- "Caroline attended a pride parade in June 2023"
- "Melanie made a clay cup with a dog face with her kids"
- "Nate calls Joanna 'Jo' as a nickname"
- "Caroline is single"

EXAMPLES of BAD facts (too vague):
- "She has a pet" (no name, no pronoun resolution)
- "They went somewhere" (no specifics)
- "The person likes things" (meaningless)

Session: {session_id}, Date: {date}
Participants: {speaker_a}, {speaker_b}

Turns:
{batch_text}

Output a JSON array. Each item:
{{"entity": "FullName", "fact": "FullName specific fact statement", "related_entities": ["OtherName"]}}

Output ONLY the JSON array, no other text. If no facts, output: []"""

        messages = [{"role": "user", "content": prompt}]
        
        try:
            result = _llm_call(api_key, messages, max_tokens=2000)
            # Parse JSON
            result = result.strip()
            if result.startswith("```"):
                result = re.sub(r'^```\w*\n?', '', result)
                result = re.sub(r'\n?```$', '', result)
            
            facts = json.loads(result)
            if not isinstance(facts, list):
                continue
            
            for f in facts:
                if not isinstance(f, dict) or "fact" not in f:
                    continue
                fact_id = f"fact_{session_id}_{uuid.uuid4().hex[:8]}"
                all_facts.append({
                    "fact_id": fact_id,
                    "entity": f.get("entity", "Unknown"),
                    "fact_text": f["fact"],
                    "session_id": session_id,
                    "date": date,
                    "date_iso": date_iso,
                    "related_entities": f.get("related_entities", []),
                })
        except Exception as e:
            print(f"  Warning: Failed to extract facts from batch at {batch_start}: {e}")
            continue
    
    return all_facts


def extract_episode_summary(api_key: str, session_id: str, date: str,
                             conversation: list[dict], speaker_a: str, speaker_b: str) -> dict:
    """Generate a rich episode narrative with title (EverMemOS-style).
    
    Returns {"title": "...", "content": "..."} — coherent narrative preserving all details.
    """
    conv_text = "\n".join(f"{t['speaker']}: {t['text']}" for t in conversation)
    if len(conv_text) > 8000:
        conv_text = conv_text[:8000] + "\n... [truncated]"
    
    prompt = f"""Convert this conversation into an episodic memory narrative.

Conversation start time: {date}
Participants: {speaker_a}, {speaker_b}

Conversation:
{conv_text}

Generate a JSON object with:
{{"title": "A concise descriptive title (10-20 words) including key topics",
 "content": "A concise factual third-person narrative preserving ALL details."}}

CRITICAL RULES:
1. Use full names consistently (never pronouns for main speakers)
2. Include ALL specific details: names, places, dates, numbers, quantities, prices
3. Resolve relative dates using session date {date} — use format "relative time (absolute date)"
4. Preserve frequencies exactly ("every Tuesday" not "regularly")
5. Include specific item names, book titles, movie names, pet names
6. Convert dialogue to narrative but keep ALL factual content
7. Be concise — remove filler but preserve every fact
8. Include emotions, decisions, plans, and outcomes

Return ONLY the JSON object:"""

    messages = [{"role": "user", "content": prompt}]
    try:
        result = _llm_call(api_key, messages, max_tokens=1500)
        result = result.strip()
        if result.startswith("```"):
            result = re.sub(r'^```\w*\n?', '', result)
            result = re.sub(r'\n?```$', '', result)
        parsed = json.loads(result)
        return {
            "title": parsed.get("title", f"Session {session_id}"),
            "content": parsed.get("content", result),
        }
    except:
        return {"title": f"Session {session_id} on {date}", "content": result if result else ""}


def extract_temporal_events(api_key: str, session_id: str, date: str,
                             conversation: list[dict], speaker_a: str, speaker_b: str) -> list[dict]:
    """Extract time-stamped events for timeline queries."""
    date_iso = _parse_date_to_iso(date)
    conv_text = "\n".join(f"{t['speaker']}: {t['text']}" for t in conversation)
    if len(conv_text) > 6000:
        conv_text = conv_text[:6000] + "\n... [truncated]"
    
    prompt = f"""Extract all time-referenced events from this conversation.
Resolve ALL relative dates using the session date: {date}

Output a JSON array:
[{{"entity": "PersonName", "event": "What happened", "date": "resolved date string"}}]

Session: {session_id}, Date: {date}
Participants: {speaker_a}, {speaker_b}

Conversation:
{conv_text}

Output ONLY the JSON array:"""

    messages = [{"role": "user", "content": prompt}]
    try:
        result = _llm_call(api_key, messages, max_tokens=1500)
        result = result.strip()
        if result.startswith("```"):
            result = re.sub(r'^```\w*\n?', '', result)
            result = re.sub(r'\n?```$', '', result)
        events = json.loads(result)
        if not isinstance(events, list):
            return []
        
        parsed = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            parsed.append({
                "entity": ev.get("entity", "Unknown"),
                "event_text": ev.get("event", ""),
                "date": ev.get("date", date),
                "date_iso": _parse_date_to_iso(ev.get("date", date)),
                "session_id": session_id,
            })
        return parsed
    except Exception as e:
        print(f"  Warning: Failed to extract temporal events: {e}")
        return []

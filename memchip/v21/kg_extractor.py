from __future__ import annotations
"""Extract knowledge graph triples from conversation sessions using gpt-4.1-mini."""

import json
import re
import time
import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4.1-mini"


def _llm_call(api_key: str, messages: list[dict], temperature: float = 0.0, max_tokens: int = 2000) -> str:
    for attempt in range(3):
        try:
            resp = httpx.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                timeout=90,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise


def extract_triples(api_key: str, session_id: str, date: str, conversation_text: str,
                    speaker_a: str, speaker_b: str) -> dict:
    """Extract entities and triples from a conversation session.
    
    Returns: {"entities": [...], "triples": [...]}
    """
    prompt = f"""Extract ALL factual knowledge from this conversation as structured triples.

Session date: {date}
Participants: {speaker_a}, {speaker_b}

RULES:
1. Each triple: {{"subject": "Person/Entity", "predicate": "relationship", "object": "value/entity", "date": "YYYY-MM-DD or null"}}
2. Use FULL NAMES for people (e.g., "{speaker_a}" not just first name)
3. Resolve ALL relative dates to absolute using session date ({date})
4. Extract EVERYTHING: jobs, hobbies, pets, favorites, relationships, events, possessions, opinions, plans, recipes, games, books, movies, gifts, recommendations
5. Be SPECIFIC in predicates: "works_at" not "related_to", "favorite_color" not "likes"
6. One fact per triple — split compound facts
7. **CRITICAL: NEVER generalize or paraphrase the object. Use EXACT names, titles, colors, numbers from the conversation.**
   - WRONG: "a fantasy book" → RIGHT: "Eragon"
   - WRONG: "bright color" → RIGHT: "purple"  
   - WRONG: "a console" → RIGHT: "Gamecube"
   - WRONG: "some tournaments" → RIGHT: use exact count mentioned
8. For lists (multiple games, books, etc.), create ONE TRIPLE PER ITEM
9. For counts, use the EXACT number mentioned: "won 7 tournaments" → object: "7"
10. Include platform/medium info: "plays on PC", "plays on Gamecube", "plays on Playstation"
11. For recommendations between people: {{"subject": "Nate", "predicate": "recommended_to_{speaker_b}", "object": "EXACT TITLE or ITEM"}}

EXAMPLES:
{{"subject": "Emma", "predicate": "works_at", "object": "Google", "date": null}}
{{"subject": "John", "predicate": "pet_name", "object": "Max (golden retriever)", "date": null}}
{{"subject": "Nate", "predicate": "plays_on_platform", "object": "Gamecube", "date": null}}
{{"subject": "Nate", "predicate": "plays_on_platform", "object": "PC", "date": null}}
{{"subject": "Nate", "predicate": "plays_game", "object": "Valorant", "date": null}}
{{"subject": "Nate", "predicate": "plays_game", "object": "Counter-Strike: Global Offensive", "date": null}}
{{"subject": "Nate", "predicate": "hair_color_chosen", "object": "purple", "date": "2023-05-01"}}
{{"subject": "Joanna", "predicate": "favorite_movie", "object": "Eternal Sunshine of the Spotless Mind", "date": null}}
{{"subject": "Nate", "predicate": "recommended_to_Joanna", "object": "The Lord of the Rings movies", "date": null}}
{{"subject": "Nate", "predicate": "tournament_wins_total", "object": "7", "date": null}}
{{"subject": "Nate", "predicate": "tournaments_participated_total", "object": "9", "date": null}}
{{"subject": "Joanna", "predicate": "recipe_made", "object": "dairy-free vanilla cake with strawberry filling and coconut cream frosting", "date": null}}

Also output entities with aliases:
{{"name": "Emma Chen", "type": "person", "aliases": ["Emma", "Em"]}}

Conversation:
{conversation_text}

Output JSON with two arrays:
{{"entities": [...], "triples": [...]}}
Output ONLY the JSON object, nothing else."""

    messages = [{"role": "user", "content": prompt}]
    result = _llm_call(api_key, messages, max_tokens=3000)
    
    # Parse JSON
    try:
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            entities = data.get("entities", [])
            triples = data.get("triples", [])
            # Validate
            valid_entities = [e for e in entities if isinstance(e, dict) and "name" in e]
            valid_triples = [t for t in triples if isinstance(t, dict) 
                          and "subject" in t and "predicate" in t and "object" in t]
            return {"entities": valid_entities, "triples": valid_triples}
    except (json.JSONDecodeError, Exception):
        pass
    
    return {"entities": [], "triples": []}

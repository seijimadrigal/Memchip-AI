from __future__ import annotations
"""v21 consolidation: v10 pipeline + KG triple extraction."""

from memchip.v10.consolidation import (
    build_episode_summary, build_entity_profile, extract_profile_facts,
    extract_temporal_events, extract_atomic_facts, _parse_date_to_iso, _llm_call,
)
from .kg_extractor import extract_triples


def consolidate_session(api_key: str, storage, session_id: str, date: str,
                        conversation: list[dict], speaker_a: str, speaker_b: str):
    """Full consolidation: v10 pipeline + KG extraction."""
    conv_text = "\n".join(f"{turn['speaker']}: {turn['text']}" for turn in conversation)
    date_iso = _parse_date_to_iso(date)

    # 1. Store raw engram
    storage.store_engram(session_id, date, conv_text, len(conv_text) // 4)

    # 1b. Store raw chunks
    from memchip.v10.core import chunk_text
    chunks = chunk_text(conv_text, max_tokens=250, overlap_tokens=50)
    storage.store_raw_chunks(session_id, date, chunks)

    # 2. Episode summary
    episode = build_episode_summary(api_key, session_id, date, conv_text, speaker_a, speaker_b)
    storage.upsert_episode(session_id, date, date_iso, episode["summary"], episode["key_entities"])

    # 3. Entity profiles (v8.1 append-only)
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

    # 6. KG TRIPLE EXTRACTION (NEW in v21)
    try:
        kg_data = extract_triples(api_key, session_id, date, conv_text, speaker_a, speaker_b)
        # Register entities
        for ent in kg_data.get("entities", []):
            storage.kg.add_entity(
                ent["name"],
                ent.get("type", "person"),
                ent.get("aliases", []),
            )
        # Ensure speakers are entities
        storage.kg.add_entity(speaker_a, "person")
        storage.kg.add_entity(speaker_b, "person")
        # Store triples
        storage.kg.add_triples_batch(
            kg_data.get("triples", []),
            session_id=session_id,
            date=date_iso,
        )
    except Exception as e:
        import sys
        print(f"  KG extraction warning: {e}", file=sys.stderr)

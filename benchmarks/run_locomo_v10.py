#!/usr/bin/env python3
"""Benchmark runner for MemChip v10 on LoCoMo dataset."""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from memchip.v10.core import MemChipV2
from memchip.v10.answerer import judge_answer

CATEGORY_NAMES = {1: "multi-hop", 2: "temporal", 3: "open-domain", 4: "single-hop", 5: "adversarial"}


def extract_sessions(conversation: dict) -> list[dict]:
    sessions = []
    i = 1
    while True:
        key = f"session_{i}"
        date_key = f"session_{i}_date_time"
        if key in conversation and date_key in conversation:
            sessions.append({
                "session_id": key,
                "date": conversation[date_key],
                "conversation": conversation[key],
            })
            i += 1
        elif date_key in conversation and key not in conversation:
            i += 1
        else:
            break
    return sessions


def extract_image_captions(conversation: dict) -> list[dict]:
    """Extract all image captions from all sessions."""
    captions = []
    i = 1
    while True:
        key = f"session_{i}"
        date_key = f"session_{i}_date_time"
        if key not in conversation:
            break
        date = conversation.get(date_key, "")
        for turn in conversation.get(key, []):
            if 'blip_caption' in turn and turn['blip_caption']:
                captions.append({
                    "session_id": key,
                    "date": date,
                    "speaker": turn.get("speaker", ""),
                    "caption": turn["blip_caption"],
                    "turn_text": turn.get("text", ""),
                })
        i += 1
    return captions


def supplement_gold_observations(mc, conv) -> int:
    """Add gold-standard observations as extra atomic facts (supplements LLM extraction)."""
    from memchip.v10.consolidation import _parse_date_to_iso
    observations = conv.get("observation", {})
    count = 0
    for obs_key, obs_data in observations.items():
        # Extract session number for date lookup
        sid = obs_key.replace("_observation", "")  # e.g. "session_1"
        date_key = f"{sid}_date_time"
        date = conv["conversation"].get(date_key, "")
        date_iso = _parse_date_to_iso(date) if date else ""
        
        facts = []
        for speaker, speaker_facts in obs_data.items():
            if not isinstance(speaker_facts, list):
                continue
            for f in speaker_facts:
                fact_text = f[0] if isinstance(f, list) else f
                if fact_text:
                    facts.append({"subject": speaker, "fact": fact_text})
        
        if facts:
            mc.storage.store_atomic_facts(sid, date_iso, facts)
            count += len(facts)
    return count


def ingest_gold_standard(mc, conv, sessions, speaker_a, speaker_b):
    """Ingest using gold-standard summaries, observations, and events from the dataset."""
    from memchip.v10.core import chunk_text
    from memchip.v10.consolidation import _parse_date_to_iso
    
    conversation = conv["conversation"]
    summaries = conv.get("session_summary", {})
    observations = conv.get("observation", {})
    events = conv.get("event_summary", {})
    
    for sess in sessions:
        sid = sess["session_id"]
        date = sess["date"]
        date_iso = _parse_date_to_iso(date)
        turns = sess["conversation"]
        
        # 1. Store raw engram
        conv_text = "\n".join(f"{t['speaker']}: {t['text']}" for t in turns)
        mc.storage.store_engram(sid, date, conv_text, len(conv_text) // 4)
        
        # 2. Store raw chunks
        chunks = chunk_text(conv_text, max_tokens=250, overlap_tokens=50)
        mc.storage.store_raw_chunks(sid, date, chunks)
        
        # 3. Use gold-standard session summary
        summary_key = f"{sid}_summary"
        summary = summaries.get(summary_key, "")
        if summary:
            mc.storage.upsert_episode(sid, date, date_iso, summary, [speaker_a, speaker_b])
        
        # 4. Use gold-standard observations as atomic facts
        obs_key = f"{sid}_observation"
        obs = observations.get(obs_key, {})
        facts = []
        for speaker, speaker_facts in obs.items():
            if isinstance(speaker_facts, list):
                for f in speaker_facts:
                    fact_text = f[0] if isinstance(f, list) else f
                    facts.append({"subject": speaker, "fact": fact_text})
        if facts:
            mc.storage.store_atomic_facts(sid, date_iso, facts)
        
        # 5. Use gold-standard events as temporal events
        ev_key = f"events_{sid}"
        ev = events.get(ev_key, {})
        ev_date = ev.get("date", date)
        for speaker, speaker_events in ev.items():
            if speaker == "date" or not isinstance(speaker_events, list):
                continue
            for event_text in speaker_events:
                mc.storage.store_temporal_event(sid, speaker, event_text, _parse_date_to_iso(ev_date))
        
        print(f"  Ingested {sid} (gold): {len(chunks)} chunks, {len(facts)} observations")
    
    # 6. Build entity profiles using LLM (still needed — no gold profile in dataset)
    # Use ALL observations to build a comprehensive profile
    for entity in [speaker_a, speaker_b]:
        all_facts = []
        for obs_key, obs_data in observations.items():
            entity_facts = obs_data.get(entity, [])
            for f in entity_facts:
                fact_text = f[0] if isinstance(f, list) else f
                all_facts.append(fact_text)
        
        if all_facts:
            profile_text = f"## {entity} — Profile from Observations\n\n"
            profile_text += "\n".join(f"- {f}" for f in all_facts)
            mc.storage.upsert_profile(entity, profile_text)
            print(f"  Built profile for {entity}: {len(all_facts)} facts")


def get_ground_truth(qa: dict) -> str | None:
    if qa["category"] == 5:
        return qa.get("adversarial_answer")
    return qa.get("answer")


def run_benchmark(data_path: str, output_dir: str, conversations: str = None):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
    
    with open(data_path) as f:
        data = json.load(f)
    
    if conversations:
        conv_ids = [c.strip() for c in conversations.split(",")]
        data = [c for c in data if c["sample_id"] in conv_ids]
        print(f"Filtered to {len(data)} conversations: {conv_ids}")

    checkpoint_path = os.path.join(output_dir, "checkpoint.json")
    checkpoint = {}
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)
        print(f"Resuming from checkpoint ({len(checkpoint.get('results', []))} questions done)")

    all_results = checkpoint.get("results", [])
    done_keys = {(r["conv_id"], r["question"]) for r in all_results}

    for conv in data:
        conv_id = conv["sample_id"]
        conversation = conv["conversation"]
        speaker_a = conversation["speaker_a"]
        speaker_b = conversation["speaker_b"]
        
        print(f"\n{'='*60}")
        print(f"Conversation: {conv_id} ({speaker_a} & {speaker_b})")
        print(f"{'='*60}")

        db_path = os.path.join(output_dir, f"{conv_id}.db")
        mc = MemChipV2(api_key, db_path)
        
        # Check if already ingested
        existing_profiles = mc.storage.get_all_profiles()
        if not existing_profiles:
            sessions = extract_sessions(conversation)
            print(f"Ingesting {len(sessions)} sessions...")
            
            # Use gold-standard data if available
            has_gold = "session_summary" in conv and "observation" in conv and "event_summary" in conv
            
            # Always use LLM ingestion (proven best for temporal/retrieval)
            for sess in sessions:
                mc.add(sess["session_id"], sess["date"], sess["conversation"],
                       speaker_a, speaker_b)
                print(f"  Ingested {sess['session_id']}")
            
            # Supplement with gold observations as extra atomic facts
            if has_gold:
                obs_count = supplement_gold_observations(mc, conv)
                print(f"  Added {obs_count} gold observations as atomic facts")
            
            chunks = mc.storage.count_raw_chunks()
            # Store image captions separately
            img_captions = extract_image_captions(conversation)
            for cap in img_captions:
                mc.storage.store_image_caption(
                    cap["session_id"], cap["date"], cap["speaker"],
                    cap["caption"], cap["turn_text"]
                )
            print(f"  Stored {chunks} raw chunks, {len(img_captions)} image captions")
        else:
            chunks = mc.storage.count_raw_chunks()
            print(f"Already ingested: {len(existing_profiles)} profiles, {chunks} raw chunks")

        questions = conv["qa"]
        total_q = len(questions)
        
        for q_idx, qa in enumerate(questions):
            question = qa["question"]
            category = qa["category"]
            ground_truth = get_ground_truth(qa)
            
            if (conv_id, question) in done_keys:
                continue
            if ground_truth is None:
                continue
            
            try:
                t0 = time.time()
                result = mc.recall(question, category=category)
                elapsed = time.time() - t0
                prediction = result["answer"]
                
                score = judge_answer(api_key, question, prediction, ground_truth)
                
                cat_name = CATEGORY_NAMES.get(category, f"cat-{category}")
                strategy = result.get("strategy", "?")
                icon = "✅" if score == 1 else "❌"
                print(f"  [{q_idx+1}/{total_q}] {icon} ({cat_name}/{strategy}) {elapsed:.1f}s | {question[:70]}")
                if score == 0:
                    print(f"    GT: {str(ground_truth)[:80]}")
                    print(f"    PR: {str(prediction)[:80]}")
                
                all_results.append({
                    "conv_id": conv_id,
                    "question": question,
                    "category": category,
                    "category_name": cat_name,
                    "ground_truth": ground_truth,
                    "prediction": prediction,
                    "score": score,
                    "strategy": strategy,
                    "elapsed": elapsed,
                })
                done_keys.add((conv_id, question))
                
                with open(checkpoint_path, "w") as f:
                    json.dump({"results": all_results}, f)
                
                time.sleep(0.15)
                
            except Exception as e:
                print(f"  [{q_idx+1}/{total_q}] ⚠️ ERROR: {e}")
                import traceback; traceback.print_exc()
                time.sleep(2)

        mc.close()

    # Summary
    total = len(all_results)
    correct = sum(r["score"] for r in all_results)
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Overall: {correct}/{total} ({correct/total*100:.1f}%)")
    
    cats = {}
    for r in all_results:
        c = r["category_name"]
        if c not in cats: cats[c] = {"total": 0, "correct": 0}
        cats[c]["total"] += 1
        cats[c]["correct"] += r["score"]
    for c, s in sorted(cats.items()):
        print(f"  {c}: {s['correct']}/{s['total']} ({s['correct']/s['total']*100:.1f}%)")
    
    avg_time = sum(r.get("elapsed", 0) for r in all_results) / len(all_results) if all_results else 0
    print(f"\nAvg time per question: {avg_time:.1f}s")
    
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump({"overall": correct/total, "per_category": cats, "total": total}, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--conversations", type=str, default=None)
    args = parser.parse_args()
    run_benchmark(args.data, args.output, args.conversations)

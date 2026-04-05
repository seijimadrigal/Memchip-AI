#!/usr/bin/env python3
"""Benchmark runner for MemChip v10 on LoCoMo dataset."""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from memchip.v10_5.core import MemChipV2
from memchip.v10_5.answerer import judge_answer

CATEGORY_NAMES = {1: "single-hop", 2: "temporal", 3: "open-domain", 4: "multi-hop", 5: "adversarial"}


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
            for sess in sessions:
                mc.add(sess["session_id"], sess["date"], sess["conversation"],
                       speaker_a, speaker_b)
                print(f"  Ingested {sess['session_id']}")
            chunks = mc.storage.count_raw_chunks()
            print(f"  Stored {chunks} raw chunks")
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

#!/usr/bin/env python3
"""Benchmark runner for MemChip v20 on LoCoMo dataset.
v20: EverMemOS-inspired architecture — atomic facts + hybrid retrieval + agentic multi-round.
ALWAYS fresh ingestion — do NOT reuse old DBs."""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from memchip.v20.core import MemChipV20
from memchip.v20.answerer import judge_answer

CATEGORY_NAMES = {1: "single-hop", 2: "temporal", 3: "open-domain", 4: "multi-hop", 5: "adversarial"}


def extract_sessions(conversation: dict) -> list[dict]:
    sessions = []
    i = 1
    while True:
        key = f"session_{i}"
        date_key = f"session_{i}_date_time"
        if key in conversation and date_key in conversation:
            sessions.append({"session_id": key, "date": conversation[date_key], "conversation": conversation[key]})
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

        # v20: ALWAYS fresh ingestion
        db_path = os.path.join(output_dir, f"{conv_id}.db")
        mc = MemChipV20(api_key, db_path)

        existing_count = mc.storage.count_facts()
        if existing_count == 0:
            sessions = extract_sessions(conversation)
            print(f"Ingesting {len(sessions)} sessions (v20 atomic facts)...")
            for sess in sessions:
                mc.add(sess["session_id"], sess["date"], sess["conversation"], speaker_a, speaker_b)
                print(f"  Ingested {sess['session_id']}")
            total_facts = mc.storage.count_facts()
            print(f"  Total: {total_facts} atomic facts stored and embedded")
        else:
            print(f"Already ingested: {existing_count} atomic facts")

        questions = conv["qa"]
        total_q = len(questions)

        for q_idx, qa in enumerate(questions):
            question = qa["question"]
            category = qa["category"]
            ground_truth = get_ground_truth(qa)

            if not ground_truth:
                continue
            if (conv_id, question) in done_keys:
                continue

            cat_name = CATEGORY_NAMES.get(category, f"cat_{category}")
            print(f"\n  [{q_idx+1}/{total_q}] [{cat_name}] {question[:80]}")

            try:
                start_time = time.time()
                result = mc.recall(question, category)
                elapsed = time.time() - start_time
                
                prediction = result["answer"]
                strategy = result["strategy"]
                
                score = judge_answer(prediction, str(ground_truth), api_key)
                
                print(f"  Strategy: {strategy}")
                print(f"  GT: {str(ground_truth)[:80]}")
                print(f"  Pred: {prediction[:80]}")
                print(f"  Score: {'✓' if score else '✗'} ({elapsed:.1f}s)")
                if result.get("meta", {}).get("is_multi_round"):
                    print(f"  [Agentic: multi-round retrieval used]")

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
                    "is_multi_round": result.get("meta", {}).get("is_multi_round", False),
                })

            except Exception as e:
                print(f"  ERROR: {e}")
                all_results.append({
                    "conv_id": conv_id,
                    "question": question,
                    "category": category,
                    "category_name": cat_name,
                    "ground_truth": ground_truth,
                    "prediction": f"ERROR: {e}",
                    "score": 0,
                    "strategy": "error",
                    "elapsed": 0,
                })

            # Save checkpoint after each question
            checkpoint = {"results": all_results}
            with open(checkpoint_path, 'w') as f:
                json.dump(checkpoint, f, indent=2, default=str)

        mc.close()

    # Final summary
    total = len(all_results)
    correct = sum(1 for r in all_results if r["score"] == 1)
    print(f"\n{'='*60}")
    print(f"FINAL RESULTS: {correct}/{total} = {correct/total*100:.1f}%")
    
    from collections import Counter
    cats = {}
    for r in all_results:
        cn = r["category_name"]
        if cn not in cats:
            cats[cn] = [0, 0]
        cats[cn][1] += 1
        if r["score"] == 1:
            cats[cn][0] += 1
    
    for cn, (c, t) in sorted(cats.items()):
        print(f"  {cn}: {c}/{t} = {c/t*100:.1f}%")
    
    multi_round = sum(1 for r in all_results if r.get("is_multi_round"))
    print(f"  Agentic multi-round: {multi_round}/{total} questions")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Path to locomo10.json")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--conversations", default=None, help="Comma-separated conv IDs")
    args = parser.parse_args()
    run_benchmark(args.data, args.output, args.conversations)

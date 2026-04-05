#!/usr/bin/env python3
"""Benchmark runner for MemChip v3 (SmartSearch) on LoCoMo dataset."""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from memchip.v3.core import MemChipV3
from memchip.v2.answerer import judge_answer

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
        mc = MemChipV3(api_key, db_path)
        
        # Ingest (no LLM calls!)
        if mc.store.count() == 0:
            sessions = extract_sessions(conversation)
            print(f"Ingesting {len(sessions)} sessions as raw text...")
            for sess in sessions:
                mc.ingest_session(sess["session_id"], sess["date"], sess["conversation"],
                                  speaker_a, speaker_b)
            print(f"Stored {mc.store.count()} chunks")
        else:
            print(f"Already ingested: {mc.store.count()} chunks")

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
                result = mc.query(question, category=category)
                elapsed = time.time() - t0
                prediction = result["answer"]
                
                score = judge_answer(api_key, question, prediction, ground_truth)
                
                cat_name = CATEGORY_NAMES.get(category, f"cat-{category}")
                icon = "✅" if score == 1 else "❌"
                print(f"  [{q_idx+1}/{total_q}] {icon} ({cat_name}) [{result['num_candidates']}→{result['num_ranked']}] {elapsed:.1f}s | {question[:70]}")
                if score == 0:
                    print(f"    GT: {ground_truth[:80]}")
                    print(f"    PR: {prediction[:80]}")
                
                all_results.append({
                    "conv_id": conv_id,
                    "question": question,
                    "category": category,
                    "category_name": cat_name,
                    "ground_truth": ground_truth,
                    "prediction": prediction,
                    "score": score,
                    "num_candidates": result["num_candidates"],
                    "num_ranked": result["num_ranked"],
                    "top_score": result.get("top_score", 0),
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
    summary = generate_summary(all_results)
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Overall: {summary['overall']['correct']}/{summary['overall']['total']} ({summary['overall']['accuracy']:.1%})")
    print(f"\nPer Category:")
    for cat, stats in sorted(summary["per_category"].items()):
        print(f"  {cat}: {stats['correct']}/{stats['total']} ({stats['accuracy']:.1%})")
    avg_time = sum(r.get("elapsed", 0) for r in all_results) / len(all_results) if all_results else 0
    print(f"\nAvg time per question: {avg_time:.1f}s")


def generate_summary(results: list[dict]) -> dict:
    total = len(results)
    correct = sum(r["score"] for r in results)
    
    per_cat = {}
    for r in results:
        cat = r["category_name"]
        if cat not in per_cat:
            per_cat[cat] = {"total": 0, "correct": 0}
        per_cat[cat]["total"] += 1
        per_cat[cat]["correct"] += r["score"]
    for cat in per_cat:
        per_cat[cat]["accuracy"] = per_cat[cat]["correct"] / per_cat[cat]["total"] if per_cat[cat]["total"] > 0 else 0
    
    return {
        "overall": {"total": total, "correct": correct, "accuracy": correct / total if total > 0 else 0},
        "per_category": per_cat,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--conversations", type=str, default=None)
    args = parser.parse_args()
    run_benchmark(args.data, args.output, args.conversations)

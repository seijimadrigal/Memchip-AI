#!/usr/bin/env python3
from __future__ import annotations
"""Benchmark runner for MemChip v2 on LoCoMo dataset."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from memchip.v2.core import MemChipV2
from memchip.v2.answerer import judge_answer

CATEGORY_NAMES = {1: "single-hop", 2: "temporal", 3: "open-domain", 4: "multi-hop", 5: "adversarial"}


def load_data(data_path: str) -> list[dict]:
    with open(data_path) as f:
        return json.load(f)


def extract_sessions(conversation: dict) -> list[dict]:
    """Extract sessions from conversation dict."""
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
            # Date exists but no conversation (empty session)
            i += 1
        else:
            break
    return sessions


def get_ground_truth(qa: dict) -> str | None:
    """Get ground truth answer. Cat 5 (adversarial) uses adversarial_answer."""
    if qa["category"] == 5:
        return qa.get("adversarial_answer")
    return qa.get("answer")


def run_benchmark(data_path: str, output_dir: str, max_conv: int = None, no_resume: bool = False):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
    data = load_data(data_path)
    
    if max_conv:
        data = data[:max_conv]

    checkpoint_path = os.path.join(output_dir, "checkpoint.json")
    
    # Load checkpoint
    checkpoint = {}
    if not no_resume and os.path.exists(checkpoint_path):
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)
        print(f"Resuming from checkpoint ({len(checkpoint.get('results', []))} questions done)")

    all_results = checkpoint.get("results", [])
    done_keys = {(r["conv_id"], r["question"]) for r in all_results}

    for conv_idx, conv in enumerate(data):
        conv_id = conv["sample_id"]
        conversation = conv["conversation"]
        speaker_a = conversation["speaker_a"]
        speaker_b = conversation["speaker_b"]
        
        print(f"\n{'='*60}")
        print(f"Processing conversation: {conv_id} ({speaker_a} & {speaker_b})")
        print(f"{'='*60}")

        # Initialize MemChip v2 for this conversation
        db_path = os.path.join(output_dir, f"{conv_id}.db")
        mc = MemChipV2(api_key, db_path)
        
        # Ingest sessions (skip if DB already exists with data)
        sessions = extract_sessions(conversation)
        
        # Check if already ingested
        existing_profiles = mc.storage.get_all_profiles()
        if not existing_profiles:
            print(f"Ingesting {len(sessions)} sessions...")
            for i, sess in enumerate(sessions):
                print(f"  Ingesting {sess['session_id']} ({sess['date']})...")
                mc.add(sess["session_id"], sess["date"], sess["conversation"], speaker_a, speaker_b)
                time.sleep(0.3)  # Rate limiting
            print(f"Ingestion complete. Profiles: {len(mc.storage.get_all_profiles())}, Episodes: {len(mc.storage.get_all_episodes())}")
        else:
            print(f"Already ingested. Profiles: {len(existing_profiles)}, Episodes: {len(mc.storage.get_all_episodes())}")

        # Answer questions
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
                result = mc.recall(question, category=category)
                prediction = result["answer"]
                strategy_used = result["strategy"]
                strategies_tried = result["strategies_tried"]
                
                # Judge
                score = judge_answer(api_key, question, prediction, ground_truth)
                
                cat_name = CATEGORY_NAMES.get(category, f"cat-{category}")
                icon = "✅" if score == 1 else "❌"
                print(f"  [{q_idx+1}/{total_q}] {icon} ({cat_name}) [{strategy_used}] {question[:80]}")
                
                result_entry = {
                    "conv_id": conv_id,
                    "question": question,
                    "category": category,
                    "category_name": cat_name,
                    "ground_truth": ground_truth,
                    "prediction": prediction,
                    "strategy": strategy_used,
                    "strategies_tried": strategies_tried,
                    "score": score,
                }
                all_results.append(result_entry)
                done_keys.add((conv_id, question))
                
                # Save checkpoint
                with open(checkpoint_path, "w") as f:
                    json.dump({"results": all_results}, f)
                
                time.sleep(0.2)  # Rate limiting
                
            except Exception as e:
                print(f"  [{q_idx+1}/{total_q}] ⚠️ ERROR: {e}")
                time.sleep(2)
                continue

        mc.close()

    # Generate summary
    summary = generate_summary(all_results)
    
    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    
    # Print summary
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Overall: {summary['overall']['correct']}/{summary['overall']['total']} ({summary['overall']['accuracy']:.1%})")
    print(f"\nPer Category:")
    for cat, stats in sorted(summary["per_category"].items()):
        print(f"  {cat}: {stats['correct']}/{stats['total']} ({stats['accuracy']:.1%})")
    print(f"\nStrategy Distribution:")
    for strat, count in sorted(summary["strategy_distribution"].items()):
        print(f"  {strat}: {count}")
    print(f"\nResults saved to {output_dir}")


def generate_summary(results: list[dict]) -> dict:
    total = len(results)
    correct = sum(r["score"] for r in results)
    
    # Per category
    per_cat = {}
    for r in results:
        cat = r["category_name"]
        if cat not in per_cat:
            per_cat[cat] = {"total": 0, "correct": 0}
        per_cat[cat]["total"] += 1
        per_cat[cat]["correct"] += r["score"]
    for cat in per_cat:
        per_cat[cat]["accuracy"] = per_cat[cat]["correct"] / per_cat[cat]["total"] if per_cat[cat]["total"] > 0 else 0
    
    # Strategy distribution
    strat_dist = {}
    for r in results:
        s = r["strategy"]
        strat_dist[s] = strat_dist.get(s, 0) + 1
    
    # Per strategy accuracy
    strat_acc = {}
    for r in results:
        s = r["strategy"]
        if s not in strat_acc:
            strat_acc[s] = {"total": 0, "correct": 0}
        strat_acc[s]["total"] += 1
        strat_acc[s]["correct"] += r["score"]
    for s in strat_acc:
        strat_acc[s]["accuracy"] = strat_acc[s]["correct"] / strat_acc[s]["total"] if strat_acc[s]["total"] > 0 else 0
    
    return {
        "overall": {
            "total": total,
            "correct": correct,
            "accuracy": correct / total if total > 0 else 0,
        },
        "per_category": per_cat,
        "strategy_distribution": strat_dist,
        "strategy_accuracy": strat_acc,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MemChip v2 LoCoMo Benchmark")
    parser.add_argument("--data", required=True, help="Path to locomo10.json")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--max-conv", type=int, default=None, help="Max conversations to process")
    parser.add_argument("--no-resume", action="store_true", help="Don't resume from checkpoint")
    args = parser.parse_args()
    
    run_benchmark(args.data, args.output, args.max_conv, args.no_resume)

#!/usr/bin/env python3
"""
LoCoMo Benchmark Runner for MemChip.

Pipeline: Add conversations → Search for answers → Evaluate with LLM judge.
Scoring: Weighted average across 4 categories (excluding adversarial cat 5).

Usage:
    python benchmarks/run_locomo.py --data path/to/locomo10.json --output results/
"""

import argparse
import json
import time
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from memchip.core import MemChip
from memchip.llm import call_llm


CATEGORY_NAMES = {
    1: "multi_hop",
    2: "temporal",
    3: "open_domain",
    4: "single_hop",
    5: "adversarial",
}

SCORED_CATEGORIES = {1, 2, 3, 4}  # Exclude adversarial (5)


def format_conversation(conversation: List[Dict]) -> str:
    """Format a conversation session into readable text."""
    lines = []
    for session in conversation:
        if isinstance(session, dict):
            session_id = session.get("session_id", "")
            date = session.get("date", "")
            if date:
                lines.append(f"\n--- Session {session_id} ({date}) ---")
            dialogue = session.get("dialogue", [])
            for turn in dialogue:
                if isinstance(turn, dict):
                    speaker = turn.get("speaker", turn.get("role", ""))
                    text = turn.get("text", turn.get("content", ""))
                    lines.append(f"{speaker}: {text}")
                elif isinstance(turn, str):
                    lines.append(turn)
        elif isinstance(session, str):
            lines.append(session)
    return "\n".join(lines)


def llm_judge(question: str, ground_truth: str, prediction: str, api_key: str) -> int:
    """Use LLM as judge: 1 if answer matches ground truth, 0 otherwise."""
    prompt = f"""You are evaluating whether a predicted answer matches the ground truth answer.

Question: {question}
Ground Truth Answer: {ground_truth}
Predicted Answer: {prediction}

Judge whether the predicted answer is semantically equivalent to the ground truth.
- Minor wording differences are OK (e.g., "New York" vs "NYC")
- The core facts must match
- If the prediction contains the ground truth answer plus extra correct info, score 1
- If the prediction is missing key facts from ground truth, score 0
- If the prediction contradicts the ground truth, score 0

Output ONLY a single number: 1 (correct) or 0 (incorrect)."""

    response = call_llm(
        prompt=prompt,
        provider="openai",
        model="gpt-4.1-mini",
        api_key=api_key,
        temperature=0.0,
        max_tokens=5,
    )

    try:
        return int(response.strip()[0])
    except (ValueError, IndexError):
        return 0


def run_benchmark(
    data_path: str,
    output_dir: str,
    api_key: Optional[str] = None,
    llm_model: str = "gpt-4.1-mini",
    max_conversations: Optional[int] = None,
    resume: bool = True,
):
    """Run the full LoCoMo benchmark."""
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Set OPENAI_API_KEY environment variable")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load dataset
    with open(data_path) as f:
        data = json.load(f)

    if max_conversations:
        data = data[:max_conversations]

    print(f"Loaded {len(data)} conversations")

    # Load checkpoint if resuming
    checkpoint_path = output_dir / "checkpoint.json"
    results = []
    processed_ids = set()
    if resume and checkpoint_path.exists():
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)
            results = checkpoint.get("results", [])
            processed_ids = {r["conv_id"] + "_" + str(r["q_idx"]) for r in results}
        print(f"Resuming from checkpoint: {len(results)} questions already processed")

    total_questions = sum(
        len([q for q in conv["qa"] if q.get("category") in SCORED_CATEGORIES])
        for conv in data
    )
    print(f"Total scored questions: {total_questions}")

    for conv_idx, conv in enumerate(data):
        conv_id = conv.get("sample_id", f"conv_{conv_idx}")
        conversation = conv["conversation"]
        qa_pairs = conv["qa"]

        # Stage 1: Ingest conversation into MemChip
        print(f"\n{'='*60}")
        print(f"Conversation {conv_idx+1}/{len(data)}: {conv_id}")
        print(f"{'='*60}")

        chip = MemChip(
            db_path=str(output_dir / f"memchip_{conv_id}.db"),
            user_id=conv_id,
            llm_model=llm_model,
            api_key=api_key,
        )

        # LoCoMo format: conversation is a dict with speaker_a, speaker_b,
        # session_N (list of turns), session_N_date_time
        if isinstance(conversation, dict):
            speaker_a = conversation.get("speaker_a", "Speaker A")
            speaker_b = conversation.get("speaker_b", "Speaker B")
            
            # Find all session keys
            session_keys = sorted(
                [k for k in conversation.keys() 
                 if k.startswith("session_") and not k.endswith("_date_time")],
                key=lambda x: int(x.split("_")[1])
            )
            
            for session_key in session_keys:
                session_id = session_key
                date_key = f"{session_key}_date_time"
                date = conversation.get(date_key, "")
                turns = conversation[session_key]
                
                if isinstance(turns, list):
                    text = "\n".join(
                        f"{t.get('speaker', '')}: {t.get('text', '')}"
                        for t in turns if isinstance(t, dict)
                    )
                    if text.strip():
                        chip.add(
                            text=text,
                            session_id=session_id,
                            timestamp=date,
                        )
                        print(f"  Added {session_id} ({date}): {len(text)} chars")
        else:
            # Fallback for other formats
            for session in conversation:
                if isinstance(session, dict):
                    session_id = session.get("session_id", "")
                    date = session.get("date", "")
                    dialogue = session.get("dialogue", [])
                    text = "\n".join(
                        f"{t.get('speaker', '')}: {t.get('text', '')}"
                        for t in dialogue if isinstance(t, dict)
                    )
                    if text.strip():
                        chip.add(text=text, session_id=str(session_id), timestamp=date)
                        print(f"  Added session {session_id} ({date}): {len(text)} chars")

        # Stage 2: Answer questions
        scored_qa = [q for q in qa_pairs if q.get("category") in SCORED_CATEGORIES]
        print(f"  Answering {len(scored_qa)} questions...")

        for q_idx, qa in enumerate(scored_qa):
            result_id = f"{conv_id}_{q_idx}"
            if result_id in processed_ids:
                continue

            question = qa["question"]
            ground_truth = qa["answer"]
            category = qa["category"]

            try:
                # Get answer from MemChip
                prediction = chip.answer(question, agentic=True)

                # Judge
                score = llm_judge(question, ground_truth, prediction, api_key)

                result = {
                    "conv_id": conv_id,
                    "q_idx": q_idx,
                    "category": category,
                    "category_name": CATEGORY_NAMES.get(category, "unknown"),
                    "question": question,
                    "ground_truth": ground_truth,
                    "prediction": prediction,
                    "score": score,
                }
                results.append(result)
                processed_ids.add(result_id)

                status = "✅" if score == 1 else "❌"
                print(f"  [{q_idx+1}/{len(scored_qa)}] {status} ({CATEGORY_NAMES.get(category, '?')}) {question[:60]}...")

            except Exception as e:
                print(f"  [{q_idx+1}/{len(scored_qa)}] ⚠️ ERROR: {e}")
                results.append({
                    "conv_id": conv_id,
                    "q_idx": q_idx,
                    "category": category,
                    "category_name": CATEGORY_NAMES.get(category, "unknown"),
                    "question": question,
                    "ground_truth": ground_truth,
                    "prediction": f"ERROR: {e}",
                    "score": 0,
                })

            # Save checkpoint after each question
            with open(checkpoint_path, "w") as f:
                json.dump({"results": results}, f)

        # Clean up DB to save disk
        chip.store.close()

    # Compute final scores
    print_scores(results, output_dir)


def print_scores(results: List[Dict], output_dir: Path):
    """Compute and print final LoCoMo scores."""
    category_scores = defaultdict(lambda: {"correct": 0, "total": 0})

    for r in results:
        cat = r["category"]
        if cat in SCORED_CATEGORIES:
            category_scores[cat]["correct"] += r["score"]
            category_scores[cat]["total"] += 1

    print(f"\n{'='*60}")
    print("LoCoMo Benchmark Results")
    print(f"{'='*60}")

    total_correct = 0
    total_questions = 0

    for cat in sorted(category_scores.keys()):
        name = CATEGORY_NAMES.get(cat, "unknown")
        correct = category_scores[cat]["correct"]
        total = category_scores[cat]["total"]
        acc = correct / total if total > 0 else 0
        print(f"  {name:15s}: {acc:.4f} ({correct}/{total})")
        total_correct += correct
        total_questions += total

    # Weighted average (by question count)
    overall = total_correct / total_questions if total_questions > 0 else 0
    print(f"\n  {'OVERALL':15s}: {overall:.4f} ({total_correct}/{total_questions})")
    print(f"{'='*60}")

    # Save results
    summary = {
        "overall_score": overall,
        "total_correct": total_correct,
        "total_questions": total_questions,
        "categories": {
            CATEGORY_NAMES.get(cat, "unknown"): {
                "score": category_scores[cat]["correct"] / category_scores[cat]["total"]
                if category_scores[cat]["total"] > 0 else 0,
                "correct": category_scores[cat]["correct"],
                "total": category_scores[cat]["total"],
            }
            for cat in sorted(category_scores.keys())
        },
    }

    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    with open(output_dir / "full_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {output_dir}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run LoCoMo benchmark on MemChip")
    parser.add_argument("--data", required=True, help="Path to locomo10.json")
    parser.add_argument("--output", default="results", help="Output directory")
    parser.add_argument("--model", default="gpt-4.1-mini", help="LLM model")
    parser.add_argument("--max-conv", type=int, help="Max conversations to process")
    parser.add_argument("--no-resume", action="store_true", help="Don't resume from checkpoint")
    args = parser.parse_args()

    run_benchmark(
        data_path=args.data,
        output_dir=args.output,
        llm_model=args.model,
        max_conversations=args.max_conv,
        resume=not args.no_resume,
    )

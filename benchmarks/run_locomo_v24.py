"""LoCoMo benchmark runner for MemChip v24 (optimal hybrid)."""
from __future__ import annotations
import json
import os
import sys
import time
import argparse
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memchip.v24.core import MemChipV24

API_URL = "https://openrouter.ai/api/v1/chat/completions"
JUDGE_MODEL = "openai/gpt-4.1-mini"
CATEGORY_NAMES = {1: "single-hop", 2: "temporal", 3: "open-domain", 4: "multi-hop", 5: "adversarial"}


def judge_answer(api_key: str, question: str, prediction: str, ground_truth: str) -> int:
    prompt = f"""You are a judge comparing two answers to a question.
Return ONLY "1" if they convey the same information, or "0" if they don't.
Be lenient with formatting differences but strict on factual correctness.
Missing items or extra wrong items = 0.

Question: {question}
Ground Truth: {ground_truth}
Prediction: {prediction}

Score (0 or 1):"""
    
    for attempt in range(3):
        try:
            resp = httpx.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": JUDGE_MODEL, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0, "max_tokens": 16},
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()["choices"][0]["message"]["content"].strip()
            return 1 if "1" in result else 0
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"  Judge error: {e}")
                return 0


def run_benchmark(data_path: str, output_dir: str, api_key: str,
                  max_conv: int = 10, resume: bool = True,
                  reuse_db: str = None):
    """Run benchmark. If reuse_db is set, use existing v10 DBs instead of re-ingesting."""
    os.makedirs(output_dir, exist_ok=True)
    checkpoint_path = os.path.join(output_dir, "checkpoint.json")
    
    with open(data_path) as f:
        data = json.load(f)
    
    results = []
    done_keys = set()
    if resume and os.path.exists(checkpoint_path):
        with open(checkpoint_path) as f:
            results = json.load(f)["results"]
            done_keys = {(r["conv_idx"], r["q_idx"]) for r in results}
        print(f"Resuming from checkpoint: {len(results)} questions done")
    
    total_start = time.time()
    
    for conv_idx, conv in enumerate(data[:max_conv]):
        print(f"\n{'='*60}")
        print(f"Conversation {conv_idx + 1}/{min(max_conv, len(data))}")
        
        # Try to reuse existing DB from a previous run
        sample_id = conv.get("sample_id", f"conv_{conv_idx}")
        db_path = None
        if reuse_db:
            # Try both naming conventions
            for name in [f"conv_{conv_idx}.db", f"{sample_id}.db"]:
                candidate = os.path.join(reuse_db, name)
                if os.path.exists(candidate):
                    db_path = candidate
                    print(f"  Reusing DB from {candidate}")
                    break
        
        if not db_path:
            db_path = os.path.join(output_dir, f"{sample_id}.db")
        
        need_ingest = not os.path.exists(db_path)
        chip = MemChipV24(api_key=api_key, db_path=db_path)
        
        if need_ingest:
            conversation = conv["conversation"]
            speaker_a = conversation.get("speaker_a", "Speaker A")
            speaker_b = conversation.get("speaker_b", "Speaker B")
            
            session_keys = sorted([k for k in conversation.keys()
                                   if k.startswith("session_") and not k.endswith("_date_time")])
            
            for sk in session_keys:
                date_key = f"{sk}_date_time"
                date = conversation.get(date_key, "")
                turns = conversation[sk]
                chip.ingest_session(sk, date, turns, speaker_a, speaker_b)
            
            print(f"  Ingested {len(session_keys)} sessions")
        
        # Answer questions
        questions = conv["qa"]
        scored_qs = [q for q in questions if q.get("category", 0) in [1, 2, 3, 4]]
        
        for q_idx, q in enumerate(scored_qs):
            key = (conv_idx, q_idx)
            if key in done_keys:
                continue
            
            category = q["category"]
            cat_name = CATEGORY_NAMES.get(category, f"cat_{category}")
            question = q["question"]
            ground_truth = q["answer"]
            
            print(f"  [{cat_name}] Q{q_idx+1}/{len(scored_qs)}: {question[:70]}...")
            
            try:
                result = chip.query(question, category=category)
                prediction = result["answer"]
            except Exception as e:
                print(f"    ERROR: {e}")
                prediction = "Error"
            
            score = judge_answer(api_key, question, str(prediction), str(ground_truth))
            
            status = "✓" if score == 1 else "✗"
            print(f"    {status} Pred: {str(prediction)[:60]} | Truth: {str(ground_truth)[:60]}")
            
            results.append({
                "conv_idx": conv_idx,
                "q_idx": q_idx,
                "category": category,
                "category_name": cat_name,
                "question": question,
                "ground_truth": str(ground_truth),
                "prediction": str(prediction),
                "score": score,
                "strategy": result.get("strategy", "?"),
            })
            done_keys.add(key)
            
            with open(checkpoint_path, "w") as f:
                json.dump({"results": results}, f)
        
        chip.close()
    
    elapsed = time.time() - total_start
    cats = {}
    for r in results:
        c = r["category_name"]
        cats.setdefault(c, [0, 0])
        cats[c][1] += 1
        cats[c][0] += r["score"]
    
    print(f"\n{'='*60}")
    print(f"RESULTS (v24 Optimal Hybrid)")
    print(f"{'='*60}")
    for c, v in sorted(cats.items()):
        print(f"  {c}: {v[0]}/{v[1]} = {v[0]/v[1]*100:.1f}%")
    tc = sum(v[0] for v in cats.values())
    tt = sum(v[1] for v in cats.values())
    print(f"  OVERALL: {tc}/{tt} = {tc/tt*100:.1f}%")
    print(f"  Time: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    
    summary = {"overall": tc/tt*100, "categories": {c: v[0]/v[1]*100 for c, v in cats.items()},
               "total_questions": tt, "elapsed_seconds": elapsed}
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-conv", type=int, default=10)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--reuse-db", help="Path to existing run dir with conv_*.db files")
    args = parser.parse_args()
    
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Set OPENROUTER_API_KEY")
        sys.exit(1)
    
    run_benchmark(args.data, args.output, api_key, args.max_conv, not args.no_resume, args.reuse_db)

"""LoCoMo benchmark for v25 — SmartSearch + category strategies."""
from __future__ import annotations
import json, os, sys, time, argparse, httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from memchip.v25.core import MemChipV25

API_URL = "https://openrouter.ai/api/v1/chat/completions"
JUDGE_MODEL = "openai/gpt-4.1-mini"
# CORRECT LoCoMo mapping
CATEGORY_NAMES = {1: "multi-hop", 2: "temporal", 3: "open-domain", 4: "single-hop", 5: "adversarial"}


def judge(api_key, question, prediction, ground_truth):
    prompt = f"""Compare two answers. Return ONLY "1" if same info, "0" if not.
Lenient on format, strict on facts. Missing/extra wrong items = 0.

Question: {question}
Ground Truth: {ground_truth}
Prediction: {prediction}

Score (0 or 1):"""
    for attempt in range(3):
        try:
            r = httpx.post(API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": JUDGE_MODEL, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0, "max_tokens": 16}, timeout=30)
            r.raise_for_status()
            return 1 if "1" in r.json()["choices"][0]["message"]["content"] else 0
        except Exception as e:
            if attempt < 2: time.sleep(2**attempt)
            else: return 0


def run(data_path, output_dir, api_key, max_conv=10, resume=True, v10_db_dir=None):
    os.makedirs(output_dir, exist_ok=True)
    cp = os.path.join(output_dir, "checkpoint.json")
    
    with open(data_path) as f:
        data = json.load(f)
    
    results, done = [], set()
    if resume and os.path.exists(cp):
        with open(cp) as f:
            results = json.load(f)["results"]
            done = {(r["conv_idx"], r["q_idx"]) for r in results}
        print(f"Resuming: {len(results)} done")
    
    t0 = time.time()
    
    for ci, conv in enumerate(data[:max_conv]):
        sid = conv["sample_id"]
        print(f"\n{'='*50}\nConv {ci+1}/{min(max_conv, len(data))} ({sid})")
        
        raw_db = os.path.join(output_dir, f"{sid}_raw.db")
        v10_db = None
        if v10_db_dir:
            candidate = os.path.join(v10_db_dir, f"{sid}.db")
            if os.path.exists(candidate):
                v10_db = candidate
                print(f"  v10 DB: {candidate}")
        
        chip = MemChipV25(api_key=api_key, raw_db_path=raw_db, v10_db_path=v10_db)
        
        if not os.path.exists(raw_db) or chip.raw_store.count() == 0:
            c = conv["conversation"]
            sa, sb = c.get("speaker_a", "A"), c.get("speaker_b", "B")
            sessions = sorted([k for k in c if k.startswith("session_") and not k.endswith("_date_time")])
            for sk in sessions:
                chip.ingest_session(sk, c.get(f"{sk}_date_time", ""), c[sk], sa, sb)
            print(f"  Ingested {len(sessions)} sessions, {chip.raw_store.count()} chunks")
        else:
            print(f"  Using existing raw DB ({chip.raw_store.count()} chunks)")
        
        scored = [q for q in conv["qa"] if q.get("category", 0) in [1, 2, 3, 4]]
        
        for qi, q in enumerate(scored):
            if (ci, qi) in done: continue
            
            cat = q["category"]
            cat_name = CATEGORY_NAMES[cat]
            question, truth = q["question"], str(q["answer"])
            
            try:
                result = chip.query(question, category=cat)
                pred = str(result["answer"])
            except Exception as e:
                print(f"  ERROR: {e}")
                pred = "Error"
            
            score = judge(api_key, question, pred, truth)
            s = "✓" if score else "✗"
            print(f"  {s} [{cat_name}] {question[:50]}... | {pred[:35]}")
            
            results.append({
                "conv_idx": ci, "q_idx": qi, "category": cat,
                "category_name": cat_name, "question": question,
                "ground_truth": truth, "prediction": pred,
                "score": score, "strategy": result.get("strategy", "?"),
            })
            done.add((ci, qi))
            with open(cp, "w") as f:
                json.dump({"results": results}, f)
        
        chip.close()
    
    elapsed = time.time() - t0
    cats = {}
    for r in results:
        c = r["category_name"]
        cats.setdefault(c, [0, 0])
        cats[c][1] += 1
        cats[c][0] += r["score"]
    
    print(f"\n{'='*50}\nRESULTS (v25 SmartSearch + Category Strategies)")
    for c, v in sorted(cats.items()):
        print(f"  {c}: {v[0]}/{v[1]} = {v[0]/v[1]*100:.1f}%")
    tc = sum(v[0] for v in cats.values())
    tt = sum(v[1] for v in cats.values())
    print(f"  OVERALL: {tc}/{tt} = {tc/tt*100:.1f}%")
    print(f"  Time: {elapsed:.0f}s")
    
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump({"overall": tc/tt*100, "categories": {c: v[0]/v[1]*100 for c,v in cats.items()},
                    "elapsed": elapsed}, f, indent=2)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--max-conv", type=int, default=10)
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--v10-db-dir", help="Dir with v10 DBs (conv-26.db etc) for temporal/episodes")
    args = p.parse_args()
    
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key: sys.exit("Set OPENROUTER_API_KEY")
    run(args.data, args.output, api_key, args.max_conv, not args.no_resume, args.v10_db_dir)

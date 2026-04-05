#!/usr/bin/env python3
"""Rapid multi-hop only tester — runs just 32 MH questions."""
import json, os, sys, time
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from memchip.v10.core import MemChipV2
from memchip.v10.answerer import judge_answer

API_KEY = os.environ.get("OPENROUTER_API_KEY")
DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "results/run56_r49db_img/conv-26.db"
DATA_PATH = "/Users/seijim/.openclaw/workspace/locomo-benchmark/data/locomo10.json"

with open(DATA_PATH) as f:
    data = json.load(f)
conv = [d for d in data if d["sample_id"] == "conv-26"][0]

mc = MemChipV2(API_KEY, DB_PATH)

# Only MH questions (category 1)
mh_questions = [qa for qa in conv["qa"] if qa["category"] == 1]
print(f"Testing {len(mh_questions)} multi-hop questions")
print(f"DB: {DB_PATH}")
print()

correct = 0
total = 0
for qa in mh_questions:
    q = qa["question"]
    gt = qa.get("answer", "")
    
    start = time.time()
    result = mc.recall(q, category=1)
    elapsed = time.time() - start
    
    pred = result["answer"]
    score = judge_answer(API_KEY, q, pred, gt)
    correct += score
    total += 1
    
    icon = "✅" if score == 1 else "❌"
    print(f"{icon} [{correct}/{total}] ({elapsed:.1f}s) Q: {q}")
    if score == 0:
        print(f"   GT:  {gt}")
        print(f"   Got: {pred[:120]}")
    print()

print(f"\n{'='*50}")
print(f"Multi-hop: {correct}/{total} = {correct/total*100:.1f}%")
mc.close()

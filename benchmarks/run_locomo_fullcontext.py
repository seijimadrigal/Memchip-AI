"""LoCoMo full-context baseline — dump entire conversation, no retrieval."""
from __future__ import annotations
import json, os, sys, time, argparse, httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API_URL = "https://openrouter.ai/api/v1/chat/completions"
ANSWER_MODEL = "openai/gpt-4.1-mini"
JUDGE_MODEL = "openai/gpt-4.1-mini"

# Correct LoCoMo mapping
CATEGORY_NAMES = {1: "multi-hop", 2: "temporal", 3: "open-domain", 4: "single-hop", 5: "adversarial"}


def llm_call(api_key, messages, model=ANSWER_MODEL, temperature=0, max_tokens=200):
    for attempt in range(3):
        try:
            resp = httpx.post(API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                timeout=120)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt < 2: time.sleep(2 ** attempt)
            else: raise


def judge(api_key, question, prediction, ground_truth):
    prompt = f"""Compare these two answers. Return ONLY "1" if same info, "0" if not.
Be lenient on format, strict on facts. Missing/extra wrong items = 0.

Question: {question}
Ground Truth: {ground_truth}
Prediction: {prediction}

Score (0 or 1):"""
    try:
        r = llm_call(api_key, [{"role": "user", "content": prompt}], model=JUDGE_MODEL, max_tokens=16)
        return 1 if "1" in r else 0
    except:
        return 0


def format_conversation(conv):
    """Format entire conversation as text with session dates."""
    c = conv["conversation"]
    speaker_a = c.get("speaker_a", "A")
    speaker_b = c.get("speaker_b", "B")
    
    sessions = sorted([k for k in c if k.startswith("session_") and not k.endswith("_date_time")])
    
    parts = []
    for sk in sessions:
        date = c.get(f"{sk}_date_time", "")
        turns = c[sk]
        lines = [f"[{sk} — {date}]"]
        for t in turns:
            lines.append(f"{t['speaker']}: {t['text']}")
        parts.append("\n".join(lines))
    
    return "\n\n".join(parts)


ANSWER_PROMPT = """You have access to the COMPLETE conversation history between two people.
Answer the question using ONLY information from these conversations.

RULES:
- Be MAXIMALLY CONCISE — answer like a trivia quiz (2-15 words ideal)
- Use EXACT words from the conversations
- For counts: give the NUMBER
- For lists: ALL relevant items, comma-separated
- For "recently"/"latest": ONLY the most recent
- Convert relative dates using session dates (e.g., "yesterday" in a May 25 session = May 24)
- Do NOT correct the question or say "Actually, it was someone else"
- No explanations, no "Based on..."
- If truly not mentioned: "Not mentioned"

CONVERSATION HISTORY:
{conversation}

QUESTION: {question}

ANSWER:"""


def run(data_path, output_dir, api_key, max_conv=10, resume=True):
    os.makedirs(output_dir, exist_ok=True)
    cp_path = os.path.join(output_dir, "checkpoint.json")
    
    with open(data_path) as f:
        data = json.load(f)
    
    results = []
    done = set()
    if resume and os.path.exists(cp_path):
        with open(cp_path) as f:
            results = json.load(f)["results"]
            done = {(r["conv_idx"], r["q_idx"]) for r in results}
        print(f"Resuming: {len(results)} done")
    
    t0 = time.time()
    
    for ci, conv in enumerate(data[:max_conv]):
        print(f"\n{'='*50}\nConversation {ci+1}/{min(max_conv, len(data))} ({conv['sample_id']})")
        
        full_text = format_conversation(conv)
        token_est = len(full_text.split()) * 1.3
        print(f"  ~{token_est:.0f} tokens")
        
        scored = [q for q in conv["qa"] if q.get("category", 0) in [1, 2, 3, 4]]
        
        for qi, q in enumerate(scored):
            if (ci, qi) in done: continue
            
            cat = q["category"]
            cat_name = CATEGORY_NAMES[cat]
            question = q["question"]
            truth = str(q["answer"])
            
            prompt = ANSWER_PROMPT.format(conversation=full_text, question=question)
            
            try:
                pred = llm_call(api_key, [{"role": "user", "content": prompt}], max_tokens=150)
            except Exception as e:
                print(f"  ERROR: {e}")
                pred = "Error"
            
            score = judge(api_key, question, str(pred), truth)
            
            s = "✓" if score else "✗"
            print(f"  {s} [{cat_name}] {question[:55]}... | {str(pred)[:40]}")
            
            results.append({
                "conv_idx": ci, "q_idx": qi, "category": cat,
                "category_name": cat_name, "question": question,
                "ground_truth": truth, "prediction": str(pred), "score": score,
            })
            done.add((ci, qi))
            
            with open(cp_path, "w") as f:
                json.dump({"results": results}, f)
    
    elapsed = time.time() - t0
    cats = {}
    for r in results:
        c = r["category_name"]
        cats.setdefault(c, [0, 0])
        cats[c][1] += 1
        cats[c][0] += r["score"]
    
    print(f"\n{'='*50}\nRESULTS (Full-Context Baseline — {ANSWER_MODEL})")
    for c, v in sorted(cats.items()):
        print(f"  {c}: {v[0]}/{v[1]} = {v[0]/v[1]*100:.1f}%")
    tc = sum(v[0] for v in cats.values())
    tt = sum(v[1] for v in cats.values())
    print(f"  OVERALL: {tc}/{tt} = {tc/tt*100:.1f}%")
    print(f"  Time: {elapsed:.0f}s")
    
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump({"overall": tc/tt*100, "categories": {c: v[0]/v[1]*100 for c, v in cats.items()},
                    "model": ANSWER_MODEL, "elapsed": elapsed}, f, indent=2)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--max-conv", type=int, default=10)
    p.add_argument("--no-resume", action="store_true")
    args = p.parse_args()
    
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key: sys.exit("Set OPENROUTER_API_KEY")
    run(args.data, args.output, api_key, args.max_conv, not args.no_resume)

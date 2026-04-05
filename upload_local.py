#!/usr/bin/env python3
"""Upload local memory files to MemChip API."""
import json, time, os, glob, urllib.request

KEY = "mc_lyn_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
API = "http://localhost:8000/v1"

def upload(text, source_file):
    if len(text.strip()) < 50:
        return "skip_short"
    text = text[:3000]
    data = json.dumps({
        "text": text,
        "user_id": "seiji",
        "agent_id": "lyn",
        "scope": "private",
        "source_type": "api_direct"
    }).encode()
    req = urllib.request.Request(API + "/memories/", data=data, headers={
        "Authorization": "Bearer " + KEY,
        "Content-Type": "application/json"
    })
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        result = json.loads(resp.read())
        created = result.get("memories_created", 0)
        status = result.get("status", "?")
        return "{}:{}".format(status, created)
    except Exception as e:
        return "err:{}".format(e)

# Upload MEMORY.md sections
with open("/tmp/lyn-memory/MEMORY.md") as f:
    content = f.read()
sections = content.split("\n## ")
for i, s in enumerate(sections):
    if len(s.strip()) > 50:
        text = ("## " + s if not s.startswith("#") else s).strip()
        result = upload(text, "MEMORY.md")
        print("MEMORY.md section {}: {}".format(i, result), flush=True)
        time.sleep(1)

# Upload daily files
for path in sorted(glob.glob("/tmp/lyn-memory/2026-*.md")):
    with open(path) as f:
        content = f.read().strip()
    if len(content) > 50:
        fname = os.path.basename(path)
        if len(content) > 3000:
            chunks = [content[j:j+3000] for j in range(0, len(content), 3000)]
            for ci, chunk in enumerate(chunks):
                result = upload(chunk, "{}[{}]".format(fname, ci))
                print("{}[{}]: {}".format(fname, ci, result), flush=True)
                time.sleep(1)
        else:
            result = upload(content, fname)
            print("{}: {}".format(fname, result), flush=True)
            time.sleep(1)

print("ALL DONE", flush=True)

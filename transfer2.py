#!/usr/bin/env python3
"""Transfer memory chunks to MemChip Cloud API."""
import json, re, time, urllib.request, os

API = "http://76.13.23.55/v1/memories/"
TOKEN = "mc_d798cc892328f4e598803eac5f675cb1ad301fc16a78fd6e"
LOG = "/Users/seijim/.openclaw/workspace/memchip/TRANSFER_LOG.md"
BASE = "/Users/seijim/.openclaw/workspace"

success = 0
fail = 0
log_lines = ["# MemChip Transfer Log", f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]

def send(label, text):
    global success, fail
    text = text[:2000].strip()
    if not text:
        return
    body = json.dumps({
        "text": text,
        "user_id": "seiji",
        "agent_id": "lyn", 
        "org_id": "team-seiji",
        "pool_id": "shared:team"
    }).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    })
    print(f"Sending: {label} ({len(text)} chars)...", end=" ", flush=True)
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        code = resp.getcode()
        print(f"✅ {code}")
        log_lines.append(f"- ✅ **{label}** — {code}")
        success += 1
    except Exception as e:
        print(f"❌ {e}")
        log_lines.append(f"- ❌ **{label}** — {e}")
        fail += 1
    time.sleep(2)

# 1. MEMORY.md sections
with open(f"{BASE}/MEMORY.md") as f:
    content = f.read()
sections = re.split(r'(?=^## )', content, flags=re.MULTILINE)
for i, section in enumerate(sections):
    section = section.strip()
    if not section:
        continue
    title = section.split('\n')[0].replace('#', '').strip() or f"section_{i}"
    send(f"MEMORY: {title[:60]}", section)

# 2. USER.md
with open(f"{BASE}/USER.md") as f:
    send("USER.md", f.read())

# 3. IDENTITY.md  
with open(f"{BASE}/IDENTITY.md") as f:
    send("IDENTITY.md", f.read())

# 4. TOOLS.md (redacted)
with open(f"{BASE}/TOOLS.md") as f:
    tools = f.read()
redacted = []
for line in tools.split('\n'):
    lo = line.lower()
    if any(k in lo for k in ['key:', 'password:', 'sk-', 'figd_', 'mc_', 'm0-', 'aiza', 'rpa_']):
        redacted.append(re.sub(r':\s*\S+.*', ': [REDACTED]', line))
    else:
        redacted.append(line)
send("TOOLS.md (redacted)", '\n'.join(redacted))

# Write log
log_lines.extend(["", "## Summary", f"- **Success:** {success}", f"- **Failed:** {fail}", 
                   f"- **Total:** {success+fail}", f"Completed: {time.strftime('%Y-%m-%d %H:%M:%S')}"])
with open(LOG, 'w') as f:
    f.write('\n'.join(log_lines))
print(f"\n=== DONE: {success} success, {fail} failed ===")

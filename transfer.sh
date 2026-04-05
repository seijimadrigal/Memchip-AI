#!/bin/bash
# MemChip Memory Transfer Script
API="http://76.13.23.55/v1/memories/"
TOKEN="mc_d798cc892328f4e598803eac5f675cb1ad301fc16a78fd6e"
LOG="/Users/seijim/.openclaw/workspace/memchip/TRANSFER_LOG.md"
CHUNKS_DIR="/Users/seijim/.openclaw/workspace/memchip/chunks"

mkdir -p "$CHUNKS_DIR"

echo "# MemChip Transfer Log" > "$LOG"
echo "Started: $(date)" >> "$LOG"
echo "" >> "$LOG"

SUCCESS=0
FAIL=0

send_chunk() {
  local label="$1"
  local file="$2"
  
  # Read and escape for JSON
  local text
  text=$(cat "$file" | head -c 2000)
  
  # Use python to properly JSON-encode
  local json
  json=$(python3 -c "
import json, sys
text = sys.stdin.read()
print(json.dumps({'text': text, 'user_id': 'seiji', 'agent_id': 'lyn', 'org_id': 'team-seiji', 'pool_id': 'shared:team'}))
" <<< "$text")
  
  echo -n "Sending: $label ... "
  
  local response
  response=$(curl -s -w "\n%{http_code}" --max-time 120 \
    -X POST "$API" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$json" 2>&1)
  
  local http_code=$(echo "$response" | tail -1)
  local body=$(echo "$response" | head -n -1)
  
  if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
    echo "✅ ($http_code)"
    echo "- ✅ **$label** — $http_code" >> "$LOG"
    SUCCESS=$((SUCCESS + 1))
  else
    echo "❌ ($http_code)"
    echo "- ❌ **$label** — $http_code: $(echo "$body" | head -c 200)" >> "$LOG"
    FAIL=$((FAIL + 1))
  fi
  
  # Small delay between requests
  sleep 2
}

# Split MEMORY.md by ## headers
python3 << 'PYEOF'
import re, os
chunks_dir = "/Users/seijim/.openclaw/workspace/memchip/chunks"
with open("/Users/seijim/.openclaw/workspace/MEMORY.md") as f:
    content = f.read()

# Split by ## headers
sections = re.split(r'(?=^## )', content, flags=re.MULTILINE)
for i, section in enumerate(sections):
    section = section.strip()
    if not section:
        continue
    # Get title from first line
    lines = section.split('\n')
    title = lines[0].replace('#', '').strip()
    if not title:
        title = f"section_{i}"
    # Sanitize filename
    fname = re.sub(r'[^a-zA-Z0-9_-]', '_', title)[:50]
    with open(f"{chunks_dir}/mem_{i:02d}_{fname}.txt", 'w') as out:
        out.write(section[:2000])
PYEOF

# Also create chunks for USER.md, IDENTITY.md, TOOLS.md (sanitized)
cp /Users/seijim/.openclaw/workspace/USER.md "$CHUNKS_DIR/file_user.txt"
cp /Users/seijim/.openclaw/workspace/IDENTITY.md "$CHUNKS_DIR/file_identity.txt"

# TOOLS.md - strip API keys/passwords
python3 << 'PYEOF'
import re
with open("/Users/seijim/.openclaw/workspace/TOOLS.md") as f:
    content = f.read()
# Remove lines with keys, passwords, tokens
filtered = []
for line in content.split('\n'):
    lower = line.lower()
    if any(kw in lower for kw in ['key:', 'password:', 'token:', 'sk-', 'figd_', 'mc_', 'm0-', 'aiza']):
        # Replace value with [REDACTED]
        filtered.append(re.sub(r'(Key|Password|Token|key|password|token).*?:\*?\*?\s*.*', r'\1: [REDACTED]', line))
    else:
        filtered.append(line)
with open("/Users/seijim/.openclaw/workspace/memchip/chunks/file_tools.txt", 'w') as f:
    f.write('\n'.join(filtered)[:2000])
PYEOF

# Send all chunks
for chunk_file in "$CHUNKS_DIR"/*.txt; do
  label=$(basename "$chunk_file" .txt)
  send_chunk "$label" "$chunk_file"
done

echo "" >> "$LOG"
echo "## Summary" >> "$LOG"
echo "- **Success:** $SUCCESS" >> "$LOG"
echo "- **Failed:** $FAIL" >> "$LOG"
echo "- **Total:** $((SUCCESS + FAIL))" >> "$LOG"
echo "Completed: $(date)" >> "$LOG"

echo ""
echo "=== DONE: $SUCCESS success, $FAIL failed ==="

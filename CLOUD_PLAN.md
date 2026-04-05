# MemChip Cloud — Full Deployment & Integration Plan

## Vision
MemChip as a **universal memory-as-a-service** that works with ANY AI agent — OpenClaw, Claude Code, Hermes, LangChain, CrewAI, Cursor, custom agents. With **real-time shared memory** between agents.

---

## Phase 1: REST API (Week 1)
**Goal:** Mem0-compatible REST API that any HTTP client can use

### Endpoints
```
POST   /v1/memories/          — Add memories (text or conversation turns)
POST   /v1/memories/search/   — Search/recall memories
GET    /v1/memories/          — List memories for a user
DELETE /v1/memories/{id}      — Delete a memory
PUT    /v1/memories/{id}      — Update a memory

POST   /v1/memories/answer/   — Answer a question using memories (MemChip unique)

# Scoping
POST   /v1/memories/          — { user_id, agent_id, session_id, org_id }
```

### Auth & Multi-tenancy
- API key auth (Bearer token)
- Keys scoped to org → users → agents
- Rate limiting per key
- Usage tracking (calls, tokens, storage)

### Stack
- **Framework:** FastAPI (Python) — async, OpenAPI docs auto-generated
- **Database:** PostgreSQL (multi-tenant) + per-user FTS indexes
- **Cache:** Redis (hot memory cache, rate limiting)
- **Queue:** Redis/Celery for async ingestion (5 LLM calls per add)

### Deliverable
- Docker Compose (API + Postgres + Redis)
- `pip install memchip` client SDK (Python)
- OpenAPI spec at `/docs`

---

## Phase 2: MCP Server (Week 1-2)
**Goal:** Native integration with Claude Code, Cursor, Windsurf, any MCP client

### MCP Tools to Expose
```
add_memory(text, user_id, metadata)     — Store a memory
search_memory(query, user_id, limit)    — Recall relevant memories
list_memories(user_id, limit)           — Browse stored memories  
delete_memory(memory_id)                — Remove a memory
answer_question(question, user_id)      — Multi-hop answer (unique to MemChip)
```

### Transport
- **SSE (Server-Sent Events)** — for remote/cloud MCP
- **stdio** — for local installations

### Installation (one-liner for Claude Code)
```bash
claude mcp add --scope user --transport sse memchip \
  --env MEMCHIP_API_KEY=mc_xxx \
  --env MEMCHIP_URL=https://api.memchip.dev
```

### Cursor/Windsurf
```json
// .cursor/mcp.json
{
  "memchip": {
    "transport": "sse",
    "url": "https://api.memchip.dev/mcp",
    "env": { "MEMCHIP_API_KEY": "mc_xxx" }
  }
}
```

---

## Phase 3: OpenClaw Plugin (Week 2)
**Goal:** Drop-in replacement for Cognee/Mem0 on OpenClaw

### Plugin: `openclaw-memchip`
```json
// openclaw.json
{
  "plugins": {
    "slots": { "memory": "openclaw-memchip" },
    "entries": {
      "openclaw-memchip": {
        "enabled": true,
        "config": {
          "apiUrl": "https://api.memchip.dev",
          "apiKey": "mc_xxx",
          "userId": "seiji",
          "autoRecall": true,
          "autoCapture": true,
          "topK": 5
        }
      }
    }
  }
}
```

### Features
- `memory_search(query)` → recalls from MemChip
- `memory_store(text)` → ingests via MemChip pipeline
- `memory_forget(query)` → deletes matching memories
- Auto-recall on every message (injects relevant memories)
- Auto-capture (extracts facts from conversations)
- Compaction-safe (memories survive context compaction)

---

## Phase 4: Shared Memory Between Agents (Week 2-3) ⭐
**Goal:** Agents share memories in real-time — Lyn sees what Luna learns, and vice versa

### Architecture
```
┌─────────┐     ┌─────────┐     ┌─────────┐
│  Lyn    │     │  Luna   │     │  Midus  │
│(OpenClaw)│     │(OpenClaw)│     │(Claude) │
└────┬────┘     └────┬────┘     └────┬────┘
     │               │               │
     ▼               ▼               ▼
┌──────────────────────────────────────────┐
│          MemChip Cloud API               │
│                                          │
│  ┌──────────────────────────────────┐   │
│  │     Shared Memory Pool           │   │
│  │  org: "team-seiji"               │   │
│  │                                  │   │
│  │  user:seiji  → personal memories │   │
│  │  user:cj     → personal memories │   │
│  │  agent:lyn   → agent memories    │   │
│  │  agent:luna  → agent memories    │   │
│  │  shared:team → team memories     │   │
│  └──────────────────────────────────┘   │
│                                          │
│  ┌──────────────────────────────────┐   │
│  │     Real-Time Sync (WebSocket)   │   │
│  │  • Memory added → broadcast      │   │
│  │  • Memory updated → broadcast    │   │
│  │  • Subscriptions per agent       │   │
│  └──────────────────────────────────┘   │
└──────────────────────────────────────────┘
```

### Memory Scoping Model
```
Organization (org_id: "team-seiji")
├── Users
│   ├── seiji → personal preferences, history
│   └── cj → personal preferences, history  
├── Agents
│   ├── lyn → operational knowledge, learned skills
│   ├── luna → research findings, analysis
│   └── midus → testing results, bugs found
└── Shared Pools
    ├── team → decisions, project state, shared context
    ├── memchip-project → MemChip development context
    └── stores → Shopify store knowledge
```

### Access Control
```json
{
  "agent_id": "lyn",
  "permissions": {
    "read": ["shared:*", "agent:luna", "agent:midus", "user:seiji"],
    "write": ["shared:team", "agent:lyn", "user:seiji"],
    "admin": ["agent:lyn"]
  }
}
```

### Real-Time Sync
- **WebSocket** endpoint: `wss://api.memchip.dev/v1/ws`
- Agents subscribe to memory pools they have read access to
- When Luna adds a research finding → Lyn gets notified instantly
- Events: `memory.added`, `memory.updated`, `memory.deleted`
- Fallback: polling `/v1/memories/changes?since=<timestamp>`

### Cross-Agent Query
```
POST /v1/memories/search/
{
  "query": "What did Luna find about EverMemOS architecture?",
  "user_id": "seiji",
  "agent_id": "lyn",
  "search_scope": ["agent:luna", "shared:memchip-project"],
  "limit": 10
}
```

---

## Phase 5: SDKs & Framework Integrations (Week 3)

### Python SDK
```python
from memchip import MemChip

mc = MemChip(api_key="mc_xxx")

# Add memory
mc.add("User prefers dark mode", user_id="seiji", agent_id="lyn")

# Search
results = mc.search("What does the user prefer?", user_id="seiji")

# Answer (multi-hop)
answer = mc.answer("When did Seiji start the MemChip project?", user_id="seiji")

# Shared memory
mc.add("EverMemOS uses event graphs", 
       scope="shared:memchip-project", 
       agent_id="luna")
```

### JavaScript/TypeScript SDK
```typescript
import { MemChip } from '@memchip/sdk';

const mc = new MemChip({ apiKey: 'mc_xxx' });
await mc.add({ text: 'User prefers dark mode', userId: 'seiji' });
const results = await mc.search({ query: 'preferences', userId: 'seiji' });
```

### Framework Adapters
- **LangChain:** `MemChipMemory` class (BaseMemory compatible)
- **CrewAI:** Memory backend plugin
- **AutoGen:** Memory store adapter
- **LangGraph:** State persistence layer
- **Hermes:** MCP integration (same as Claude Code)

---

## Phase 6: Cloud Infrastructure (Week 3-4)

### Deployment
```
┌─────────────────────────────────────────┐
│              Cloudflare CDN              │
│          (SSL, DDoS protection)         │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│         Load Balancer (nginx)           │
└──────┬───────────────┬──────────────────┘
       │               │
┌──────▼──────┐ ┌──────▼──────┐
│  API Pod 1  │ │  API Pod 2  │  (FastAPI, autoscale)
└──────┬──────┘ └──────┬──────┘
       │               │
┌──────▼───────────────▼──────────────────┐
│              PostgreSQL                  │
│  (Supabase or self-hosted, FTS enabled) │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│              Redis                       │
│  (cache + pub/sub for WebSocket sync)   │
└─────────────────────────────────────────┘
```

### Hosting Options
| Option | Cost/mo | Pros | Cons |
|--------|---------|------|------|
| Hostinger VPS (current) | $8-15 | Already have it | Limited scale |
| Hetzner CX31 | $12 | Great value, EU | No managed DB |
| Railway | $5 + usage | Easy deploy | Vendor lock-in |
| Fly.io | $5 + usage | Global edge | Learning curve |
| AWS Lightsail | $20 | Full AWS ecosystem | Overkill early |

**Recommendation:** Start on Hostinger VPS (we already have it), migrate to Hetzner or Railway when we hit 100+ users.

---

## Phase 7: Dashboard & Admin (Week 4)

### Web Dashboard (api.memchip.dev)
- Memory browser (search, view, edit, delete)
- Usage analytics (calls/day, tokens, storage)
- Agent activity feed (who stored what, when)
- API key management
- Shared memory pool management
- Real-time memory stream viewer

### CLI Tool
```bash
memchip status                    # API health + usage
memchip memories list --user seiji
memchip memories search "trading preferences"
memchip memories add "Prefers scalping on EURUSD"
memchip agents list               # Connected agents
memchip shared list               # Shared memory pools
```

---

## What Makes MemChip Different From Mem0

| Feature | Mem0 | **MemChip** |
|---------|------|-------------|
| Benchmark score | 62-67% | **86.8%** |
| Multi-hop reasoning | No | **Yes (71.9%)** |
| Temporal queries | No | **Yes (94.6%)** |
| Self-hostable | Cloud only ($99/mo) | **Yes + cloud** |
| Shared agent memory | No | **Yes (real-time)** |
| MCP server | Yes (OpenMemory) | **Yes** |
| Answer endpoint | No (search only) | **Yes (CoT answering)** |
| Price per user | $99/mo (pro) | **~$3-5/mo** |
| Open source | Partial | **Fully open** |

---

## Timeline

| Week | Phase | Deliverable |
|------|-------|-------------|
| 1 | REST API | FastAPI + Docker + Python SDK |
| 1-2 | MCP Server | Claude Code / Cursor / Windsurf integration |
| 2 | OpenClaw Plugin | Drop-in Cognee/Mem0 replacement |
| 2-3 | Shared Memory | WebSocket sync, scoping, cross-agent queries |
| 3 | SDKs | JS/TS SDK, LangChain/CrewAI adapters |
| 3-4 | Cloud Deploy | Production infrastructure on VPS |
| 4 | Dashboard | Web UI + CLI tool |

## Cost to Build & Run

| Item | Cost |
|------|------|
| Development | $0 (we build it) |
| VPS (Hostinger) | $8/mo (already have) |
| Domain (memchip.dev) | ~$12/yr |
| LLM API (OpenRouter) | ~$3.30/100 users/mo |
| **Total launch cost** | **~$20** |

---

## Revenue Model (Optional)

| Tier | Price | Includes |
|------|-------|----------|
| Free | $0 | 1 user, 1 agent, 1K memories, 100 queries/day |
| Pro | $10/mo | 5 users, 10 agents, unlimited memories, shared pools |
| Team | $25/mo | 20 users, unlimited agents, priority support, dashboard |
| Enterprise | Custom | Self-hosted, SLA, dedicated instance |

Even at 50 Pro users = $500/mo revenue vs ~$165/mo costs = **$335/mo profit**.

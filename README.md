# MemChip AI

**Memory-as-a-Service for AI Agents** — Give any AI agent persistent, searchable, structured long-term memory.

MemChip replaces flat-file memory (like MEMORY.md) with a real memory backend: hybrid retrieval, structured extraction, shared pools, and auto-capture — all through a simple REST API.

---

## Why MemChip?

| | Flat Files (MEMORY.md) | MemChip |
|---|---|---|
| **Search** | Keyword/grep only | Semantic + BM25 + knowledge graph |
| **Structure** | Raw text | Triples, summaries, profiles, temporal events |
| **Multi-agent** | No sharing | Shared pools with ACL |
| **Scaling** | Eats context window | Only relevant memories loaded |
| **Auto-capture** | Manual writes | Captures conversations + tool results automatically |
| **Retrieval** | Load entire file | Hybrid search returns top-K relevant memories |

## Features

- **Hybrid Search** — BM25 full-text + vector similarity + knowledge graph walk, fused via Reciprocal Rank Fusion (RRF)
- **5-Type Extraction** — Every stored text is auto-extracted into: summaries, triples (subject-predicate-object), profiles (key-value), temporal events, and raw text
- **Tool-Aware Auto-Capture** (v0.6.0) — Captures not just conversations but also tool results (shell commands, deployments, API calls) via `after_tool_call` hook
- **Shared Memory Pools** — Multiple agents read/write to the same pool with ACL-based access control
- **Conflict Detection** — Deduplication with supersede (≥0.88 similarity) and chain (≥0.80) strategies
- **Importance Scoring** — 0-5 auto-scoring filters noise at write time
- **Memory Decay** — Time-based decay with access frequency boosting
- **Dashboard** — Full Next.js + shadcn/ui dashboard with analytics, graph view, and built-in AI assistant
- **AI Assistant** — Chat interface on the dashboard that queries your memories with smart dual-retrieval (time-filtered DB fetch + semantic search)

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Dashboard (Next.js)             │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Memories  │ │ Analytics│ │  AI Assistant     │ │
│  │ Explorer  │ │ & Graph  │ │  (dual retrieval) │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
└────────────────────┬────────────────────────────┘
                     │ HTTP
┌────────────────────▼────────────────────────────┐
│              API Server (FastAPI)                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Memories  │ │ Search   │ │  Extraction      │ │
│  │ CRUD      │ │ (Hybrid) │ │  Pipeline        │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Projects  │ │ Pools &  │ │  Assistant       │ │
│  │ & Tasks   │ │ ACL      │ │  (LLM + search)  │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
└───────┬──────────────┬──────────────┬───────────┘
        │              │              │
   ┌────▼────┐   ┌─────▼─────┐  ┌────▼────┐
   │PostgreSQL│   │  Redis    │  │Embeddings│
   │  (data)  │   │ (cache)   │  │(MiniLM)  │
   └─────────┘   └───────────┘  └─────────┘
```

## Quick Start

### 1. Deploy the API

```bash
cd cloud/
cp .env.example .env  # Add your OpenRouter API key
docker compose up -d
```

### 2. Store a memory

```bash
curl -X POST http://localhost/v1/memories/ \
  -H "Authorization: Bearer mc_your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "User prefers dark mode and vim keybindings",
    "user_id": "seiji",
    "agent_id": "lyn"
  }'
```

### 3. Search it back

```bash
curl -X POST http://localhost/v1/memories/search/ \
  -H "Authorization: Bearer mc_your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "user preferences",
    "user_id": "seiji",
    "top_k": 15
  }'
```

## OpenClaw Plugin

Add persistent memory to any OpenClaw agent:

```json
{
  "plugins": {
    "slots": {
      "memory": "openclaw-memchip"
    },
    "entries": {
      "openclaw-memchip": {
        "enabled": true,
        "config": {
          "apiUrl": "http://your-server/v1",
          "apiKey": "mc_your_api_key",
          "userId": "your_user_id",
          "agentId": "your_agent_id",
          "autoRecall": true,
          "autoCapture": true,
          "topK": 15,
          "sharedPools": ["shared:team"],
          "compactionFlush": true
        }
      }
    }
  }
}
```

**Plugin hooks (v0.6.0):**
- `before_agent_start` — Auto-recall: injects top-K relevant memories as context
- `after_tool_call` — Captures high-signal tool results (exec, web_search, deployments)
- `agent_end` — Captures conversation + tool action summaries
- `before_compaction` — Last-chance save before context is trimmed

## MCP Server (Claude Code / Cursor)

```json
{
  "mcpServers": {
    "memchip": {
      "command": "python3",
      "args": [
        "mcp/mcp_server.py",
        "--api-url", "http://your-server/v1",
        "--api-key", "mc_your_key",
        "--user-id", "your_user_id"
      ]
    }
  }
}
```

## SDKs

### Python

```python
from memchip import MemChip

mc = MemChip(api_key="mc_xxx", base_url="http://your-server/v1")
mc.add("User prefers dark mode", user_id="seiji", agent_id="lyn")
results = mc.search("preferences", user_id="seiji")
```

### TypeScript

```typescript
import { MemChip } from '@memchip/sdk';

const mc = new MemChip({ apiKey: 'mc_xxx', baseUrl: 'http://your-server/v1' });
await mc.add({ text: 'User prefers dark mode', userId: 'seiji', agentId: 'lyn' });
const results = await mc.search({ query: 'preferences', userId: 'seiji' });
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/memories/` | Store a memory (auto-extracts triples, summaries, etc.) |
| `POST` | `/v1/memories/search/` | Hybrid semantic search |
| `POST` | `/v1/memories/answer/` | Search + LLM-synthesized answer |
| `GET` | `/v1/memories/` | List memories with filters |
| `PUT` | `/v1/memories/{id}` | Update a memory |
| `DELETE` | `/v1/memories/{id}` | Soft-delete (archive) |
| `POST` | `/v1/memories/bulk/delete/` | Bulk soft-delete (max 100) |
| `POST` | `/v1/memories/bulk/import/` | Bulk import |
| `POST` | `/v1/memories/bulk/export/` | Bulk export |
| `POST` | `/v1/assistant/chat/` | AI assistant with dual-retrieval |
| `GET` | `/v1/agents/{id}/profile/` | Dynamic MEMORY.md-like summary |
| `POST` | `/v1/projects/` | Create project (auto-generates pool) |
| `POST` | `/v1/tasks/` | Create task |
| `PUT` | `/v1/agents/{id}/context/` | Set agent's active project/task |
| `GET` | `/v1/health` | Health check |
| `GET` | `/v1/analytics/` | Usage analytics |
| `GET` | `/v1/graph/` | Memory relationship graph |

## Key Concepts

- **Memory Types**: `raw`, `triple`, `summary`, `temporal`, `profile`
- **Scopes**: `private`, `task`, `project`, `team`, `global`
- **Pools**: Shared namespaces (e.g. `shared:team`) with ACL
- **Importance**: 0-5 auto-scoring (0=noise, 5=foundational)
- **Conflict Resolution**: `supersede` (≥0.88), `chain` (≥0.80), `new`
- **Embeddings**: all-MiniLM-L6-v2 (local, free)

## Tech Stack

- **API**: Python, FastAPI, SQLAlchemy (async), uvicorn
- **Database**: PostgreSQL 16
- **Cache**: Redis 7
- **Embeddings**: sentence-transformers (all-MiniLM-L6-v2)
- **LLM**: OpenRouter (configurable model)
- **Dashboard**: Next.js 15, React, shadcn/ui, Tailwind CSS
- **Deployment**: Docker Compose + nginx

## License

Private — All rights reserved.

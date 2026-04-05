# MemChip → Complete OpenClaw Memory Replacement

## What OpenClaw's Memory System Actually Does

After auditing the full plugin SDK, here's EVERYTHING the memory system handles:

---

### Layer 1: Built-in Memory (Markdown Files)
OpenClaw's default memory is **file-based**:
- `MEMORY.md` — curated long-term facts (always in context)
- `memory/YYYY-MM-DD.md` — daily logs (searchable)
- `SOUL.md`, `USER.md`, `IDENTITY.md` — persona/user context
- Agent reads/writes these as regular files

**MemChip needs:** Nothing — this layer stays. MemChip AUGMENTS it, not replaces it.

---

### Layer 2: Memory Search & Indexing (QMD/Builtin)
The search system that finds relevant memories when the agent needs context:

| Feature | Current (Builtin/QMD) | MemChip Status |
|---------|----------------------|----------------|
| FTS5 full-text search | ✅ | ✅ Already have |
| Vector/semantic search | ✅ (QMD embeddings) | ❌ NEED TO ADD |
| Hybrid search (FTS + vector) | ✅ | ❌ NEED TO ADD |
| File watching (auto-reindex on change) | ✅ | ❌ NEED TO ADD |
| Session transcript indexing | ✅ | ❌ NEED TO ADD |
| Citation with file:line references | ✅ | ❌ NEED TO ADD |
| Snippet extraction | ✅ | ❌ NEED TO ADD |
| Max injected chars limit | ✅ | ❌ NEED TO ADD |
| Workspace-scoped search | ✅ | ❌ NEED TO ADD |

---

### Layer 3: Memory Plugin Interface (Cognee/Mem0 slot)
The `kind: "memory"` plugin slot that Cognee/Mem0 fill. The plugin must:

| Requirement | What It Does | MemChip Status |
|-------------|-------------|----------------|
| `registerTool(memory_search)` | Search memories via agent tool | ❌ NEED |
| `registerTool(memory_store)` | Store new memories via agent tool | ❌ NEED |
| `registerTool(memory_forget)` | Delete memories via agent tool | ❌ NEED |
| `registerTool(memory_list)` | List all memories via agent tool | ❌ NEED |
| Auto-recall on `before_agent_start` hook | Inject relevant memories into context before LLM sees the message | ❌ NEED |
| Auto-capture on `agent_end` hook | Extract facts from conversation after each turn | ❌ NEED |
| `before_compaction` hook | Save important context before session gets compressed | ❌ NEED |
| `after_compaction` hook | Re-inject critical memories after compaction | ❌ NEED |
| `configSchema` validation | Validate plugin config (apiUrl, apiKey, etc.) | ❌ NEED |
| Plugin config in `openclaw.json` | Standard config format | ❌ NEED |

---

### Layer 4: Memory Flush (Compaction Safety)
When context window fills up, OpenClaw runs a "memory flush":

| Feature | What It Does | MemChip Status |
|---------|-------------|----------------|
| Detect context threshold (4000 tokens soft limit) | Triggers flush before compaction | ❌ NEED |
| Extract important facts from conversation | LLM call to pull out key info | ✅ Have (extraction pipeline) |
| Write to persistent store | Facts survive compaction | ❌ NEED (hook integration) |
| Re-inject after compaction | Critical context comes back | ❌ NEED |

---

### Layer 5: Session Memory (Cross-Session Recall)
OpenClaw indexes past session transcripts:

| Feature | What It Does | MemChip Status |
|---------|-------------|----------------|
| Export session transcripts to searchable format | Session history becomes searchable | ❌ NEED |
| Session-scoped search | "What did we discuss last Tuesday?" | ✅ Have (temporal) |
| Cross-session recall | Find info from any past conversation | ❌ NEED (ingestion) |
| Session memory warm-up | Pre-load relevant session context | ❌ NEED |

---

## Complete Feature List for MemChip to Replace Everything

### Must Have (Week 1-2)

#### 1. OpenClaw Plugin Package (`openclaw-memchip`)
```javascript
// plugin.js
export default {
  id: "openclaw-memchip",
  name: "MemChip Memory",
  kind: "memory",
  configSchema: { /* zod schema */ },
  
  async activate(api) {
    const config = api.pluginConfig;
    const client = new MemChipClient(config.apiUrl, config.apiKey);
    
    // Register agent tools
    api.registerTool(memorySearchTool(client));    // memory_search
    api.registerTool(memoryStoreTool(client));      // memory_store  
    api.registerTool(memoryForgetTool(client));     // memory_forget
    api.registerTool(memoryListTool(client));       // memory_list
    
    // Auto-recall: inject memories before agent sees message
    api.on("before_agent_start", async (event, ctx) => {
      const memories = await client.recall(event.prompt, {
        userId: config.userId,
        agentId: ctx.agentId,
        topK: config.topK || 5
      });
      return {
        prependContext: formatMemories(memories)
      };
    });
    
    // Auto-capture: extract facts after each turn
    api.on("agent_end", async (event, ctx) => {
      if (!config.autoCapture) return;
      await client.add(extractConversation(event.messages), {
        userId: config.userId,
        agentId: ctx.agentId,
        sessionKey: ctx.sessionKey
      });
    });
    
    // Compaction safety: save before compress
    api.on("before_compaction", async (event, ctx) => {
      await client.add(event.messages, {
        userId: config.userId,
        agentId: ctx.agentId,
        tags: ["pre-compaction"],
        sessionKey: ctx.sessionKey
      });
    });
  }
};
```

#### 2. Vector/Embedding Search
MemChip currently uses FTS5 only. Need to add:
- **Embedding model:** all-MiniLM-L6-v2 (local, free) or OpenAI ada-002
- **Vector storage:** SQLite with vec extension, or Qdrant for cloud
- **Hybrid search:** Combine FTS5 BM25 + vector similarity + graph walk (RRF fusion)
- Already have RRF fusion code — just need embeddings

#### 3. Workspace File Indexing
MemChip currently only indexes conversation text. Need:
- **File watcher:** Monitor workspace files (memory/*.md, MEMORY.md, etc.)
- **Incremental indexing:** Only re-index changed files
- **Citation support:** Return `file:line` references with search results
- **Snippet extraction:** Return relevant text chunks, not just scores

#### 4. Session Transcript Ingestion
- Accept full session transcripts (JSONL format)
- Parse into conversation turns
- Run extraction pipeline on each turn
- Index with session metadata (sessionKey, timestamp, participants)

### Must Have (Week 2-3)

#### 5. Memory Scoping & Access Control
```
POST /v1/memories/search
{
  "query": "user preferences",
  "scope": {
    "user_id": "seiji",
    "agent_id": "lyn",
    "org_id": "team-seiji",
    "include_shared": true
  }
}
```

#### 6. Real-Time Shared Memory (WebSocket)
```
WS /v1/ws
→ subscribe: { pools: ["shared:team", "agent:luna"] }
← event: { type: "memory.added", memory: {...}, source_agent: "luna" }
```

#### 7. Contradiction Detection & Resolution
When new facts contradict old ones:
- Detect: "User moved to Austin" vs "User lives in NYC"
- Resolve: Keep newest, archive old with timestamp
- Already have basic contradiction detection in SQLite store

#### 8. Memory Decay & Relevance Scoring
- Memories accessed frequently → higher relevance
- Old unaccessed memories → lower priority
- Configurable retention policies
- "Forgetting curve" for natural memory behavior

### Nice to Have (Week 3-4)

#### 9. Entity Graph
- Build entity relationships: Person → works_at → Company
- Entity pages: consolidated view of everything known about an entity
- Graph traversal for multi-hop queries

#### 10. Temporal Reasoning Engine
- Already have 94.6% on temporal questions
- Need: relative time parsing ("last week", "before Christmas")
- Timeline view: chronological history of an entity

#### 11. Memory Reflection (Letta/MemGPT style)
- Periodic "reflection" job that reviews recent memories
- Synthesizes higher-level insights
- Updates entity pages and opinion confidence scores
- Runs as cron job or on compaction

#### 12. Import/Export
- Import from Mem0 (API compatible)
- Import from Cognee (knowledge graph format)
- Export to JSON/Markdown
- Backup/restore

---

## Architecture for Complete Replacement

```
┌─────────────────────────────────────────────────────────┐
│                    OpenClaw Agent                         │
│                                                           │
│  Tools:  memory_search | memory_store | memory_forget    │
│          memory_list   | memory_answer                    │
│                                                           │
│  Hooks:  before_agent_start (auto-recall)                │
│          agent_end (auto-capture)                          │
│          before_compaction (safety flush)                  │
│          after_compaction (re-inject)                      │
└──────────────────┬────────────────────────────────────────┘
                   │ HTTP/WebSocket
                   ▼
┌─────────────────────────────────────────────────────────┐
│                  MemChip Cloud API                        │
│                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │  Ingestion   │  │  Retrieval   │  │  Real-Time     │ │
│  │  Pipeline    │  │  Engine      │  │  Sync (WS)     │ │
│  │             │  │              │  │                │ │
│  │ 5-type      │  │ FTS5 BM25   │  │ Agent events   │ │
│  │ extraction  │  │ + Vector    │  │ Memory pubsub  │ │
│  │ + file      │  │ + Graph     │  │ Subscriptions  │ │
│  │   indexing   │  │ + Temporal  │  │                │ │
│  │ + session   │  │ + RRF fusion│  │                │ │
│  │   transcripts│  │ + Agentic  │  │                │ │
│  └─────────────┘  └──────────────┘  └────────────────┘ │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              Storage Layer                           │ │
│  │                                                     │ │
│  │  PostgreSQL    Redis         S3/Minio               │ │
│  │  (memories,    (cache,       (file backups,         │ │
│  │   entities,    pub/sub,      session transcripts)   │ │
│  │   graphs)      rate limit)                          │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## What MemChip Already Has vs What's Missing

| Component | Have | Missing |
|-----------|------|---------|
| 5-type extraction pipeline | ✅ | — |
| SQLite + FTS5 storage | ✅ | Postgres for multi-tenant |
| Multi-hop reasoning (71.9%) | ✅ | Needs improvement |
| Temporal reasoning (94.6%) | ✅ | — |
| BM25 + graph retrieval | ✅ | — |
| Agentic multi-round search | ✅ | — |
| Chain-of-thought answering | ✅ | — |
| RRF fusion | ✅ | — |
| Contradiction detection | ✅ (basic) | Needs improvement |
| **Vector/embedding search** | ❌ | **Critical — add week 1** |
| **OpenClaw plugin package** | ❌ | **Critical — add week 1** |
| **Auto-recall hook** | ❌ | **Critical — add week 1** |
| **Auto-capture hook** | ❌ | **Critical — add week 1** |
| **Compaction safety hooks** | ❌ | **Critical — add week 1** |
| **File/workspace indexing** | ❌ | **Important — add week 2** |
| **Session transcript ingestion** | ❌ | **Important — add week 2** |
| **Citation with file:line** | ❌ | **Important — add week 2** |
| **REST API** | ❌ | **Critical — add week 1** |
| **WebSocket shared memory** | ❌ | **Important — add week 2** |
| **MCP Server** | ❌ | **Important — add week 2** |
| **Memory decay/relevance** | ❌ | Nice to have |
| **Reflection/synthesis jobs** | ❌ | Nice to have |
| **Entity graph pages** | ❌ | Nice to have |
| **Dashboard** | ❌ | Nice to have |

---

## Priority Build Order

### Sprint 1 (Week 1): Core API + OpenClaw Plugin
1. FastAPI REST endpoints (add, search, list, delete, answer)
2. Vector embedding search (all-MiniLM-L6-v2)
3. Hybrid search (BM25 + vector + graph, RRF)
4. `openclaw-memchip` npm plugin package
5. Auto-recall hook (before_agent_start)
6. Auto-capture hook (agent_end)
7. Compaction hooks (before/after_compaction)
8. Deploy API on Hostinger VPS

### Sprint 2 (Week 2): File Indexing + Sessions + Shared Memory
1. Workspace file watcher + incremental indexing
2. Session transcript ingestion pipeline
3. Citation support (file:line references)
4. WebSocket real-time sync
5. Agent-scoped memory pools
6. Cross-agent shared memory

### Sprint 3 (Week 3): MCP + SDKs + Polish
1. MCP Server (SSE + stdio transport)
2. Python SDK (`pip install memchip`)
3. JavaScript SDK (`npm install @memchip/sdk`)
4. Memory decay + relevance scoring
5. Import from Mem0/Cognee

### Sprint 4 (Week 4): Dashboard + Production
1. Web dashboard (memory browser, usage analytics)
2. Production hardening (auth, rate limits, monitoring)
3. Documentation + examples
4. Launch on GitHub

---

## Config (target)

```json
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
          "agentId": "lyn",
          "orgId": "team-seiji",
          "autoRecall": true,
          "autoCapture": true,
          "topK": 5,
          "sharedPools": ["team", "memchip-project"],
          "compactionFlush": true,
          "sessionIndexing": true,
          "workspaceIndexing": true,
          "embeddingModel": "local"
        }
      }
    }
  }
}
```

When this is done, you delete the Cognee config, add MemChip, and everything works the same — but better.

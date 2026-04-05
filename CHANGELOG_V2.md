# MemChip v0.2.0 — Ecosystem Release

## New Features (15 total)

### 🔴 Critical
1. **Memory Deduplication** — ADD/UPDATE/NOOP on ingest based on embedding similarity
2. **MCP Server** — stdio transport for Claude Code, Cursor, Windsurf (`mcp/mcp_server.py`)
3. **Pool Access Control** — read/write/admin permissions per agent per pool
4. **Memory Decay & Relevance** — exponential decay + access reinforcement scoring
5. **Python SDK** — `pip install memchip` (`sdk/python/`)
6. **TypeScript SDK** — `npm install memchip` (`sdk/typescript/`)

### 🟡 Important
7. **Structured Memory Schemas** — custom types (customer_ticket, trade_signal) with typed fields
8. **Memory Provenance / Audit Log** — tracks who created/modified/deleted every memory
9. **Webhooks** — HTTP callbacks on memory.added, memory.updated, memory.deleted, memory.searched
10. **Conversation Sessions** — short-term memory with auto-expiry
11. **Bulk Import/Export** — JSON import/export for migration

### 🟢 Nice to Have
12. **Memory Analytics** — growth trends, agent activity, category distribution
13. **Memory Instructions** — custom rules for what to store/ignore
14. **Decay Cleanup** — remove memories below relevance threshold
15. **Decay Preview** — see which memories are losing relevance

## New API Endpoints
- `POST /v1/sessions/` — create session
- `GET /v1/sessions/` — list sessions
- `DELETE /v1/sessions/{id}` — delete session + its memories
- `POST /v1/pools/access/` — grant pool access
- `GET /v1/pools/{id}/access/` — list pool access
- `DELETE /v1/pools/access/{id}` — revoke access
- `POST /v1/webhooks/` — create webhook
- `GET /v1/webhooks/` — list webhooks
- `DELETE /v1/webhooks/{id}` — delete webhook
- `POST /v1/schemas/` — create custom memory schema
- `GET /v1/schemas/` — list schemas
- `DELETE /v1/schemas/{id}` — delete schema
- `POST /v1/instructions/` — create memory instruction
- `GET /v1/instructions/` — list instructions
- `DELETE /v1/instructions/{id}` — delete instruction
- `POST /v1/memories/bulk/import/` — bulk import
- `POST /v1/memories/bulk/export/` — bulk export
- `GET /v1/audit/` — provenance/audit log
- `GET /v1/analytics/` — memory analytics
- `POST /v1/decay/cleanup/` — remove decayed memories
- `GET /v1/decay/preview/` — preview decay scores

## New Database Tables
- `memory_sessions` — conversation-scoped sessions
- `pool_access` — ACL for shared pools
- `webhooks` — webhook configurations
- `memory_audit` — provenance tracking
- `memory_schemas` — custom memory type definitions
- `memory_instructions` — storage rules

## SDKs
- Python: `sdk/python/` — install with `pip install .`
- TypeScript: `sdk/typescript/` — install with `npm install .`

## MCP Server
- `mcp/mcp_server.py` — Model Context Protocol server
- Works with Claude Code, Cursor, Windsurf, any MCP client
- 5 tools: memory_store, memory_search, memory_answer, memory_list, memory_delete

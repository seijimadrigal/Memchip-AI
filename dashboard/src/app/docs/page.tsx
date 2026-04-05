"use client";

import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  BookOpen,
  Zap,
  Server,
  Code2,
  Layers,
  Package,
  Bot,
} from "lucide-react";

// ── Helpers ──────────────────────────────────────────────

function MethodBadge({ method }: { method: string }) {
  const colors: Record<string, string> = {
    GET: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    POST: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    PUT: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    DELETE: "bg-red-500/20 text-red-400 border-red-500/30",
  };
  return (
    <Badge variant="outline" className={`font-mono text-[11px] px-1.5 py-0 ${colors[method] || ""}`}>
      {method}
    </Badge>
  );
}

function CodeBlock({ code, lang = "bash" }: { code: string; lang?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="relative group rounded-lg bg-muted border border-border overflow-hidden my-3">
      <div className="flex items-center justify-between px-4 py-1.5 bg-card border-b border-border">
        <span className="text-[11px] text-muted-foreground font-mono">{lang}</span>
        <button onClick={copy} className="text-muted-foreground hover:text-foreground transition-colors">
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      </div>
      <pre className="p-4 overflow-x-auto text-[13px] leading-relaxed">
        <code className="text-foreground/80 font-mono">{code}</code>
      </pre>
    </div>
  );
}

function Collapsible({ title, children, defaultOpen = false }: { title: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-border rounded-lg overflow-hidden my-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full px-4 py-3 text-left text-sm font-medium hover:bg-accent/50 transition-colors"
      >
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        {title}
      </button>
      {open && <div className="px-4 pb-4 border-t border-border">{children}</div>}
    </div>
  );
}

function Endpoint({ method, path, desc, body, response }: { method: string; path: string; desc: string; body?: string; response?: string }) {
  return (
    <Collapsible
      title={
        <span className="flex items-center gap-2">
          <MethodBadge method={method} />
          <code className="text-[13px] font-mono text-foreground">{path}</code>
          <span className="text-muted-foreground font-normal ml-2">— {desc}</span>
        </span>
      }
    >
      {body && (
        <div className="mt-2">
          <p className="text-xs text-muted-foreground mb-1 font-medium">Request Body</p>
          <CodeBlock code={body} lang="json" />
        </div>
      )}
      {response && (
        <div className="mt-2">
          <p className="text-xs text-muted-foreground mb-1 font-medium">Response</p>
          <CodeBlock code={response} lang="json" />
        </div>
      )}
    </Collapsible>
  );
}

// ── TOC ──────────────────────────────────────────────────

const sections = [
  { id: "quickstart", label: "Quick Start", icon: Zap },
  { id: "openclaw", label: "OpenClaw Integration", icon: Server },
  { id: "agent-guide", label: "Agent Best Practices", icon: Bot },
  { id: "mcp", label: "Claude Code / MCP", icon: Code2 },
  { id: "api", label: "REST API Reference", icon: BookOpen },
  { id: "concepts", label: "Concepts", icon: Layers },
  { id: "sdks", label: "SDKs", icon: Package },
];

// ── Page ─────────────────────────────────────────────────

export default function DocsPage() {
  const [activeSection, setActiveSection] = useState("quickstart");

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id);
          }
        }
      },
      { rootMargin: "-20% 0px -60% 0px" }
    );
    sections.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, []);

  return (
    <div className="flex min-h-screen">
      {/* Left TOC */}
      <nav className="hidden lg:block w-56 shrink-0 sticky top-0 h-screen overflow-y-auto border-r border-border p-4">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-3">
          On this page
        </p>
        <div className="space-y-0.5">
          {sections.map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors ${
                activeSection === s.id
                  ? "bg-accent text-accent-foreground font-medium"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
              }`}
            >
              <s.icon className="h-3.5 w-3.5" />
              {s.label}
            </a>
          ))}
        </div>
      </nav>

      {/* Content */}
      <main className="flex-1 max-w-4xl px-6 py-8 space-y-16 overflow-y-auto">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-2">MemChip Documentation</h1>
          <p className="text-muted-foreground">
            Everything you need to integrate with MemChip — hybrid memory orchestrator for AI agents.
          </p>
        </div>

        {/* ── Section 1: Quick Start ── */}
        <section id="quickstart" className="scroll-mt-8 space-y-4">
          <h2 className="text-2xl font-bold tracking-tight border-b border-border pb-2">Quick Start</h2>
          <p className="text-muted-foreground leading-relaxed">
            <strong className="text-foreground">MemChip</strong> is a hybrid memory orchestrator for AI agents.
            It combines auto-recall (structured context injection), async auto-capture, a dynamic memory profile endpoint,
            and shared memory pools — all through a simple REST API. Currently at <Badge variant="outline">v0.6.0</Badge>.
          </p>

          <Card className="bg-card">
            <CardContent className="pt-4 space-y-3">
              <p className="text-sm font-medium">Base URL</p>
              <CodeBlock code="http://76.13.23.55/v1/" lang="text" />
              <p className="text-sm font-medium">Authentication</p>
              <p className="text-sm text-muted-foreground">
                Include your API key as a Bearer token in the <code className="text-xs bg-muted px-1 py-0.5 rounded">Authorization</code> header.
                Generate per-agent keys via the Admin API.
              </p>
              <CodeBlock code='Authorization: Bearer mc_your_api_key' lang="http" />
            </CardContent>
          </Card>

          <h3 className="text-lg font-semibold mt-6">Store a memory</h3>
          <CodeBlock
            lang="bash"
            code={`curl -X POST http://76.13.23.55/v1/memories/ \\
  -H "Authorization: Bearer mc_xxx" \\
  -H "Content-Type: application/json" \\
  -d '{
    "text": "User prefers dark mode and vim keybindings",
    "user_id": "seiji",
    "agent_id": "lyn"
  }'`}
          />

          <h3 className="text-lg font-semibold">Search it back</h3>
          <CodeBlock
            lang="bash"
            code={`curl -X POST http://76.13.23.55/v1/memories/search/ \\
  -H "Authorization: Bearer mc_xxx" \\
  -H "Content-Type: application/json" \\
  -d '{
    "query": "user preferences",
    "user_id": "seiji",
    "top_k": 15
  }'`}
          />
        </section>

        {/* ── Section 2: OpenClaw Integration ── */}
        <section id="openclaw" className="scroll-mt-8 space-y-4">
          <h2 className="text-2xl font-bold tracking-tight border-b border-border pb-2">OpenClaw Integration</h2>
          <p className="text-muted-foreground">Add persistent memory to any OpenClaw agent in three steps.</p>

          <h3 className="text-lg font-semibold">1. Copy the plugin</h3>
          <CodeBlock
            lang="bash"
            code="scp -r root@76.13.23.55:/usr/lib/node_modules/openclaw/dist/extensions/openclaw-memchip/ \\\n  /usr/lib/node_modules/openclaw/dist/extensions/"
          />

          <h3 className="text-lg font-semibold">2. Add to openclaw.json</h3>
          <CodeBlock
            lang="json"
            code={`{
  "plugins": {
    "slots": {
      "memory": "openclaw-memchip"
    },
    "entries": {
      "openclaw-memchip": {
        "enabled": true,
        "config": {
          "apiUrl": "http://76.13.23.55/v1",
          "apiKey": "mc_your_api_key",
          "userId": "your_user_id",
          "agentId": "your_agent_id",
          "orgId": "your_org_id",
          "autoRecall": true,
          "autoCapture": true,
          "topK": 15,
          "sharedPools": ["shared:team"],
          "compactionFlush": true
        }
      }
    }
  }
}`}
          />
          <p className="text-xs text-muted-foreground mt-2 ml-1">
            <strong>Key fields:</strong> <code>slots.memory</code> tells OpenClaw to use MemChip as the primary memory plugin.
            <code> sharedPools</code> enables cross-agent memory sharing. <code>compactionFlush</code> saves context before it gets trimmed.
          </p>

          <h3 className="text-lg font-semibold">3. Restart the gateway</h3>
          <CodeBlock lang="bash" code="openclaw gateway restart" />

          <h3 className="text-lg font-semibold mt-6">Available Tools</h3>
          <div className="grid gap-3">
            {[
              { name: "memory_store", params: "text, pool_id?, scope?, source_type?", desc: "Store a new memory. Text is processed for importance and conflict detection." },
              { name: "memory_search", params: "query, top_k?", desc: "Semantic search across accessible memories." },
              { name: "memory_forget", params: "query", desc: "Delete memories matching a query. Omit query to delete all." },
              { name: "memory_list", params: "limit?, offset?", desc: "List all stored memories with pagination." },
            ].map((t) => (
              <Card key={t.name} className="bg-card">
                <CardContent className="py-3 flex items-start gap-3">
                  <code className="text-sm font-mono text-primary whitespace-nowrap">{t.name}</code>
                  <div>
                    <p className="text-sm text-muted-foreground">{t.desc}</p>
                    <p className="text-xs text-muted-foreground/60 mt-1">Params: <code>{t.params}</code></p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        {/* ── Section 3: Agent Best Practices ── */}
        <section id="agent-guide" className="scroll-mt-8 space-y-6">
          <h2 className="text-2xl font-bold tracking-tight border-b border-border pb-2">Agent Best Practices</h2>
          <p className="text-muted-foreground">
            How to get the most out of MemChip as an OpenClaw agent. This guide covers what gets captured automatically,
            what you should store manually, and how to avoid common pitfalls.
          </p>

          <Card className="bg-card">
            <CardContent className="pt-4">
              <h3 className="text-base font-semibold mb-2">How Auto-Capture Works <Badge variant="outline" className="ml-2">v0.6.0</Badge></h3>
              <p className="text-sm text-muted-foreground mb-3">
                MemChip captures memories from <strong className="text-foreground">three sources</strong> automatically:
              </p>
              <ul className="text-sm text-muted-foreground space-y-3 list-disc ml-4">
                <li>
                  <strong className="text-foreground">Tool Results</strong> (<code className="text-xs bg-muted px-1 py-0.5 rounded">after_tool_call</code> hook) —
                  When you run shell commands, API calls, or deployments, the results are captured in real-time.
                  Only high-signal tools are stored: <code className="text-xs bg-muted px-1 py-0.5 rounded">exec</code>,{" "}
                  <code className="text-xs bg-muted px-1 py-0.5 rounded">web_search</code>,{" "}
                  <code className="text-xs bg-muted px-1 py-0.5 rounded">web_fetch</code>,{" "}
                  <code className="text-xs bg-muted px-1 py-0.5 rounded">message</code>,{" "}
                  <code className="text-xs bg-muted px-1 py-0.5 rounded">gateway</code>,{" "}
                  <code className="text-xs bg-muted px-1 py-0.5 rounded">sessions_spawn</code>.
                  Noise (polls, reads, heartbeats) is filtered out.
                </li>
                <li>
                  <strong className="text-foreground">Conversation</strong> (<code className="text-xs bg-muted px-1 py-0.5 rounded">agent_end</code> hook) —
                  At the end of each turn, the last 4 user/assistant messages plus any tool action summaries are stored together.
                </li>
                <li>
                  <strong className="text-foreground">Pre-Compaction</strong> (<code className="text-xs bg-muted px-1 py-0.5 rounded">before_compaction</code> hook) —
                  When the context window gets full and OpenClaw trims old messages, MemChip saves the at-risk content first.
                  This is your last-chance safety net.
                </li>
              </ul>
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardContent className="pt-4">
              <h3 className="text-base font-semibold mb-2">What Gets Extracted</h3>
              <p className="text-sm text-muted-foreground mb-3">
                Every captured text is processed by the extraction pipeline into 5 memory types:
              </p>
              <div className="grid gap-2">
                {[
                  { type: "summary", desc: "Concise overview of the conversation or action", example: "VPS disk cleanup freed 101GB by removing EverMemOS stack" },
                  { type: "triple", desc: "Structured subject-predicate-object facts", example: "VPS disk usage → 19%" },
                  { type: "profile", desc: "Key-value attributes about people/systems", example: "user preference: dark mode = true" },
                  { type: "temporal", desc: "Time-anchored events", example: "Deployed MemChip v0.6.0 on 2026-04-05" },
                  { type: "raw", desc: "Full text preserved verbatim for context", example: "Complete conversation transcript" },
                ].map((t) => (
                  <div key={t.type} className="flex items-start gap-3 px-3 py-2 rounded-md bg-muted/30">
                    <Badge variant="outline" className="font-mono text-[11px] mt-0.5 shrink-0">{t.type}</Badge>
                    <div>
                      <p className="text-sm text-muted-foreground">{t.desc}</p>
                      <p className="text-xs text-muted-foreground/60 mt-0.5 italic">{t.example}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardContent className="pt-4">
              <h3 className="text-base font-semibold mb-2">When to Store Manually</h3>
              <p className="text-sm text-muted-foreground mb-3">
                Auto-capture is good but not perfect. Use <code className="text-xs bg-muted px-1 py-0.5 rounded">memory_store</code> explicitly for:
              </p>
              <ul className="text-sm text-muted-foreground space-y-2 list-disc ml-4">
                <li><strong className="text-foreground">Decisions & rationale</strong> — &quot;We chose PostgreSQL over MongoDB because...&quot;</li>
                <li><strong className="text-foreground">User preferences</strong> — &quot;User wants no emojis on product pages&quot;</li>
                <li><strong className="text-foreground">Credentials & config</strong> — API keys, server IPs, account details (stored securely)</li>
                <li><strong className="text-foreground">Project milestones</strong> — &quot;Phase 1 complete, moving to Phase 2&quot;</li>
                <li><strong className="text-foreground">Lessons learned</strong> — &quot;Never use ORDER_FILLING_IOC with FXTM broker&quot;</li>
                <li><strong className="text-foreground">Cross-session context</strong> — anything the next session absolutely needs to know</li>
              </ul>
              <CodeBlock
                lang="bash"
                code={`# Example: Store a decision with context
memory_store(
  text="Decided to use Zamba2-2.7B for the universal memory model. Reason: constant memory at inference, O(n) linear scaling, 3 memory systems.",
  source_type="agent_reasoning",
  scope="project"
)`}
              />
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardContent className="pt-4">
              <h3 className="text-base font-semibold mb-2">Shared Memory Pools</h3>
              <p className="text-sm text-muted-foreground mb-3">
                Multiple agents can read and write to the same memory pool. This is how teams collaborate.
              </p>
              <CodeBlock
                lang="json"
                code={`// In openclaw.json — both agents use the same shared pool
{
  "sharedPools": ["shared:team"]
}

// Agent A stores a memory
memory_store(text="API deployed to prod", pool_id="shared:team")

// Agent B searches and finds it
memory_search(query="deployment status", pool_id="shared:team")`}
              />
              <p className="text-xs text-muted-foreground mt-2">
                <strong>Tip:</strong> Use <code className="text-xs bg-muted px-1 py-0.5 rounded">scope: &quot;team&quot;</code> for memories
                that should be visible to all agents, <code className="text-xs bg-muted px-1 py-0.5 rounded">scope: &quot;private&quot;</code> for
                agent-specific context.
              </p>
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardContent className="pt-4">
              <h3 className="text-base font-semibold mb-2">Common Pitfalls</h3>
              <div className="space-y-3">
                {[
                  {
                    bad: "Storing every message verbatim",
                    good: "Let auto-capture handle conversation; manually store only decisions and insights",
                    why: "Noise drowns out signal. The extraction pipeline already creates summaries and triples."
                  },
                  {
                    bad: "Not setting source_type on manual stores",
                    good: "Always include source_type: 'agent_reasoning', 'conversation', 'research', etc.",
                    why: "Source types help with filtering and understanding where knowledge came from."
                  },
                  {
                    bad: "Ignoring pool_id for team memories",
                    good: "Use pool_id='shared:team' when storing info other agents need",
                    why: "Without pool_id, memories default to private scope — invisible to teammates."
                  },
                  {
                    bad: "Storing secrets in global scope",
                    good: "Use scope='private' for credentials, API keys, passwords",
                    why: "Global/team scope memories are visible to all agents in the org."
                  },
                ].map((p, i) => (
                  <div key={i} className="rounded-lg border border-border p-3 space-y-1.5">
                    <div className="flex items-start gap-2">
                      <span className="text-red-400 text-sm">✗</span>
                      <p className="text-sm text-muted-foreground">{p.bad}</p>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-emerald-400 text-sm">✓</span>
                      <p className="text-sm text-foreground">{p.good}</p>
                    </div>
                    <p className="text-xs text-muted-foreground/60 ml-5">{p.why}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardContent className="pt-4">
              <h3 className="text-base font-semibold mb-2">Recommended AGENTS.md Snippet</h3>
              <p className="text-sm text-muted-foreground mb-3">
                Add this to your agent&apos;s workspace instructions so it knows how to use MemChip effectively:
              </p>
              <CodeBlock
                lang="markdown"
                code={`## Memory (MemChip)

MemChip is your long-term memory. It auto-captures tool results and conversations.

### What to store manually:
- Decisions and why they were made
- User preferences and corrections
- Project milestones and status changes
- Credentials and config (scope: private)
- Lessons learned from mistakes

### How to store:
- Use memory_store(text, source_type, scope) for important facts
- Use pool_id="shared:team" for things teammates need
- Use scope="private" for secrets

### How to search:
- memory_search(query) finds relevant memories semantically
- Check memory before asking the user to repeat themselves

### What NOT to do:
- Don't store every message — auto-capture handles that
- Don't store secrets in team/global scope
- Don't forget to set source_type`}
              />
            </CardContent>
          </Card>
        </section>

        {/* ── Section 4: MCP ── */}
        <section id="mcp" className="scroll-mt-8 space-y-4">
          <h2 className="text-2xl font-bold tracking-tight border-b border-border pb-2">Claude Code / MCP Integration</h2>
          <p className="text-muted-foreground">
            Use MemChip as an MCP server for Claude Code, Cursor, or any MCP-compatible client.
          </p>

          <h3 className="text-lg font-semibold">MCP Server</h3>
          <p className="text-sm text-muted-foreground">Located at <code className="text-xs bg-muted px-1 py-0.5 rounded">memchip/mcp/mcp_server.py</code></p>

          <h3 className="text-lg font-semibold">Configuration</h3>
          <p className="text-sm text-muted-foreground mb-2">Add to <code className="text-xs bg-muted px-1 py-0.5 rounded">~/.claude/mcp.json</code>:</p>
          <CodeBlock
            lang="json"
            code={`{
  "mcpServers": {
    "memchip": {
      "command": "python3",
      "args": [
        "/path/to/mcp_server.py",
        "--api-url", "http://76.13.23.55/v1",
        "--api-key", "YOUR_KEY",
        "--user-id", "seiji"
      ]
    }
  }
}`}
          />

          <h3 className="text-lg font-semibold mt-4">MCP Tools</h3>
          <div className="grid gap-2">
            {[
              { name: "memory_store", desc: "Store a memory with automatic enrichment" },
              { name: "memory_search", desc: "Semantic search with optional agentic reasoning" },
              { name: "memory_answer", desc: "Search and synthesize an answer from memories" },
              { name: "memory_list", desc: "List memories with filters" },
              { name: "memory_delete", desc: "Delete a specific memory by ID" },
            ].map((t) => (
              <div key={t.name} className="flex items-center gap-3 px-3 py-2 rounded-md bg-muted/30">
                <code className="text-sm font-mono text-primary">{t.name}</code>
                <span className="text-sm text-muted-foreground">{t.desc}</span>
              </div>
            ))}
          </div>
        </section>

        {/* ── Section 4: REST API Reference ── */}
        <section id="api" className="scroll-mt-8 space-y-6">
          <h2 className="text-2xl font-bold tracking-tight border-b border-border pb-2">REST API Reference</h2>

          {/* Memories */}
          <div>
            <h3 className="text-lg font-semibold mb-2">Memories</h3>
            <Endpoint method="POST" path="/v1/memories/" desc="Add a memory"
              body={`{
  "text": "User prefers dark mode",
  "user_id": "seiji",
  "agent_id": "lyn",
  "pool_id": "default",
  "scope": "private",
  "source_type": "api"
}`}
              response={`{
  "id": "mem_abc123",
  "text": "User prefers dark mode",
  "importance": 3,
  "created_at": "2026-04-04T08:00:00Z"
}`}
            />
            <Endpoint method="POST" path="/v1/memories/search/" desc="Semantic search"
              body={`{
  "query": "user preferences",
  "user_id": "seiji",
  "agent_id": "lyn",
  "pool_id": "default",
  "top_k": 15,
  "agentic": false
}`}
              response={`{
  "results": [
    {
      "id": "mem_abc123",
      "text": "User prefers dark mode",
      "score": 0.92
    }
  ]
}`}
            />
            <Endpoint method="GET" path="/v1/memories/" desc="List memories"
              body={`Query params: user_id, agent_id, pool_id,
memory_type, scope, limit, offset`}
            />
            <Endpoint method="PUT" path="/v1/memories/{id}" desc="Update a memory"
              body={`{
  "text": "Updated memory text"
}`}
            />
            <Endpoint method="DELETE" path="/v1/memories/{id}" desc="Archive (soft delete)" />
            <Endpoint method="GET" path="/v1/memories/{id}/history/" desc="Event history for a memory" />
            <Endpoint method="GET" path="/v1/memories/{id}/conflicts/" desc="Conflict chain" />
            <Endpoint method="POST" path="/v1/memories/{id}/resolve/" desc="Resolve a conflict"
              body={`{
  "resolution": "supersede",
  "winner_id": "mem_abc123"
}`}
            />
          </div>

          {/* Memory Profile */}
          <div>
            <h3 className="text-lg font-semibold mb-2">Memory Profile</h3>
            <Endpoint method="GET" path="/v1/agents/{agent_id}/profile/" desc="Dynamic MEMORY.md-like structured summary"
              response={`{
  "agent_id": "lyn",
  "profile": "## User Preferences\\n- Dark mode...\\n\\n## Key Decisions\\n...",
  "memory_count": 142,
  "generated_at": "2026-04-04T08:00:00Z"
}`}
            />
          </div>

          {/* Projects */}
          <div>
            <h3 className="text-lg font-semibold mb-2">Projects</h3>
            <Endpoint method="POST" path="/v1/projects/" desc="Create project" body={`{ "name": "My Project", "description": "..." }`} />
            <Endpoint method="GET" path="/v1/projects/" desc="List projects" />
            <Endpoint method="GET" path="/v1/projects/{id}" desc="Get project" />
            <Endpoint method="PUT" path="/v1/projects/{id}" desc="Update project" />
            <Endpoint method="DELETE" path="/v1/projects/{id}" desc="Delete project" />
          </div>

          {/* Agent Context */}
          <div>
            <h3 className="text-lg font-semibold mb-2">Agent Context</h3>
            <Endpoint method="GET" path="/v1/agents/{agent_id}/context/" desc="Get agent context" />
            <Endpoint method="PUT" path="/v1/agents/{agent_id}/context/" desc="Update agent context"
              body={`{ "active_project_id": "proj_xxx", "default_scope": "team" }`}
            />
            <Endpoint method="DELETE" path="/v1/agents/{agent_id}/context/" desc="Clear agent context" />
          </div>

          {/* Pools & Access */}
          <div>
            <h3 className="text-lg font-semibold mb-2">Pools & Access</h3>
            <Endpoint method="POST" path="/v1/pools/access/" desc="Grant pool access"
              body={`{ "pool_id": "pool_xxx", "agent_id": "lyn", "permission": "read" }`}
            />
            <Endpoint method="GET" path="/v1/pools/{pool_id}/access/" desc="List ACL for a pool" />
          </div>

          {/* Events & Subscriptions */}
          <div>
            <h3 className="text-lg font-semibold mb-2">Events & Subscriptions</h3>
            <Endpoint method="GET" path="/v1/events/" desc="Event stream (query: after, limit, event_type)" />
            <Endpoint method="POST" path="/v1/subscriptions/" desc="Create subscription"
              body={`{ "url": "https://example.com/webhook", "event_types": ["memory.created"] }`}
            />
            <Endpoint method="GET" path="/v1/subscriptions/" desc="List subscriptions" />
            <Endpoint method="DELETE" path="/v1/subscriptions/{id}" desc="Delete subscription" />
          </div>

          {/* Admin */}
          <div>
            <h3 className="text-lg font-semibold mb-2">Admin</h3>
            <Endpoint method="GET" path="/v1/admin/keys/" desc="List API keys for all agents" />
            <Endpoint method="POST" path="/v1/admin/keys/" desc="Generate per-agent API key"
              body={`{
  "name": "lyn-prod",
  "agent_id": "lyn",
  "scopes": ["memories:read", "memories:write"]
}`}
              response={`{
  "id": "key_abc123",
  "key": "mc_live_...",
  "name": "lyn-prod",
  "agent_id": "lyn",
  "created_at": "2026-04-04T08:00:00Z"
}`}
            />
            <Endpoint method="DELETE" path="/v1/admin/keys/{id}" desc="Revoke API key" />
          </div>

          {/* Bulk Operations */}
          <div>
            <h3 className="text-lg font-semibold mb-2">Bulk Operations</h3>
            <Endpoint method="POST" path="/v1/memories/bulk/import/" desc="Bulk import memories" />
            <Endpoint method="POST" path="/v1/memories/bulk/export/" desc="Bulk export memories" />
            <Endpoint method="POST" path="/v1/memories/bulk/delete/" desc="Bulk soft-delete up to 100 memories by ID"
              body={`{
  "memory_ids": [
    "mem_abc123",
    "mem_def456",
    "mem_ghi789"
  ]
}`}
              response={`{
  "status": "ok",
  "total": 3,
  "deleted": 2,
  "errors": [
    { "id": "mem_ghi789", "error": "Not found" }
  ]
}`}
            />
            <p className="text-xs text-muted-foreground mt-2 ml-1">
              Note: This performs a <strong>soft delete</strong> (archive). Memories can be recovered.
              Maximum 100 IDs per request.
            </p>
          </div>

          {/* Other */}
          <div>
            <h3 className="text-lg font-semibold mb-2">Other</h3>
            <Endpoint method="GET" path="/v1/health" desc="Health check" />
            <Endpoint method="GET" path="/v1/stats/" desc="System statistics" />
            <Endpoint method="GET" path="/v1/analytics/" desc="Analytics data" />
            <Endpoint method="GET" path="/v1/graph/" desc="Memory relationship graph" />
            <Endpoint method="GET" path="/v1/decay/preview/" desc="Preview decay effects" />
            <Endpoint method="POST" path="/v1/decay/cleanup/" desc="Run decay cleanup" />
          </div>
        </section>

        {/* ── Section 5: Concepts ── */}
        <section id="concepts" className="scroll-mt-8 space-y-6">
          <h2 className="text-2xl font-bold tracking-tight border-b border-border pb-2">Concepts</h2>

          <div className="grid gap-4">
            <Card className="bg-card">
              <CardContent className="pt-4">
                <h3 className="text-base font-semibold mb-2">Hybrid Memory Architecture</h3>
                <p className="text-sm text-muted-foreground mb-3">
                  MemChip acts as a hybrid memory orchestrator combining multiple memory strategies:
                </p>
                <ul className="text-sm text-muted-foreground space-y-2 list-disc ml-4">
                  <li><strong className="text-foreground">Auto-Recall</strong> — structured context injection. On each turn, the top 15 relevant memories are fetched and injected as system context. Retrieval is pure relevance: vector similarity + BM25 + time decay.</li>
                  <li><strong className="text-foreground">Auto-Capture</strong> <Badge variant="outline" className="ml-1 text-[10px]">v0.6.0</Badge> — tool-aware, async capture. Captures conversation text AND tool results (shell commands, deployments, API calls) via <code className="text-xs bg-muted px-1 py-0.5 rounded">after_tool_call</code>, <code className="text-xs bg-muted px-1 py-0.5 rounded">agent_end</code>, and <code className="text-xs bg-muted px-1 py-0.5 rounded">before_compaction</code> hooks. Noise (heartbeats, polls, reads) is filtered out automatically.</li>
                  <li><strong className="text-foreground">Memory Profile</strong> — a dynamic MEMORY.md-like summary generated on demand via the profile endpoint.</li>
                  <li><strong className="text-foreground">Shared Pools</strong> — agents collaborate through shared memory pools with ACL-based access control.</li>
                </ul>
              </CardContent>
            </Card>

            <Card className="bg-card">
              <CardContent className="pt-4">
                <h3 className="text-base font-semibold mb-2">Memory Profile</h3>
                <p className="text-sm text-muted-foreground">
                  The <code className="text-xs bg-muted px-1 py-0.5 rounded">GET /v1/agents/{"{agent_id}"}/profile/</code> endpoint
                  returns a dynamically generated structured summary of an agent&apos;s memory — like a living MEMORY.md.
                  It distills preferences, key decisions, facts, and patterns from stored memories into a concise document
                  that can be injected as system context or used for agent introspection.
                </p>
              </CardContent>
            </Card>

            <Card className="bg-card">
              <CardContent className="pt-4">
                <h3 className="text-base font-semibold mb-2">Memory Scopes</h3>
                <p className="text-sm text-muted-foreground mb-3">Control visibility and lifetime of memories.</p>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                  {["private", "task", "project", "team", "global"].map((s) => (
                    <div key={s} className="text-center px-2 py-1.5 rounded-md bg-muted/40 text-xs font-mono">{s}</div>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  <strong>private</strong> — only the creating agent; <strong>task</strong> — within active task;
                  <strong> project</strong> — all agents on a project; <strong>team</strong> — all agents of a user;
                  <strong> global</strong> — all agents system-wide.
                </p>
              </CardContent>
            </Card>

            <Card className="bg-card">
              <CardContent className="pt-4">
                <h3 className="text-base font-semibold mb-2">Importance Scoring</h3>
                <p className="text-sm text-muted-foreground mb-3">
                  Every memory is auto-scored 0–5. Importance is used for <strong className="text-foreground">write filtering only</strong> —
                  low-importance content may be dropped at capture time. It does <em>not</em> affect retrieval ranking.
                </p>
                <div className="space-y-1 text-sm">
                  {[
                    { score: 0, label: "Noise", color: "text-gray-500" },
                    { score: 1, label: "Ops", color: "text-gray-400" },
                    { score: 2, label: "Routine", color: "text-blue-400" },
                    { score: 3, label: "Significant", color: "text-yellow-400" },
                    { score: 4, label: "Critical", color: "text-orange-400" },
                    { score: 5, label: "Foundational", color: "text-red-400" },
                  ].map((t) => (
                    <div key={t.score} className="flex items-center gap-2">
                      <Badge variant="outline" className="font-mono w-6 justify-center">{t.score}</Badge>
                      <span className={t.color}>{t.label}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card className="bg-card">
              <CardContent className="pt-4">
                <h3 className="text-base font-semibold mb-2">Conflict Detection</h3>
                <p className="text-sm text-muted-foreground">
                  When a new memory contradicts an existing one, MemChip detects the conflict and resolves it.
                  Dedup thresholds: <strong className="text-foreground">supersede</strong> at 0.88 similarity,
                  <strong className="text-foreground"> chain</strong> at 0.80 similarity.
                </p>
                <ul className="text-sm text-muted-foreground mt-2 space-y-1 list-disc ml-4">
                  <li><strong className="text-foreground">supersede</strong> — new memory replaces the old one (≥0.88 similarity)</li>
                  <li><strong className="text-foreground">chain</strong> — both kept, linked as an evolution (≥0.80 similarity)</li>
                  <li><strong className="text-foreground">new</strong> — no conflict, stored independently</li>
                </ul>
              </CardContent>
            </Card>

            <Card className="bg-card">
              <CardContent className="pt-4">
                <h3 className="text-base font-semibold mb-2">Agent Isolation</h3>
                <p className="text-sm text-muted-foreground">
                  Each agent can only access its own memories and pools explicitly shared via ACL.
                  This prevents data leakage between agents while enabling controlled collaboration.
                </p>
              </CardContent>
            </Card>

            <Card className="bg-card">
              <CardContent className="pt-4">
                <h3 className="text-base font-semibold mb-2">Auto-Routing</h3>
                <p className="text-sm text-muted-foreground">
                  Memories are automatically routed to the right pool based on agent context:
                </p>
                <div className="flex items-center gap-2 mt-2 text-sm font-mono text-muted-foreground">
                  <span className="text-primary">agent context</span> → <span>task pool</span> → <span>project pool</span> → <span>default</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>

        {/* ── Section 6: SDKs ── */}
        <section id="sdks" className="scroll-mt-8 space-y-4">
          <h2 className="text-2xl font-bold tracking-tight border-b border-border pb-2">SDKs</h2>

          <Tabs defaultValue="python">
            <TabsList>
              <TabsTrigger value="python">Python</TabsTrigger>
              <TabsTrigger value="typescript">TypeScript</TabsTrigger>
            </TabsList>
            <TabsContent value="python">
              <CodeBlock
                lang="python"
                code={`from memchip import MemChip

mc = MemChip(api_key="mc_xxx", base_url="http://76.13.23.55/v1")

# Store a memory
mc.add("User prefers dark mode", user_id="seiji", agent_id="lyn")

# Search
results = mc.search("preferences", user_id="seiji")
for r in results:
    print(f"{r['text']} (score: {r['score']})")

# List all
memories = mc.list(user_id="seiji", limit=20)

# Delete
mc.delete("mem_abc123")`}
              />
            </TabsContent>
            <TabsContent value="typescript">
              <CodeBlock
                lang="typescript"
                code={`import { MemChip } from '@memchip/sdk';

const mc = new MemChip({
  apiKey: 'mc_xxx',
  baseUrl: 'http://76.13.23.55/v1'
});

// Store a memory
await mc.add({
  text: 'User prefers dark mode',
  userId: 'seiji',
  agentId: 'lyn'
});

// Search
const results = await mc.search({
  query: 'preferences',
  userId: 'seiji'
});

// List
const memories = await mc.list({ userId: 'seiji', limit: 20 });

// Delete
await mc.delete('mem_abc123');`}
              />
            </TabsContent>
          </Tabs>
        </section>

        {/* Footer spacer */}
        <div className="h-16" />
      </main>
    </div>
  );
}

"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Search, Trash2, RefreshCw, X, History, AlertTriangle } from "lucide-react";
import { getMemories, searchMemories, deleteMemory, getAgentsList, getMemoryHistory, getMemoryConflicts } from "@/lib/api";
import { toast } from "sonner";

interface Memory {
  id: string;
  content: string;
  memory_type: string;
  agent_id: string;
  pool_id: string;
  confidence: number;
  decay_score: number;
  access_count: number;
  chain_id: string;
  created_at: string;
  scope: string;
  conflict_status: string;
  version: number;
  source_type: string;
  status: string;
  supersedes_id?: string;
  importance: number | null;
}

const IMPORTANCE_LABELS: Record<number, { label: string; color: string }> = {
  0: { label: "Noise", color: "bg-zinc-500/20 text-zinc-500" },
  1: { label: "Ops", color: "bg-zinc-500/20 text-zinc-400" },
  2: { label: "Routine", color: "bg-blue-500/20 text-blue-400" },
  3: { label: "Significant", color: "bg-green-500/20 text-green-400" },
  4: { label: "Critical", color: "bg-orange-500/20 text-orange-400" },
  5: { label: "Core", color: "bg-red-500/20 text-red-400" },
};

interface AgentInfo {
  agent_id: string | null;
  count: number;
}

interface HistoryEvent {
  id: string;
  event_type: string;
  timestamp: string;
  actor_id: string;
  details: string;
}

interface Conflict {
  id: string;
  memory_id: string;
  conflicting_memory_id: string;
  conflict_type: string;
  status: string;
  created_at: string;
}

function timeAgo(date: string): string {
  const now = Date.now();
  const then = new Date(date + "Z").getTime();
  const diff = now - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

const TYPES = ["Overview", "triple", "summary", "profile", "temporal", "raw"];

const SCOPE_COLORS: Record<string, string> = {
  private: "bg-zinc-500/20 text-zinc-400",
  task: "bg-blue-500/20 text-blue-400",
  project: "bg-purple-500/20 text-purple-400",
  team: "bg-green-500/20 text-green-400",
  global: "bg-orange-500/20 text-orange-400",
};

const CONFLICT_COLORS: Record<string, string> = {
  superseded: "bg-yellow-500/20 text-yellow-400",
  disputed: "bg-red-500/20 text-red-400",
};

const SCOPES = ["private", "task", "project", "team", "global"];
const CONFLICT_STATUSES = ["active", "superseded", "disputed"];

export default function MemoriesPage() {
  return (
    <Suspense fallback={<div className="p-8 text-muted-foreground">Loading...</div>}>
      <Content />
    </Suspense>
  );
}

function Content() {
  const searchParams = useSearchParams();
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState(searchParams.get("q") || "");
  const [activeTab, setActiveTab] = useState("Overview");
  const [detailMem, setDetailMem] = useState<Memory | null>(null);

  // Filters
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [selectedScope, setSelectedScope] = useState<string>("");
  const [selectedConflictStatus, setSelectedConflictStatus] = useState<string>("");
  const [selectedImportance, setSelectedImportance] = useState<string>("");

  // History & Conflicts dialogs
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyEvents, setHistoryEvents] = useState<HistoryEvent[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [conflictsOpen, setConflictsOpen] = useState(false);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [conflictsLoading, setConflictsLoading] = useState(false);

  useEffect(() => {
    async function loadFilters() {
      try {
        const agts = await getAgentsList();
        setAgents(Array.isArray(agts) ? agts : []);
      } catch (e) {
        console.error("Failed to load filters:", e);
      }
    }
    loadFilters();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (search.trim()) {
        const res = await searchMemories(search, {
          user_id: "seiji",
          limit: 100,
          ...(selectedAgent ? { agent_id: selectedAgent } : {}),
        });
        const mems = res.memories || res.results || res;
        setMemories(Array.isArray(mems) ? mems : []);
      } else {
        const params: Record<string, string> = { user_id: "seiji", limit: "500" };
        if (selectedAgent) params.agent_id = selectedAgent;
        if (selectedScope) params.scope = selectedScope;
        if (selectedConflictStatus) params.conflict_status = selectedConflictStatus;
        const mems = await getMemories(params);
        if (Array.isArray(mems)) {
          mems.sort((a: Memory, b: Memory) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
          setMemories(mems);
        }
      }
    } catch (e) {
      console.error(e);
      toast.error("Failed to load memories");
    } finally {
      setLoading(false);
    }
  }, [search, selectedAgent, selectedScope, selectedConflictStatus]);

  useEffect(() => { load(); }, [load]);

  const filtered = (activeTab === "Overview"
    ? memories
    : memories.filter((m) => m.memory_type === activeTab)
  ).filter((m) => selectedImportance === "" || m.importance === Number(selectedImportance));

  const handleDelete = async (id: string) => {
    try {
      await deleteMemory(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
      toast.success("Memory deleted");
    } catch {
      toast.error("Delete failed");
    }
  };

  const loadHistory = async (memId: string) => {
    setHistoryLoading(true);
    setHistoryOpen(true);
    try {
      const res = await getMemoryHistory(memId);
      setHistoryEvents(Array.isArray(res) ? res : res.events || []);
    } catch {
      toast.error("Failed to load history");
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadConflicts = async (memId: string) => {
    setConflictsLoading(true);
    setConflictsOpen(true);
    try {
      const res = await getMemoryConflicts(memId);
      setConflicts(Array.isArray(res) ? res : res.conflicts || []);
    } catch {
      toast.error("Failed to load conflicts");
    } finally {
      setConflictsLoading(false);
    }
  };

  const activeFilters = (selectedAgent ? 1 : 0) + (selectedScope ? 1 : 0) + (selectedConflictStatus ? 1 : 0) + (selectedImportance ? 1 : 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Memories</h1>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="gap-1.5 text-xs h-8" onClick={load}>
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
        </div>
      </div>

      {/* Filters Row */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Agent Filter */}
        <div className="relative">
          <select
            value={selectedAgent}
            onChange={(e) => setSelectedAgent(e.target.value)}
            className="h-8 px-3 pr-8 text-xs rounded-md border border-border bg-card text-foreground appearance-none cursor-pointer focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="">All Agents</option>
            {agents.map((a) => (
              <option key={a.agent_id || "none"} value={a.agent_id || ""}>
                {a.agent_id || "unassigned"} ({a.count})
              </option>
            ))}
          </select>
          <svg className="absolute right-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
        </div>

        {/* Scope Filter */}
        <div className="relative">
          <select
            value={selectedScope}
            onChange={(e) => setSelectedScope(e.target.value)}
            className="h-8 px-3 pr-8 text-xs rounded-md border border-border bg-card text-foreground appearance-none cursor-pointer focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="">All Scopes</option>
            {SCOPES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <svg className="absolute right-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
        </div>

        {/* Conflict Status Filter */}
        <div className="relative">
          <select
            value={selectedConflictStatus}
            onChange={(e) => setSelectedConflictStatus(e.target.value)}
            className="h-8 px-3 pr-8 text-xs rounded-md border border-border bg-card text-foreground appearance-none cursor-pointer focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="">All Status</option>
            {CONFLICT_STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <svg className="absolute right-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
        </div>

        {/* Importance Filter */}
        <div className="relative">
          <select
            value={selectedImportance}
            onChange={(e) => setSelectedImportance(e.target.value)}
            className="h-8 px-3 pr-8 text-xs rounded-md border border-border bg-card text-foreground appearance-none cursor-pointer focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="">All Importance</option>
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <option key={i} value={i}>{i} — {IMPORTANCE_LABELS[i]?.label}</option>
            ))}
          </select>
          <svg className="absolute right-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
        </div>

        {/* Active filter badges */}
        {activeFilters > 0 && (
          <div className="flex items-center gap-1.5">
            {selectedAgent && (
              <Badge variant="secondary" className="text-[11px] gap-1 pr-1">
                agent: {selectedAgent}
                <button onClick={() => setSelectedAgent("")} className="ml-0.5 hover:text-foreground"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {selectedScope && (
              <Badge variant="secondary" className="text-[11px] gap-1 pr-1">
                scope: {selectedScope}
                <button onClick={() => setSelectedScope("")} className="ml-0.5 hover:text-foreground"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {selectedConflictStatus && (
              <Badge variant="secondary" className="text-[11px] gap-1 pr-1">
                status: {selectedConflictStatus}
                <button onClick={() => setSelectedConflictStatus("")} className="ml-0.5 hover:text-foreground"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {selectedImportance && (
              <Badge variant="secondary" className="text-[11px] gap-1 pr-1">
                importance: {selectedImportance}
                <button onClick={() => setSelectedImportance("")} className="ml-0.5 hover:text-foreground"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            <button
              onClick={() => { setSelectedAgent(""); setSelectedScope(""); setSelectedConflictStatus(""); setSelectedImportance(""); }}
              className="text-[11px] text-muted-foreground hover:text-foreground ml-1"
            >
              Clear all
            </button>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-border pb-0">
        {TYPES.map((t) => (
          <button
            key={t}
            onClick={() => setActiveTab(t)}
            className={`px-3 py-2 text-sm transition-colors border-b-2 -mb-px ${
              activeTab === t
                ? "border-foreground text-foreground font-medium"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t}
            {t !== "Overview" && (
              <span className="ml-1.5 text-xs text-muted-foreground">
                {memories.filter((m) => m.memory_type === t).length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Search */}
      <form onSubmit={(e) => { e.preventDefault(); load(); }} className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search memories..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-10 h-9"
        />
      </form>

      {/* Results count */}
      <div className="text-xs text-muted-foreground">
        {filtered.length} memories{activeFilters > 0 ? " (filtered)" : ""}
      </div>

      {/* Table */}
      <div className="border border-border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="w-28 text-xs font-medium">Time</TableHead>
              <TableHead className="w-24 text-xs font-medium">Agent</TableHead>
              <TableHead className="text-xs font-medium">Memory Content</TableHead>
              <TableHead className="w-20 text-xs font-medium">Scope</TableHead>
              <TableHead className="w-24 text-xs font-medium">Type</TableHead>
              <TableHead className="w-24 text-xs font-medium">Importance</TableHead>
              <TableHead className="w-16 text-xs font-medium text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-12 text-muted-foreground">Loading...</TableCell>
              </TableRow>
            ) : filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-12 text-muted-foreground">No memories found</TableCell>
              </TableRow>
            ) : (
              filtered.map((mem) => (
                <TableRow
                  key={mem.id}
                  className="group cursor-pointer hover:bg-muted/40"
                  onClick={() => setDetailMem(mem)}
                >
                  <TableCell className="text-sm text-muted-foreground">{timeAgo(mem.created_at)}</TableCell>
                  <TableCell>
                    <span className="text-sm">{mem.agent_id || "—"}</span>
                  </TableCell>
                  <TableCell className="max-w-lg">
                    <p className="text-sm truncate">{mem.content}</p>
                  </TableCell>
                  <TableCell>
                    {mem.scope ? (
                      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${SCOPE_COLORS[mem.scope] || "bg-zinc-500/20 text-zinc-400"}`}>
                        {mem.scope}
                      </span>
                    ) : <span className="text-xs text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="text-[11px] font-normal">{mem.memory_type}</Badge>
                  </TableCell>
                  <TableCell>
                    {mem.importance != null ? (
                      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${IMPORTANCE_LABELS[mem.importance]?.color || "bg-zinc-500/20 text-zinc-400"}`}>
                        {mem.importance} — {IMPORTANCE_LABELS[mem.importance]?.label || "?"}
                      </span>
                    ) : <span className="text-xs text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 opacity-0 group-hover:opacity-100"
                      onClick={(e) => { e.stopPropagation(); handleDelete(mem.id); }}
                    >
                      <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Detail Dialog */}
      <Dialog open={!!detailMem} onOpenChange={() => setDetailMem(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Memory Details</DialogTitle></DialogHeader>
          {detailMem && (
            <div className="space-y-4">
              <p className="text-sm leading-relaxed">{detailMem.content}</p>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><p className="text-xs text-muted-foreground">Type</p><Badge variant="secondary">{detailMem.memory_type}</Badge></div>
                <div><p className="text-xs text-muted-foreground">Agent</p><p>{detailMem.agent_id || "—"}</p></div>
                <div><p className="text-xs text-muted-foreground">Pool</p><p>{detailMem.pool_id || "private"}</p></div>
                <div>
                  <p className="text-xs text-muted-foreground">Scope</p>
                  {detailMem.scope ? (
                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${SCOPE_COLORS[detailMem.scope] || "bg-zinc-500/20 text-zinc-400"}`}>
                      {detailMem.scope}
                    </span>
                  ) : <p>—</p>}
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Importance</p>
                  {detailMem.importance != null ? (
                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${IMPORTANCE_LABELS[detailMem.importance]?.color || ""}`}>
                      {detailMem.importance}/5 — {IMPORTANCE_LABELS[detailMem.importance]?.label}
                    </span>
                  ) : <p>—</p>}
                </div>
                <div><p className="text-xs text-muted-foreground">Decay Score</p><p>{detailMem.decay_score?.toFixed(3) ?? "—"}</p></div>
                <div><p className="text-xs text-muted-foreground">Access Count</p><p>{detailMem.access_count ?? 0}</p></div>
                <div><p className="text-xs text-muted-foreground">Version</p><p>{detailMem.version ?? 1}</p></div>
                <div><p className="text-xs text-muted-foreground">Source Type</p><p>{detailMem.source_type || "—"}</p></div>
                <div>
                  <p className="text-xs text-muted-foreground">Conflict Status</p>
                  {detailMem.conflict_status && detailMem.conflict_status !== "active" ? (
                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${CONFLICT_COLORS[detailMem.conflict_status] || "bg-zinc-500/20 text-zinc-400"}`}>
                      {detailMem.conflict_status}
                    </span>
                  ) : <p>active</p>}
                </div>
                <div><p className="text-xs text-muted-foreground">Created</p><p>{new Date(detailMem.created_at + "Z").toLocaleString()}</p></div>
                <div><p className="text-xs text-muted-foreground">ID</p><p className="font-mono text-xs truncate">{detailMem.id}</p></div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2 pt-2 border-t border-border">
                <Button variant="outline" size="sm" className="gap-1.5 text-xs" onClick={() => loadHistory(detailMem.id)}>
                  <History className="h-3.5 w-3.5" /> History
                </Button>
                {(detailMem.supersedes_id || detailMem.conflict_status === "superseded" || detailMem.conflict_status === "disputed") && (
                  <Button variant="outline" size="sm" className="gap-1.5 text-xs" onClick={() => loadConflicts(detailMem.id)}>
                    <AlertTriangle className="h-3.5 w-3.5" /> Conflicts
                  </Button>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* History Dialog */}
      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="max-w-xl max-h-[70vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Memory History</DialogTitle></DialogHeader>
          {historyLoading ? (
            <p className="text-sm text-muted-foreground py-4">Loading history...</p>
          ) : historyEvents.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">No history events found</p>
          ) : (
            <div className="space-y-3">
              {historyEvents.map((ev) => (
                <div key={ev.id} className="flex items-start gap-3 border border-border rounded-md p-3">
                  <Badge variant="secondary" className="text-[11px] shrink-0">{ev.event_type}</Badge>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm">{ev.details || "—"}</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {ev.actor_id && <span>by {ev.actor_id} · </span>}
                      {new Date(ev.timestamp + "Z").toLocaleString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Conflicts Dialog */}
      <Dialog open={conflictsOpen} onOpenChange={setConflictsOpen}>
        <DialogContent className="max-w-xl max-h-[70vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Memory Conflicts</DialogTitle></DialogHeader>
          {conflictsLoading ? (
            <p className="text-sm text-muted-foreground py-4">Loading conflicts...</p>
          ) : conflicts.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">No conflicts found</p>
          ) : (
            <div className="space-y-3">
              {conflicts.map((c) => (
                <div key={c.id} className="border border-border rounded-md p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <Badge variant="secondary" className="text-[11px]">{c.conflict_type}</Badge>
                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${c.status === "resolved" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"}`}>
                      {c.status}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Conflicting: <span className="font-mono">{c.conflicting_memory_id}</span>
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">{new Date(c.created_at + "Z").toLocaleString()}</p>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

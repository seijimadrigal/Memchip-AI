"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Brain, Users, Search, Activity, BarChart3, ArrowRight, Rss, Globe2, AlertTriangle } from "lucide-react";
import { getStats, getActivity, getAnalytics, getEvents, getMemories } from "@/lib/api";
import { useRouter } from "next/navigation";

interface ActivityEntry {
  timestamp: string;
  type: string;
  path: string;
  status: number;
  latency_ms: number;
}

interface DecayDist {
  healthy: number;
  aging: number;
  critical: number;
}

interface EventEntry {
  id: string;
  event_type: string;
  actor: string;
  content: string;
  created_at: string;
  memory_id?: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [decay, setDecay] = useState<DecayDist | null>(null);
  const [dedupStats, setDedupStats] = useState<{ duplicates_found?: number; duplicates_merged?: number } | null>(null);
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [scopeCounts, setScopeCounts] = useState<Record<string, number>>({});
  const [conflictCounts, setConflictCounts] = useState<Record<string, number>>({});
  const [timeRange, setTimeRange] = useState("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [s, a, an, ev, mems] = await Promise.all([
          getStats(),
          getActivity({ limit: "50" }),
          getAnalytics().catch(() => null),
          getEvents({ limit: "5" }).catch(() => ({ events: [] })),
          getMemories({ user_id: "seiji", limit: "500" }).catch(() => []),
        ]);
        setStats(s);
        setActivity(a.entries || []);
        if (an) {
          setDecay(an.decay_distribution || null);
          setDedupStats(an.dedup_stats || null);
        }
        setEvents(ev.events || []);

        // Count scopes and conflicts from memories
        const memList = Array.isArray(mems) ? mems : [];
        const sc: Record<string, number> = {};
        const cc: Record<string, number> = {};
        for (const m of memList) {
          const scope = (m as Record<string, unknown>).scope as string || "private";
          sc[scope] = (sc[scope] || 0) + 1;
          const conflict = (m as Record<string, unknown>).conflict_status as string || "active";
          cc[conflict] = (cc[conflict] || 0) + 1;
        }
        setScopeCounts(sc);
        setConflictCounts(cc);
      } catch (e) {
        console.error("Failed to load:", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const totalMems = (stats?.total_memories as number) || 0;
  const addEvents = (stats?.add_events as number) || 0;
  const searchEvents = (stats?.search_events as number) || 0;
  const totalRequests = (stats?.total_requests as number) || 0;
  const byAgent = (stats?.by_agent as Record<string, number>) || {};
  const byType = (stats?.by_type as Record<string, number>) || {};

  const statCards = [
    { label: "Total Memories", value: totalMems, icon: Brain, color: "text-foreground" },
    { label: "Search Events", value: searchEvents, icon: Search, color: "text-foreground" },
    { label: "Add Events", value: addEvents, icon: Activity, color: "text-foreground" },
    { label: "Total Requests", value: totalRequests, icon: BarChart3, color: "text-foreground" },
  ];

  const ranges = ["All Time", "1d", "7d", "30d"];

  const eventTypeColor: Record<string, string> = {
    created: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    updated: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    superseded: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    archived: "bg-red-500/20 text-red-400 border-red-500/30",
  };

  const scopeColors: Record<string, string> = {
    private: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
    task: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    project: "bg-purple-500/20 text-purple-400 border-purple-500/30",
    team: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    global: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  };

  function timeAgo(ts: string): string {
    const diff = Date.now() - new Date(ts).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  }

  const totalConflicts = (conflictCounts["superseded"] || 0) + (conflictCounts["disputed"] || 0);
  const totalScoped = Object.values(scopeCounts).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-8">
      {/* Date Range Picker */}
      <div className="flex items-center justify-end gap-1">
        {ranges.map((r) => (
          <Button
            key={r}
            variant={timeRange === r ? "secondary" : "ghost"}
            size="sm"
            className="text-xs h-7 px-3"
            onClick={() => setTimeRange(r)}
          >
            {r}
          </Button>
        ))}
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((s) => (
          <div key={s.label} className="border border-border rounded-lg p-5 bg-card">
            <div className="flex items-center gap-2 mb-3">
              <s.icon className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">{s.label}</span>
            </div>
            <div className="text-3xl font-semibold tracking-tight">
              {loading ? "—" : s.value.toLocaleString()}
            </div>
          </div>
        ))}
      </div>

      {/* Decay Distribution */}
      {decay && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[
            { label: "Healthy", value: decay.healthy, color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
            { label: "Aging", value: decay.aging, color: "text-yellow-400", bg: "bg-yellow-500/10 border-yellow-500/20" },
            { label: "Critical", value: decay.critical, color: "text-red-400", bg: "bg-red-500/10 border-red-500/20" },
          ].map((d) => (
            <div key={d.label} className={`border rounded-lg p-5 ${d.bg}`}>
              <p className={`text-sm ${d.color}`}>{d.label}</p>
              <p className="text-3xl font-semibold mt-1">{d.value.toLocaleString()}</p>
              <p className="text-xs text-muted-foreground mt-1">memories</p>
            </div>
          ))}
        </div>
      )}

      {/* Dedup Stats */}
      {dedupStats && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="border border-border rounded-lg p-5 bg-card">
            <p className="text-sm text-muted-foreground">Duplicates Found</p>
            <p className="text-3xl font-semibold mt-1">{dedupStats.duplicates_found?.toLocaleString() || 0}</p>
          </div>
          <div className="border border-border rounded-lg p-5 bg-card">
            <p className="text-sm text-muted-foreground">Duplicates Merged</p>
            <p className="text-3xl font-semibold mt-1">{dedupStats.duplicates_merged?.toLocaleString() || 0}</p>
          </div>
        </div>
      )}

      {/* Two-column charts area */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Requests Card */}
        <div className="border border-border rounded-lg p-5 bg-card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-base font-semibold">Requests</h3>
              <p className="text-2xl font-semibold mt-1">{totalRequests.toLocaleString()}</p>
            </div>
            <Button variant="outline" size="sm" onClick={() => router.push("/activity")} className="gap-1">
              View Requests <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </div>
          <div className="h-32 flex items-end gap-1">
            {activity.slice(0, 30).map((a, i) => (
              <div
                key={i}
                className={`flex-1 min-w-[4px] rounded-t ${a.type === "ADD" ? "bg-emerald-500/60" : a.type === "SEARCH" ? "bg-purple-500/60" : "bg-muted"}`}
                style={{ height: `${Math.min(100, Math.max(8, (a.latency_ms / 1000) * 10))}%` }}
              />
            ))}
            {activity.length === 0 && (
              <div className="flex-1 flex items-center justify-center text-xs text-muted-foreground">
                No requests yet
              </div>
            )}
          </div>
          <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" /> ADD</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-purple-500 inline-block" /> SEARCH</span>
          </div>
        </div>

        {/* Agents Card */}
        <div className="border border-border rounded-lg p-5 bg-card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-base font-semibold">Agents</h3>
              <p className="text-2xl font-semibold mt-1">{Object.keys(byAgent).length}</p>
            </div>
            <Button variant="outline" size="sm" onClick={() => router.push("/agents")} className="gap-1">
              View Agents <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </div>
          <div className="space-y-3">
            {Object.entries(byAgent).map(([agent, count]) => (
              <div key={agent} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Users className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-sm">{agent}</span>
                </div>
                <span className="text-sm text-muted-foreground">{count} memories</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Memory Types Breakdown */}
      <div className="border border-border rounded-lg p-5 bg-card">
        <h3 className="text-base font-semibold mb-4">Memory Types</h3>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {Object.entries(byType).map(([type, count]) => (
            <div key={type} className="text-center p-3 rounded-lg bg-muted/50">
              <p className="text-lg font-semibold">{(count as number).toLocaleString()}</p>
              <p className="text-xs text-muted-foreground mt-1">{type}</p>
            </div>
          ))}
        </div>
      </div>

      {/* v0.3.0: Event Stream, Scope Distribution, Conflict Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Event Stream */}
        <div className="lg:col-span-2 border border-border rounded-lg p-5 bg-card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Rss className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-base font-semibold">Event Stream</h3>
            </div>
            <Button variant="outline" size="sm" onClick={() => router.push("/events")} className="gap-1">
              View All <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </div>
          {events.length === 0 ? (
            <p className="text-sm text-muted-foreground">No events yet</p>
          ) : (
            <div className="space-y-3">
              {events.map((ev) => (
                <div key={ev.id} className="flex items-start gap-3 p-2 rounded-lg bg-muted/30">
                  <Badge variant="outline" className={`text-[10px] shrink-0 mt-0.5 ${eventTypeColor[ev.event_type] || "bg-muted text-muted-foreground"}`}>
                    {ev.event_type}
                  </Badge>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm truncate">{ev.content}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-muted-foreground">{ev.actor}</span>
                      <span className="text-xs text-muted-foreground">·</span>
                      <span className="text-xs text-muted-foreground">{timeAgo(ev.created_at)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Scope Distribution + Conflict Summary stacked */}
        <div className="space-y-4">
          {/* Scope Distribution */}
          <div className="border border-border rounded-lg p-5 bg-card">
            <div className="flex items-center gap-2 mb-4">
              <Globe2 className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-base font-semibold">Scope Distribution</h3>
            </div>
            {totalScoped === 0 ? (
              <p className="text-sm text-muted-foreground">No scope data</p>
            ) : (
              <div className="space-y-2">
                {["private", "task", "project", "team", "global"].map((scope) => {
                  const count = scopeCounts[scope] || 0;
                  if (count === 0) return null;
                  const pct = Math.round((count / totalScoped) * 100);
                  return (
                    <div key={scope}>
                      <div className="flex items-center justify-between mb-1">
                        <Badge variant="outline" className={`text-[10px] ${scopeColors[scope]}`}>{scope}</Badge>
                        <span className="text-xs text-muted-foreground">{count} ({pct}%)</span>
                      </div>
                      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${scope === "private" ? "bg-zinc-500" : scope === "task" ? "bg-blue-500" : scope === "project" ? "bg-purple-500" : scope === "team" ? "bg-emerald-500" : "bg-orange-500"}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Conflict Summary */}
          <div className={`border rounded-lg p-5 bg-card ${totalConflicts > 0 ? "border-red-500/30" : "border-border"}`}>
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle className={`h-4 w-4 ${totalConflicts > 0 ? "text-red-400" : "text-muted-foreground"}`} />
              <h3 className="text-base font-semibold">Conflicts</h3>
              {totalConflicts > 0 && (
                <Badge variant="outline" className="text-[10px] bg-red-500/20 text-red-400 border-red-500/30">
                  {totalConflicts}
                </Badge>
              )}
            </div>
            {totalConflicts === 0 ? (
              <p className="text-sm text-muted-foreground">No conflicts detected</p>
            ) : (
              <div className="space-y-2">
                {conflictCounts["superseded"] ? (
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="text-[10px] bg-yellow-500/20 text-yellow-400 border-yellow-500/30">superseded</Badge>
                    <span className="text-sm font-medium">{conflictCounts["superseded"]}</span>
                  </div>
                ) : null}
                {conflictCounts["disputed"] ? (
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="text-[10px] bg-red-500/20 text-red-400 border-red-500/30">disputed</Badge>
                    <span className="text-sm font-medium">{conflictCounts["disputed"]}</span>
                  </div>
                ) : null}
                {conflictCounts["stale"] ? (
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="text-[10px] bg-zinc-500/20 text-zinc-400 border-zinc-500/30">stale</Badge>
                    <span className="text-sm font-medium">{conflictCounts["stale"]}</span>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Users, AlertTriangle, Rss, Globe2, FileCode2 } from "lucide-react";
import { getAnalytics, getMemories, getEvents } from "@/lib/api";

interface Analytics {
  growth?: { date: string; count: number }[];
  by_agent?: Record<string, number>;
  by_type?: Record<string, number>;
  decay_distribution?: { healthy: number; aging: number; critical: number };
}

export default function AnalyticsPage() {
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [scopeCounts, setScopeCounts] = useState<Record<string, number>>({});
  const [conflictCounts, setConflictCounts] = useState<Record<string, number>>({});
  const [sourceCounts, setSourceCounts] = useState<Record<string, number>>({});
  const [eventTypeCounts, setEventTypeCounts] = useState<Record<string, number>>({});

  useEffect(() => {
    async function load() {
      try {
        const [an, mems, ev] = await Promise.all([
          getAnalytics(),
          getMemories({ user_id: "seiji", limit: "500" }).catch(() => []),
          getEvents({ limit: "200" }).catch(() => ({ events: [] })),
        ]);
        setData(an);

        const memList = Array.isArray(mems) ? mems : [];
        const sc: Record<string, number> = {};
        const cc: Record<string, number> = {};
        const src: Record<string, number> = {};
        for (const m of memList) {
          const mem = m as Record<string, unknown>;
          const scope = (mem.scope as string) || "private";
          sc[scope] = (sc[scope] || 0) + 1;
          const conflict = (mem.conflict_status as string) || "active";
          cc[conflict] = (cc[conflict] || 0) + 1;
          const sourceType = (mem.source_type as string) || "unknown";
          src[sourceType] = (src[sourceType] || 0) + 1;
        }
        setScopeCounts(sc);
        setConflictCounts(cc);
        setSourceCounts(src);

        const evList = (ev.events || []) as { event_type: string }[];
        const ec: Record<string, number> = {};
        for (const e of evList) {
          ec[e.event_type] = (ec[e.event_type] || 0) + 1;
        }
        setEventTypeCounts(ec);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const growth = data?.growth || [];
  const maxCount = Math.max(1, ...growth.map((g) => g.count));
  const byAgent = data?.by_agent || {};
  const byType = data?.by_type || {};
  const decay = data?.decay_distribution || { healthy: 0, aging: 0, critical: 0 };

  const scopeColors: Record<string, { bar: string; badge: string }> = {
    private: { bar: "bg-zinc-500", badge: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30" },
    task: { bar: "bg-blue-500", badge: "bg-blue-500/20 text-blue-400 border-blue-500/30" },
    project: { bar: "bg-purple-500", badge: "bg-purple-500/20 text-purple-400 border-purple-500/30" },
    team: { bar: "bg-emerald-500", badge: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
    global: { bar: "bg-orange-500", badge: "bg-orange-500/20 text-orange-400 border-orange-500/30" },
  };

  const eventColors: Record<string, string> = {
    created: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    updated: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    superseded: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    archived: "bg-red-500/20 text-red-400 border-red-500/30",
  };

  const totalScoped = Object.values(scopeCounts).reduce((a, b) => a + b, 0);
  const totalConflicts = (conflictCounts["superseded"] || 0) + (conflictCounts["disputed"] || 0);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
        <p className="text-muted-foreground">Memory usage insights and trends</p>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading analytics...</p>
      ) : (
        <>
          {/* Growth Chart */}
          <div className="border border-border rounded-lg p-5 bg-card">
            <h3 className="text-base font-semibold mb-4">Memory Growth (30 days)</h3>
            <div className="h-40 flex items-end gap-1">
              {growth.length === 0 ? (
                <div className="flex-1 flex items-center justify-center text-xs text-muted-foreground">No data</div>
              ) : (
                growth.map((g, i) => (
                  <div key={i} className="flex-1 flex flex-col items-center gap-1">
                    <div
                      className="w-full min-w-[6px] rounded-t bg-purple-500/70"
                      style={{ height: `${Math.max(4, (g.count / maxCount) * 100)}%` }}
                      title={`${g.date}: ${g.count}`}
                    />
                  </div>
                ))
              )}
            </div>
            {growth.length > 0 && (
              <div className="flex justify-between mt-2 text-[10px] text-muted-foreground">
                <span>{growth[0]?.date}</span>
                <span>{growth[growth.length - 1]?.date}</span>
              </div>
            )}
          </div>

          {/* Decay Distribution */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { label: "Healthy", value: decay.healthy, color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
              { label: "Aging", value: decay.aging, color: "text-yellow-400", bg: "bg-yellow-500/10 border-yellow-500/20" },
              { label: "Critical", value: decay.critical, color: "text-red-400", bg: "bg-red-500/10 border-red-500/20" },
            ].map((d) => (
              <div key={d.label} className={`border rounded-lg p-5 ${d.bg}`}>
                <p className={`text-sm ${d.color}`}>{d.label}</p>
                <p className="text-3xl font-semibold mt-1">{d.value.toLocaleString()}</p>
              </div>
            ))}
          </div>

          {/* v0.3.0: Scope Distribution + Conflict Overview */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Scope Distribution */}
            <div className="border border-border rounded-lg p-5 bg-card">
              <div className="flex items-center gap-2 mb-4">
                <Globe2 className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-base font-semibold">Scope Distribution</h3>
              </div>
              {totalScoped === 0 ? (
                <p className="text-sm text-muted-foreground">No scope data</p>
              ) : (
                <div className="space-y-3">
                  {["private", "task", "project", "team", "global"].map((scope) => {
                    const count = scopeCounts[scope] || 0;
                    if (count === 0) return null;
                    const pct = Math.round((count / totalScoped) * 100);
                    const colors = scopeColors[scope] || scopeColors["private"];
                    return (
                      <div key={scope}>
                        <div className="flex items-center justify-between mb-1">
                          <Badge variant="outline" className={`text-[10px] ${colors.badge}`}>{scope}</Badge>
                          <span className="text-xs text-muted-foreground">{count} ({pct}%)</span>
                        </div>
                        <div className="h-2 bg-muted rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${colors.bar}`} style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Conflict Overview */}
            <div className={`border rounded-lg p-5 bg-card ${totalConflicts > 0 ? "border-red-500/30" : "border-border"}`}>
              <div className="flex items-center gap-2 mb-4">
                <AlertTriangle className={`h-4 w-4 ${totalConflicts > 0 ? "text-red-400" : "text-muted-foreground"}`} />
                <h3 className="text-base font-semibold">Conflict Overview</h3>
                {totalConflicts > 0 && (
                  <Badge variant="outline" className="text-[10px] bg-red-500/20 text-red-400 border-red-500/30">
                    {totalConflicts} conflicts
                  </Badge>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                {["active", "superseded", "disputed", "stale"].map((status) => {
                  const count = conflictCounts[status] || 0;
                  const isConflict = status === "superseded" || status === "disputed";
                  return (
                    <div key={status} className={`p-3 rounded-lg ${isConflict && count > 0 ? "bg-red-500/10" : "bg-muted/50"}`}>
                      <p className="text-lg font-semibold">{count}</p>
                      <p className="text-xs text-muted-foreground">{status}</p>
                    </div>
                  );
                })}
              </div>
              {totalConflicts > 0 && (
                <p className="text-xs text-red-400 mt-3">⚠ {totalConflicts} memories need conflict resolution</p>
              )}
            </div>
          </div>

          {/* v0.3.0: Event Activity + Source Type */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Event Activity */}
            <div className="border border-border rounded-lg p-5 bg-card">
              <div className="flex items-center gap-2 mb-4">
                <Rss className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-base font-semibold">Event Activity</h3>
              </div>
              {Object.keys(eventTypeCounts).length === 0 ? (
                <p className="text-sm text-muted-foreground">No events</p>
              ) : (
                <div className="space-y-3">
                  {Object.entries(eventTypeCounts)
                    .sort(([, a], [, b]) => b - a)
                    .map(([type, count]) => (
                      <div key={type} className="flex items-center justify-between">
                        <Badge variant="outline" className={`text-[10px] ${eventColors[type] || "bg-muted text-muted-foreground"}`}>
                          {type}
                        </Badge>
                        <span className="text-sm font-medium">{count}</span>
                      </div>
                    ))}
                </div>
              )}
            </div>

            {/* Source Type Distribution */}
            <div className="border border-border rounded-lg p-5 bg-card">
              <div className="flex items-center gap-2 mb-4">
                <FileCode2 className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-base font-semibold">Source Types</h3>
              </div>
              {Object.keys(sourceCounts).length === 0 ? (
                <p className="text-sm text-muted-foreground">No source data</p>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(sourceCounts)
                    .sort(([, a], [, b]) => b - a)
                    .map(([type, count]) => (
                      <div key={type} className="text-center p-3 rounded-lg bg-muted/50">
                        <p className="text-lg font-semibold">{count}</p>
                        <p className="text-xs text-muted-foreground mt-1">{type}</p>
                      </div>
                    ))}
                </div>
              )}
            </div>
          </div>

          {/* Agent Activity */}
          <div className="border border-border rounded-lg p-5 bg-card">
            <h3 className="text-base font-semibold mb-4">Agent Activity</h3>
            <div className="space-y-3">
              {Object.entries(byAgent).length === 0 ? (
                <p className="text-sm text-muted-foreground">No agent data</p>
              ) : (
                Object.entries(byAgent).map(([agent, count]) => (
                  <div key={agent} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Users className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-sm">{agent}</span>
                    </div>
                    <span className="text-sm text-muted-foreground">{count} memories</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Memory Type Distribution */}
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
        </>
      )}
    </div>
  );
}

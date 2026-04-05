"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { RefreshCw, CheckCircle2, XCircle } from "lucide-react";
import { getActivity } from "@/lib/api";

interface Entry {
  timestamp: string;
  type: string;
  path: string;
  method: string;
  status: number;
  latency_ms: number;
}

function timeAgo(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diff = now - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

const TABS = ["Overview", "ADD", "SEARCH", "LIST", "DELETE"];

const typeBadgeColors: Record<string, string> = {
  ADD: "bg-emerald-500/15 text-emerald-400 border-emerald-500/20",
  SEARCH: "bg-purple-500/15 text-purple-400 border-purple-500/20",
  LIST: "bg-blue-500/15 text-blue-400 border-blue-500/20",
  DELETE: "bg-red-500/15 text-red-400 border-red-500/20",
  ANSWER: "bg-amber-500/15 text-amber-400 border-amber-500/20",
};

export default function ActivityPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("Overview");

  const load = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { limit: "500" };
      if (activeTab !== "Overview") params.type = activeTab;
      const res = await getActivity(params);
      setEntries(res.entries || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [activeTab]);

  // Simple bar chart data
  const barData = entries.slice(0, 50).reverse();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Requests</h1>
        <Button variant="outline" size="sm" className="gap-1.5 text-xs h-8" onClick={load}>
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-border pb-0">
        {TABS.map((t) => (
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
          </button>
        ))}
      </div>

      {/* Timeline bar chart */}
      <div className="border border-border rounded-lg p-5 bg-card">
        <div className="h-24 flex items-end gap-0.5">
          {barData.map((e, i) => (
            <div
              key={i}
              className={`flex-1 min-w-[3px] rounded-t transition-all ${
                e.type === "ADD" ? "bg-emerald-500/50" :
                e.type === "SEARCH" ? "bg-purple-500/50" :
                e.type === "LIST" ? "bg-blue-500/30" : "bg-muted"
              }`}
              style={{ height: `${Math.min(100, Math.max(5, (e.latency_ms / 5000) * 100))}%` }}
              title={`${e.type} — ${formatLatency(e.latency_ms)}`}
            />
          ))}
          {barData.length === 0 && (
            <div className="flex-1 flex items-center justify-center text-xs text-muted-foreground">
              No activity yet
            </div>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="border border-border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="w-28 text-xs font-medium">Time</TableHead>
              <TableHead className="w-24 text-xs font-medium">Type</TableHead>
              <TableHead className="text-xs font-medium">Path</TableHead>
              <TableHead className="w-28 text-xs font-medium">Latency</TableHead>
              <TableHead className="w-20 text-xs font-medium text-center">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={5} className="text-center py-12 text-muted-foreground">Loading...</TableCell></TableRow>
            ) : entries.length === 0 ? (
              <TableRow><TableCell colSpan={5} className="text-center py-12 text-muted-foreground">No requests recorded</TableCell></TableRow>
            ) : (
              entries.map((e, i) => (
                <TableRow key={i}>
                  <TableCell className="text-sm text-muted-foreground">{timeAgo(e.timestamp)}</TableCell>
                  <TableCell>
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border ${typeBadgeColors[e.type] || "bg-muted text-muted-foreground"}`}>
                      {e.type}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm font-mono text-muted-foreground">{e.path}</TableCell>
                  <TableCell className="text-sm">{formatLatency(e.latency_ms)}</TableCell>
                  <TableCell className="text-center">
                    {e.status < 400 ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-500 mx-auto" />
                    ) : (
                      <XCircle className="h-4 w-4 text-red-500 mx-auto" />
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

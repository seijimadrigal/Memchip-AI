"use client";

import { useEffect, useState, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { RefreshCw, Radio } from "lucide-react";
import { getEvents } from "@/lib/api";

interface EventEntry {
  id: string;
  event_type: string;
  memory_id: string;
  actor_id: string | null;
  actor_type: string | null;
  source: string | null;
  new_content: string | null;
  created_at: string;
}

const TYPE_COLORS: Record<string, string> = {
  created: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  updated: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  superseded: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  archived: "bg-red-500/20 text-red-400 border-red-500/30",
  accessed: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
  disputed: "bg-orange-500/20 text-orange-400 border-orange-500/30",
};

export default function EventsPage() {
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [typeFilter, setTypeFilter] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);

  const load = useCallback(async () => {
    try {
      const params: Record<string, string> = { limit: "50" };
      if (typeFilter) params.event_type = typeFilter;
      const res = await getEvents(params);
      setEvents(res.events || res.entries || []);
      setTotal(res.total || 0);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [typeFilter]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, [autoRefresh, load]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Radio className="h-5 w-5 text-emerald-400" /> Event Stream
          </h1>
          <p className="text-muted-foreground">{total} total events</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={autoRefresh ? "default" : "outline"}
            size="sm"
            className="text-xs h-8"
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            {autoRefresh ? "⏸ Pause" : "▶ Live"}
          </Button>
          <Button variant="outline" size="sm" className="gap-1.5 text-xs h-8" onClick={load}>
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="h-8 px-3 pr-8 text-xs rounded-md border border-border bg-card text-foreground appearance-none cursor-pointer"
        >
          <option value="">All events</option>
          <option value="created">Created</option>
          <option value="updated">Updated</option>
          <option value="superseded">Superseded</option>
          <option value="archived">Archived</option>
          <option value="accessed">Accessed</option>
        </select>
        {autoRefresh && (
          <span className="flex items-center gap-1.5 text-xs text-emerald-400">
            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            Live — refreshing every 10s
          </span>
        )}
      </div>

      <div className="border border-border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="w-40 text-xs font-medium">Time</TableHead>
              <TableHead className="w-28 text-xs font-medium">Event</TableHead>
              <TableHead className="w-24 text-xs font-medium">Actor</TableHead>
              <TableHead className="w-24 text-xs font-medium">Source</TableHead>
              <TableHead className="text-xs font-medium">Content</TableHead>
              <TableHead className="w-48 text-xs font-medium">Memory ID</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={6} className="text-center py-12 text-muted-foreground">Loading...</TableCell></TableRow>
            ) : events.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="text-center py-12 text-muted-foreground">No events yet</TableCell></TableRow>
            ) : (
              events.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="text-sm text-muted-foreground">{new Date(e.created_at).toLocaleString()}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`text-[11px] ${TYPE_COLORS[e.event_type] || ""}`}>
                      {e.event_type}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm">{e.actor_id || "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{e.source || "—"}</TableCell>
                  <TableCell className="text-sm truncate max-w-xs">{e.new_content?.slice(0, 80) || "—"}</TableCell>
                  <TableCell className="font-mono text-[11px] text-muted-foreground truncate">{e.memory_id?.slice(0, 12)}...</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

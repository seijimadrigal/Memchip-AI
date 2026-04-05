"use client";

import { useEffect, useState, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { getAudit } from "@/lib/api";

interface AuditEntry {
  id: string;
  org_id: string;
  memory_id: string;
  action: string;
  actor_id: string | null;
  actor_type: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

const ACTION_COLORS: Record<string, string> = {
  create: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  update: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  delete: "bg-red-500/20 text-red-400 border-red-500/30",
};

const ACTOR_TYPE_COLORS: Record<string, string> = {
  agent: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  user: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
  system: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
};

function renderDetails(details: Record<string, unknown> | null): string {
  if (!details || Object.keys(details).length === 0) return "—";
  return JSON.stringify(details);
}

export default function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionFilter, setActionFilter] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const perPage = 25;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {
        limit: String(perPage),
        offset: String((page - 1) * perPage),
      };
      if (actionFilter) params.action = actionFilter;
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;
      const res = await getAudit(params);
      setEntries(res.entries || res || []);
      setTotal(res.total || (res.entries || res || []).length);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [page, actionFilter, startDate, endDate]);

  useEffect(() => { load(); }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / perPage));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Audit Log</h1>
        <p className="text-muted-foreground">Track all memory operations</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={actionFilter}
          onChange={(e) => { setActionFilter(e.target.value); setPage(1); }}
          className="h-9 rounded-md border border-border bg-background px-3 text-sm"
        >
          <option value="">All actions</option>
          <option value="create">Create</option>
          <option value="update">Update</option>
          <option value="delete">Delete</option>
        </select>
        <Input
          type="date"
          placeholder="Start date"
          value={startDate}
          onChange={(e) => { setStartDate(e.target.value); setPage(1); }}
          className="h-9 w-40"
        />
        <Input
          type="date"
          placeholder="End date"
          value={endDate}
          onChange={(e) => { setEndDate(e.target.value); setPage(1); }}
          className="h-9 w-40"
        />
      </div>

      {/* Table */}
      <div className="border border-border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="w-40 text-xs font-medium">Time</TableHead>
              <TableHead className="w-24 text-xs font-medium">Action</TableHead>
              <TableHead className="w-48 text-xs font-medium">Memory ID</TableHead>
              <TableHead className="w-36 text-xs font-medium">Actor</TableHead>
              <TableHead className="text-xs font-medium">Details</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={5} className="text-center py-12 text-muted-foreground">Loading...</TableCell></TableRow>
            ) : entries.length === 0 ? (
              <TableRow><TableCell colSpan={5} className="text-center py-12 text-muted-foreground">No audit entries</TableCell></TableRow>
            ) : (
              entries.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="text-sm text-muted-foreground">{new Date(e.created_at).toLocaleString()}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`text-[11px] ${ACTION_COLORS[e.action] || ""}`}>
                      {e.action}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground truncate max-w-[12rem]">{e.memory_id}</TableCell>
                  <TableCell className="text-sm">
                    <span className="flex items-center gap-1.5">
                      {e.actor_type && (
                        <Badge variant="outline" className={`text-[10px] ${ACTOR_TYPE_COLORS[e.actor_type] || ""}`}>
                          {e.actor_type}
                        </Badge>
                      )}
                      <span className="truncate">{e.actor_id || "—"}</span>
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground truncate max-w-xs">{renderDetails(e.details)}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{total} total entries</p>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm text-muted-foreground">Page {page} of {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

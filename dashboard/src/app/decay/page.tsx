"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Timer, AlertTriangle, Archive, Info } from "lucide-react";
import { getDecayPreview, runDecayCleanup, getMemories } from "@/lib/api";
import { toast } from "sonner";

interface DecayMemory {
  id: string;
  content: string;
  memory_type: string;
  decay_score: number;
  access_count: number;
  last_accessed: string;
  created_at: string;
  status?: string;
  scope?: string;
}

function scoreColor(score: number): string {
  if (score < 0.3) return "text-red-400";
  if (score < 0.7) return "text-yellow-400";
  return "text-emerald-400";
}

function scoreBg(score: number): string {
  if (score < 0.3) return "bg-red-500/20 border-red-500/30";
  if (score < 0.7) return "bg-yellow-500/20 border-yellow-500/30";
  return "bg-emerald-500/20 border-emerald-500/30";
}

const scopeBadgeColor: Record<string, string> = {
  private: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
  task: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  project: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  team: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  global: "bg-orange-500/20 text-orange-400 border-orange-500/30",
};

export default function DecayPage() {
  const [memories, setMemories] = useState<DecayMemory[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCleanup, setShowCleanup] = useState(false);
  const [threshold, setThreshold] = useState("0.3");
  const [cleaning, setCleaning] = useState(false);
  const [archivedCount, setArchivedCount] = useState(0);

  const load = async () => {
    setLoading(true);
    try {
      const [res, mems] = await Promise.all([
        getDecayPreview(100),
        getMemories({ user_id: "seiji", limit: "500", status: "archived" }).catch(() => []),
      ]);
      setMemories(res.memories || res || []);
      const memList = Array.isArray(mems) ? mems : [];
      setArchivedCount(memList.length);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const atRisk = memories.filter((m) => m.decay_score < Number(threshold)).length;

  const handleCleanup = async () => {
    setCleaning(true);
    try {
      const res = await runDecayCleanup(Number(threshold));
      toast.success(`Cleanup complete: ${res.deleted_count || res.deleted || 0} memories archived`);
      setShowCleanup(false);
      load();
    } catch { toast.error("Cleanup failed"); } finally { setCleaning(false); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Memory Decay</h1>
          <p className="text-muted-foreground">Preview and manage decaying memories</p>
        </div>
        <Button size="sm" variant="destructive" className="gap-1.5" onClick={() => setShowCleanup(true)}>
          <Timer className="h-4 w-4" /> Run Cleanup
        </Button>
      </div>

      {/* Soft-delete notice */}
      <div className="flex items-start gap-2 p-3 rounded-lg bg-blue-500/10 border border-blue-500/20">
        <Info className="h-4 w-4 text-blue-400 mt-0.5 shrink-0" />
        <p className="text-sm text-blue-400">
          <span className="font-medium">v0.3.0:</span> Cleanup now <strong>soft-deletes</strong> (archives) memories instead of permanently removing them. Archived memories can be restored.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        {[
          { label: "Healthy (≥ 0.7)", count: memories.filter((m) => m.decay_score >= 0.7).length, color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
          { label: "Aging (0.3–0.7)", count: memories.filter((m) => m.decay_score >= 0.3 && m.decay_score < 0.7).length, color: "text-yellow-400", bg: "bg-yellow-500/10 border-yellow-500/20" },
          { label: "Critical (< 0.3)", count: memories.filter((m) => m.decay_score < 0.3).length, color: "text-red-400", bg: "bg-red-500/10 border-red-500/20" },
          { label: "Archived", count: archivedCount, color: "text-zinc-400", bg: "bg-zinc-500/10 border-zinc-500/20", icon: true },
        ].map((d) => (
          <div key={d.label} className={`border rounded-lg p-5 ${d.bg}`}>
            <div className="flex items-center gap-1.5">
              {d.icon && <Archive className="h-3.5 w-3.5 text-zinc-400" />}
              <p className={`text-sm ${d.color}`}>{d.label}</p>
            </div>
            <p className="text-3xl font-semibold mt-1">{d.count}</p>
          </div>
        ))}
      </div>

      {/* Decay Table */}
      <div className="border border-border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="text-xs font-medium">Content</TableHead>
              <TableHead className="w-24 text-xs font-medium">Type</TableHead>
              <TableHead className="w-20 text-xs font-medium">Scope</TableHead>
              <TableHead className="w-20 text-xs font-medium">Status</TableHead>
              <TableHead className="w-28 text-xs font-medium">Decay Score</TableHead>
              <TableHead className="w-24 text-xs font-medium">Accesses</TableHead>
              <TableHead className="w-36 text-xs font-medium">Last Accessed</TableHead>
              <TableHead className="w-36 text-xs font-medium">Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={8} className="text-center py-12 text-muted-foreground">Loading...</TableCell></TableRow>
            ) : memories.length === 0 ? (
              <TableRow><TableCell colSpan={8} className="text-center py-12 text-muted-foreground">No decay data</TableCell></TableRow>
            ) : (
              memories.map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="text-sm truncate max-w-xs">{m.content}</TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="text-[11px]">{m.memory_type}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`text-[10px] ${scopeBadgeColor[m.scope || "private"] || scopeBadgeColor["private"]}`}>
                      {m.scope || "private"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`text-[10px] ${m.status === "archived" ? "bg-zinc-500/20 text-zinc-400 border-zinc-500/30" : "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"}`}>
                      {m.status || "active"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`text-[11px] ${scoreBg(m.decay_score)} ${scoreColor(m.decay_score)}`}>
                      {m.decay_score.toFixed(3)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{m.access_count}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{m.last_accessed ? new Date(m.last_accessed).toLocaleDateString() : "—"}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{new Date(m.created_at).toLocaleDateString()}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Cleanup Dialog */}
      <Dialog open={showCleanup} onOpenChange={setShowCleanup}>
        <DialogContent>
          <DialogHeader><DialogTitle className="flex items-center gap-2"><AlertTriangle className="h-5 w-5 text-red-400" /> Run Decay Cleanup</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">Archive memories with a decay score below the threshold. Archived memories are soft-deleted and can be restored.</p>
            <div>
              <label className="text-sm font-medium">Threshold</label>
              <Input type="number" step="0.1" min="0" max="1" value={threshold} onChange={(e) => setThreshold(e.target.value)} className="mt-1" />
            </div>
            <div className="rounded-lg bg-yellow-500/10 border border-yellow-500/20 p-3">
              <p className="text-sm text-yellow-400 font-medium">{atRisk} memories will be archived</p>
              <p className="text-xs text-muted-foreground mt-1">Memories are soft-deleted and can be restored later</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCleanup(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleCleanup} disabled={cleaning}>
              {cleaning ? "Archiving..." : "Run Cleanup"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

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
import { Plus, Trash2 } from "lucide-react";
import { getInstructions, createInstruction, deleteInstruction } from "@/lib/api";
import { toast } from "sonner";

interface InstructionEntry {
  id: string;
  user_id: string;
  instruction: string;
  active: boolean;
  created_at: string;
}

export default function InstructionsPage() {
  const [instructions, setInstructions] = useState<InstructionEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [form, setForm] = useState({ user_id: "seiji", instruction: "" });

  const load = async () => {
    setLoading(true);
    try {
      const res = await getInstructions("seiji");
      setInstructions(res.instructions || res || []);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    try {
      await createInstruction({ user_id: form.user_id, instruction: form.instruction });
      toast.success("Instruction created");
      setShowCreate(false);
      setForm({ user_id: "seiji", instruction: "" });
      load();
    } catch { toast.error("Failed to create instruction"); }
  };

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await deleteInstruction(deleteId);
      toast.success("Instruction deleted");
      setDeleteId(null);
      load();
    } catch { toast.error("Failed to delete"); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Instructions</h1>
          <p className="text-muted-foreground">Custom processing instructions per user</p>
        </div>
        <Button size="sm" className="gap-1.5" onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4" /> New Instruction
        </Button>
      </div>

      <div className="border border-border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="w-28 text-xs font-medium">User</TableHead>
              <TableHead className="text-xs font-medium">Instruction</TableHead>
              <TableHead className="w-20 text-xs font-medium">Status</TableHead>
              <TableHead className="w-40 text-xs font-medium">Created</TableHead>
              <TableHead className="w-16 text-xs font-medium" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={5} className="text-center py-12 text-muted-foreground">Loading...</TableCell></TableRow>
            ) : instructions.length === 0 ? (
              <TableRow><TableCell colSpan={5} className="text-center py-12 text-muted-foreground">No instructions</TableCell></TableRow>
            ) : (
              instructions.map((ins) => (
                <TableRow key={ins.id} className="group">
                  <TableCell className="text-sm">{ins.user_id}</TableCell>
                  <TableCell className="text-sm truncate max-w-lg">{ins.instruction}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={ins.active !== false ? "text-emerald-400 border-emerald-500/30" : "text-muted-foreground"}>
                      {ins.active !== false ? "Active" : "Inactive"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{new Date(ins.created_at).toLocaleDateString()}</TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" className="h-7 w-7 opacity-0 group-hover:opacity-100" onClick={() => setDeleteId(ins.id)}>
                      <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader><DialogTitle>Create Instruction</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Input placeholder="User ID" value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} />
            <textarea
              placeholder="Instruction text..."
              value={form.instruction}
              onChange={(e) => setForm({ ...form, instruction: e.target.value })}
              rows={4}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={!form.user_id || !form.instruction}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Delete Instruction</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Are you sure? This cannot be undone.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteId(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

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
import { getSessions, createSession, deleteSession } from "@/lib/api";
import { toast } from "sonner";

interface Session {
  id: string;
  name: string;
  user_id: string;
  agent_id: string;
  expires_at: string;
  created_at: string;
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", user_id: "seiji", agent_id: "", expires_in_minutes: "" });

  const load = async () => {
    setLoading(true);
    try {
      const res = await getSessions("seiji");
      setSessions(res.sessions || res || []);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    try {
      await createSession({
        name: form.name,
        user_id: form.user_id,
        agent_id: form.agent_id || undefined,
        expires_in_minutes: form.expires_in_minutes ? Number(form.expires_in_minutes) : undefined,
      });
      toast.success("Session created");
      setShowCreate(false);
      setForm({ name: "", user_id: "seiji", agent_id: "", expires_in_minutes: "" });
      load();
    } catch { toast.error("Failed to create session"); }
  };

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await deleteSession(deleteId);
      toast.success("Session deleted");
      setDeleteId(null);
      load();
    } catch { toast.error("Failed to delete"); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Sessions</h1>
          <p className="text-muted-foreground">Manage active sessions</p>
        </div>
        <Button size="sm" className="gap-1.5" onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4" /> New Session
        </Button>
      </div>

      <div className="border border-border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="text-xs font-medium">Name</TableHead>
              <TableHead className="text-xs font-medium">User</TableHead>
              <TableHead className="text-xs font-medium">Agent</TableHead>
              <TableHead className="text-xs font-medium">Expires</TableHead>
              <TableHead className="text-xs font-medium">Created</TableHead>
              <TableHead className="w-16 text-xs font-medium" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={6} className="text-center py-12 text-muted-foreground">Loading...</TableCell></TableRow>
            ) : sessions.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="text-center py-12 text-muted-foreground">No sessions</TableCell></TableRow>
            ) : (
              sessions.map((s) => (
                <TableRow key={s.id} className="group">
                  <TableCell className="text-sm font-medium">{s.name}</TableCell>
                  <TableCell className="text-sm">{s.user_id}</TableCell>
                  <TableCell className="text-sm">{s.agent_id || "—"}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{s.expires_at ? new Date(s.expires_at).toLocaleString() : "—"}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{new Date(s.created_at).toLocaleString()}</TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" className="h-7 w-7 opacity-0 group-hover:opacity-100" onClick={() => setDeleteId(s.id)}>
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
          <DialogHeader><DialogTitle>Create Session</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Input placeholder="Session name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <Input placeholder="User ID" value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} />
            <Input placeholder="Agent ID (optional)" value={form.agent_id} onChange={(e) => setForm({ ...form, agent_id: e.target.value })} />
            <Input placeholder="Expires in minutes (optional)" type="number" value={form.expires_in_minutes} onChange={(e) => setForm({ ...form, expires_in_minutes: e.target.value })} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={!form.name || !form.user_id}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Delete Session</DialogTitle></DialogHeader>
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

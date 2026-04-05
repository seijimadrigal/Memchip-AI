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
import { getWebhooks, createWebhook, deleteWebhook } from "@/lib/api";
import { toast } from "sonner";

interface WebhookEntry {
  id: string;
  url: string;
  events: string[];
  active: boolean;
  created_at: string;
}

const ALL_EVENTS = ["memory.created", "memory.updated", "memory.deleted", "memory.searched", "session.created", "decay.cleanup"];

export default function WebhooksPage() {
  const [webhooks, setWebhooks] = useState<WebhookEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [form, setForm] = useState({ url: "", secret: "", events: [] as string[] });

  const load = async () => {
    setLoading(true);
    try {
      const res = await getWebhooks();
      setWebhooks(res.webhooks || res || []);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const toggleEvent = (ev: string) => {
    setForm((f) => ({
      ...f,
      events: f.events.includes(ev) ? f.events.filter((e) => e !== ev) : [...f.events, ev],
    }));
  };

  const handleCreate = async () => {
    try {
      await createWebhook({ url: form.url, events: form.events, secret: form.secret || undefined });
      toast.success("Webhook created");
      setShowCreate(false);
      setForm({ url: "", secret: "", events: [] });
      load();
    } catch { toast.error("Failed to create webhook"); }
  };

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await deleteWebhook(deleteId);
      toast.success("Webhook deleted");
      setDeleteId(null);
      load();
    } catch { toast.error("Failed to delete"); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Webhooks</h1>
          <p className="text-muted-foreground">HTTP callbacks for memory events</p>
        </div>
        <Button size="sm" className="gap-1.5" onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4" /> New Webhook
        </Button>
      </div>

      <div className="border border-border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="text-xs font-medium">URL</TableHead>
              <TableHead className="text-xs font-medium">Events</TableHead>
              <TableHead className="w-20 text-xs font-medium">Status</TableHead>
              <TableHead className="w-16 text-xs font-medium" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={4} className="text-center py-12 text-muted-foreground">Loading...</TableCell></TableRow>
            ) : webhooks.length === 0 ? (
              <TableRow><TableCell colSpan={4} className="text-center py-12 text-muted-foreground">No webhooks</TableCell></TableRow>
            ) : (
              webhooks.map((w) => (
                <TableRow key={w.id} className="group">
                  <TableCell className="text-sm font-mono truncate max-w-xs">{w.url}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {w.events.map((ev) => (
                        <Badge key={ev} variant="secondary" className="text-[11px]">{ev}</Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={w.active !== false ? "text-emerald-400 border-emerald-500/30" : "text-muted-foreground"}>
                      {w.active !== false ? "Active" : "Inactive"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" className="h-7 w-7 opacity-0 group-hover:opacity-100" onClick={() => setDeleteId(w.id)}>
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
          <DialogHeader><DialogTitle>Create Webhook</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Input placeholder="https://example.com/webhook" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
            <Input placeholder="Secret (optional)" value={form.secret} onChange={(e) => setForm({ ...form, secret: e.target.value })} />
            <div>
              <p className="text-sm font-medium mb-2">Events</p>
              <div className="flex flex-wrap gap-2">
                {ALL_EVENTS.map((ev) => (
                  <button
                    key={ev}
                    onClick={() => toggleEvent(ev)}
                    className={`px-2.5 py-1 rounded-md text-xs border transition-colors ${
                      form.events.includes(ev)
                        ? "bg-primary text-primary-foreground border-primary"
                        : "bg-muted/50 text-muted-foreground border-border hover:border-primary/50"
                    }`}
                  >
                    {ev}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={!form.url || form.events.length === 0}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Delete Webhook</DialogTitle></DialogHeader>
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

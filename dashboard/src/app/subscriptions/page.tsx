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
import { Bell, Plus, Trash2 } from "lucide-react";
import { getSubscriptions, createSubscription, deleteSubscription, getAgentsList } from "@/lib/api";
import { toast } from "sonner";

interface Subscription {
  id: string;
  agent_id: string;
  scope_filter: string | null;
  pool_filter: string | null;
  category_filter: string | null;
  event_types: string[];
  is_active: boolean;
  created_at: string;
}

const EVENT_OPTIONS = ["created", "updated", "superseded", "archived", "disputed"];

export default function SubscriptionsPage() {
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [agents, setAgents] = useState<{agent_id: string | null; count: number}[]>([]);
  const [form, setForm] = useState({
    agent_id: "",
    scope_filter: "",
    pool_filter: "",
    category_filter: "",
    event_types: ["created", "superseded"] as string[],
  });

  const load = async () => {
    setLoading(true);
    try {
      const res = await getSubscriptions();
      setSubs(Array.isArray(res) ? res : res.subscriptions || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);
  useEffect(() => {
    getAgentsList().then(setAgents).catch(() => {});
  }, []);

  const handleCreate = async () => {
    if (!form.agent_id) { toast.error("Agent ID required"); return; }
    try {
      const data: Record<string, unknown> = { agent_id: form.agent_id, event_types: form.event_types };
      if (form.scope_filter) data.scope_filter = form.scope_filter;
      if (form.pool_filter) data.pool_filter = form.pool_filter;
      if (form.category_filter) data.category_filter = form.category_filter;
      await createSubscription(data as Parameters<typeof createSubscription>[0]);
      toast.success("Subscription created");
      setShowCreate(false);
      setForm({ agent_id: "", scope_filter: "", pool_filter: "", category_filter: "", event_types: ["created", "superseded"] });
      load();
    } catch { toast.error("Failed to create"); }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteSubscription(id);
      toast.success("Subscription deleted");
      load();
    } catch { toast.error("Failed to delete"); }
  };

  const toggleEvent = (evt: string) => {
    setForm(f => ({
      ...f,
      event_types: f.event_types.includes(evt)
        ? f.event_types.filter(e => e !== evt)
        : [...f.event_types, evt],
    }));
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Bell className="h-5 w-5 text-purple-400" /> Subscriptions
          </h1>
          <p className="text-muted-foreground">Event-driven notifications for agents</p>
        </div>
        <Button size="sm" className="gap-1.5" onClick={() => setShowCreate(true)}>
          <Plus className="h-3.5 w-3.5" /> New Subscription
        </Button>
      </div>

      <div className="border border-border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="w-28 text-xs font-medium">Agent</TableHead>
              <TableHead className="w-24 text-xs font-medium">Scope</TableHead>
              <TableHead className="w-28 text-xs font-medium">Pool</TableHead>
              <TableHead className="w-28 text-xs font-medium">Category</TableHead>
              <TableHead className="text-xs font-medium">Events</TableHead>
              <TableHead className="w-24 text-xs font-medium">Status</TableHead>
              <TableHead className="w-16 text-xs font-medium" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={7} className="text-center py-12 text-muted-foreground">Loading...</TableCell></TableRow>
            ) : subs.length === 0 ? (
              <TableRow><TableCell colSpan={7} className="text-center py-12 text-muted-foreground">No subscriptions</TableCell></TableRow>
            ) : (
              subs.map((s) => (
                <TableRow key={s.id} className="group">
                  <TableCell className="text-sm font-medium">{s.agent_id}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{s.scope_filter || "all"}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{s.pool_filter || "all"}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{s.category_filter || "all"}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {(s.event_types || []).map((evt) => (
                        <Badge key={evt} variant="secondary" className="text-[10px]">{evt}</Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={s.is_active ? "default" : "secondary"} className="text-[10px]">
                      {s.is_active ? "active" : "paused"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 opacity-0 group-hover:opacity-100"
                      onClick={() => handleDelete(s.id)}
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

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader><DialogTitle>Create Subscription</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-xs text-muted-foreground">Agent *</label>
              <select
                value={form.agent_id}
                onChange={(e) => setForm({ ...form, agent_id: e.target.value })}
                className="w-full h-9 px-3 text-sm rounded-md border border-border bg-background"
              >
                <option value="">Select agent...</option>
                {agents.filter(a => a.agent_id).map((a) => (
                  <option key={a.agent_id} value={a.agent_id!}>{a.agent_id} ({a.count} memories)</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-muted-foreground">Scope Filter</label>
                <select
                  value={form.scope_filter}
                  onChange={(e) => setForm({ ...form, scope_filter: e.target.value })}
                  className="w-full h-9 px-3 text-sm rounded-md border border-border bg-background"
                >
                  <option value="">All scopes</option>
                  <option value="private">private</option>
                  <option value="task">task</option>
                  <option value="project">project</option>
                  <option value="team">team</option>
                  <option value="global">global</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Pool Filter</label>
                <Input value={form.pool_filter} onChange={(e) => setForm({ ...form, pool_filter: e.target.value })} placeholder="shared:team" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Category Filter</label>
                <Input value={form.category_filter} onChange={(e) => setForm({ ...form, category_filter: e.target.value })} placeholder="trading" />
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-2 block">Event Types</label>
              <div className="flex flex-wrap gap-2">
                {EVENT_OPTIONS.map((evt) => (
                  <button
                    key={evt}
                    onClick={() => toggleEvent(evt)}
                    className={`px-3 py-1 rounded-full text-xs border transition-colors ${
                      form.event_types.includes(evt)
                        ? "bg-primary text-primary-foreground border-primary"
                        : "bg-card text-muted-foreground border-border hover:border-foreground/30"
                    }`}
                  >
                    {evt}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={!form.agent_id}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

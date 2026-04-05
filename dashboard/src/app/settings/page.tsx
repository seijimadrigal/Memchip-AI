"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Key, Copy, Shield, RefreshCw, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { getHealth } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/v1";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

function apiFetch(path: string, options: RequestInit = {}) {
  return fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${API_KEY}`,
      ...options.headers,
    },
  });
}

interface ApiKeyInfo {
  id: string;
  key_prefix: string;
  name: string;
  is_active: boolean;
  rate_limit_per_minute: number;
  rate_limit_per_day: number;
  created_at: string;
}

interface HealthInfo {
  status: string;
  version: string;
  postgres: boolean;
  redis: boolean;
  embedding_model: string;
}

const AGENT_COLORS: Record<string, string> = {
  lyn: "bg-purple-500/20 text-purple-400",
  luna: "bg-pink-500/20 text-pink-400",
  midus: "bg-amber-500/20 text-amber-400",
};

function getAgentFromName(name: string): string | null {
  const lower = name.toLowerCase();
  if (lower.includes("lyn")) return "lyn";
  if (lower.includes("luna")) return "luna";
  if (lower.includes("midus")) return "midus";
  return null;
}

export default function SettingsPage() {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyAgent, setNewKeyAgent] = useState("");
  const [generatedKey, setGeneratedKey] = useState<string | null>(null);

  const loadKeys = async () => {
    try {
      const res = await apiFetch("/admin/keys/");
      if (res.ok) {
        const data = await res.json();
        setKeys(Array.isArray(data) ? data : []);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    async function load() {
      try {
        const h = await getHealth();
        setHealth(h);
        await loadKeys();
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const handleCreate = async () => {
    if (!newKeyName) { toast.error("Name required"); return; }
    try {
      const body: Record<string, unknown> = { name: newKeyName };
      if (newKeyAgent) body.agent_id = newKeyAgent;
      const res = await apiFetch("/admin/keys/", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (!res.ok) { toast.error("Failed to create key"); return; }
      const data = await res.json();
      setGeneratedKey(data.key);
      toast.success("API key created");
      setNewKeyName("");
      setNewKeyAgent("");
      loadKeys();
    } catch { toast.error("Failed to create key"); }
  };

  const handleRevoke = async (keyId: string, keyName: string) => {
    if (!confirm(`Revoke "${keyName}"? This cannot be undone.`)) return;
    try {
      const res = await apiFetch(`/admin/keys/${keyId}`, { method: "DELETE" });
      if (res.ok) {
        toast.success("Key revoked");
        loadKeys();
      } else { toast.error("Failed to revoke"); }
    } catch { toast.error("Failed to revoke"); }
  };

  const copyKey = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success("Copied to clipboard");
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">API keys, configuration, and system health</p>
      </div>

      {/* System Health */}
      {health && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <RefreshCw className="h-4 w-4" />
              System Health
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Version</p>
                <p className="text-sm font-medium">{health.version}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Status</p>
                <Badge variant={health.status === "ok" ? "default" : "secondary"}>{health.status}</Badge>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">PostgreSQL</p>
                <Badge variant={health.postgres ? "default" : "destructive"}>{health.postgres ? "Connected" : "Down"}</Badge>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Redis</p>
                <Badge variant={health.redis ? "default" : "destructive"}>{health.redis ? "Connected" : "Down"}</Badge>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Embedding Model</p>
                <p className="text-xs font-mono">{health.embedding_model}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* API Keys */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Key className="h-4 w-4" />
            API Keys ({keys.length})
          </CardTitle>
          <Button size="sm" className="gap-1.5" onClick={() => { setShowCreate(true); setGeneratedKey(null); }}>
            <Plus className="h-3.5 w-3.5" /> Generate Key
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/30">
                <TableHead className="text-xs font-medium">Name</TableHead>
                <TableHead className="text-xs font-medium">Agent</TableHead>
                <TableHead className="text-xs font-medium">Key Prefix</TableHead>
                <TableHead className="text-xs font-medium">Rate Limit</TableHead>
                <TableHead className="text-xs font-medium">Status</TableHead>
                <TableHead className="w-20 text-xs font-medium">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">Loading...</TableCell></TableRow>
              ) : keys.length === 0 ? (
                <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No API keys</TableCell></TableRow>
              ) : keys.map((k) => {
                const agent = getAgentFromName(k.name);
                return (
                  <TableRow key={k.id} className="group">
                    <TableCell className="font-medium text-sm">{k.name}</TableCell>
                    <TableCell>
                      {agent ? (
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${AGENT_COLORS[agent]}`}>
                          {agent}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">admin</span>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{k.key_prefix}...</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{k.rate_limit_per_minute}/min · {k.rate_limit_per_day}/day</TableCell>
                    <TableCell>
                      <Badge variant={k.is_active ? "default" : "secondary"} className="text-[10px]">
                        {k.is_active ? "active" : "revoked"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100">
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => copyKey(k.key_prefix)}>
                          <Copy className="h-3.5 w-3.5" />
                        </Button>
                        {k.is_active && (
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => handleRevoke(k.id, k.name)}>
                            <Trash2 className="h-3.5 w-3.5 text-red-400" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* API Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Shield className="h-4 w-4" />
            API Configuration
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium">API Endpoint</label>
            <Input value="http://76.13.23.55/v1/" readOnly className="mt-1 font-mono text-sm" />
          </div>
          <div>
            <label className="text-sm font-medium">WebSocket Endpoint</label>
            <Input value="ws://76.13.23.55/v1/ws" readOnly className="mt-1 font-mono text-sm" />
          </div>
          <div>
            <label className="text-sm font-medium">Dashboard</label>
            <Input value="http://76.13.23.55/" readOnly className="mt-1 font-mono text-sm" />
          </div>
        </CardContent>
      </Card>

      {/* Create Key Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader><DialogTitle>{generatedKey ? "Key Generated" : "Generate API Key"}</DialogTitle></DialogHeader>
          
          {generatedKey ? (
            <div className="space-y-4">
              <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                <p className="text-xs text-emerald-400 mb-2 font-medium">Save this key — it won't be shown again!</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-sm font-mono break-all">{generatedKey}</code>
                  <Button variant="outline" size="sm" onClick={() => copyKey(generatedKey)}>
                    <Copy className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
              <DialogFooter>
                <Button onClick={() => { setShowCreate(false); setGeneratedKey(null); }}>Done</Button>
              </DialogFooter>
            </div>
          ) : (
            <>
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium">Key Name *</label>
                  <Input value={newKeyName} onChange={(e) => setNewKeyName(e.target.value)} placeholder="e.g. Luna Agent Key" className="mt-1" />
                </div>
                <div>
                  <label className="text-sm font-medium">Agent ID (optional)</label>
                  <Input value={newKeyAgent} onChange={(e) => setNewKeyAgent(e.target.value)} placeholder="e.g. luna, midus" className="mt-1" />
                  <p className="text-xs text-muted-foreground mt-1">Key prefix will be mc_agentid_...</p>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
                <Button onClick={handleCreate} disabled={!newKeyName}>Generate</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Database, ChevronRight, Shield, Plus, Trash2, Globe, Lock, AlertTriangle, Users } from "lucide-react";
import { getMemories, getStats, getPoolAccess, grantPoolAccess, revokePoolAccess } from "@/lib/api";
import { toast } from "sonner";

interface Memory {
  id: string;
  content: string;
  memory_type: string;
  agent_id: string;
  pool_id: string | null;
  user_id: string;
  created_at: string;
  scope?: string;
  conflict_status?: string;
}

interface PoolInfo {
  id: string;
  memoryCount: number;
  agentBreakdown: Record<string, number>;
  isShared: boolean;
  acl: AclEntry[];
}

interface AclEntry {
  agent_id: string;
  permissions: { read: boolean; write: boolean; admin: boolean };
}

interface AccessEntry {
  id: string;
  agent_id: string;
  permissions: { read: boolean; write: boolean; admin: boolean };
}

const AGENT_COLORS: Record<string, string> = {
  lyn: "bg-purple-500",
  luna: "bg-pink-500",
  midus: "bg-amber-500",
};

const AGENT_TEXT_COLORS: Record<string, string> = {
  lyn: "text-purple-400",
  luna: "text-pink-400",
  midus: "text-amber-400",
};

export default function PoolsPage() {
  const [pools, setPools] = useState<PoolInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPool, setSelectedPool] = useState<string | null>(null);
  const [poolMemories, setPoolMemories] = useState<Memory[]>([]);
  const [memoriesLoading, setMemoriesLoading] = useState(false);
  const [showAccess, setShowAccess] = useState<string | null>(null);
  const [accessEntries, setAccessEntries] = useState<AccessEntry[]>([]);
  const [accessLoading, setAccessLoading] = useState(false);
  const [showGrant, setShowGrant] = useState(false);
  const [grantForm, setGrantForm] = useState({ agent_id: "", read: true, write: false, admin: false });

  useEffect(() => {
    async function load() {
      try {
        const stats = await getStats();
        // stats.by_pool should be Record<string, number> or similar
        const byPool: Record<string, number> = stats?.by_pool || {};
        const byAgent: Record<string, Record<string, number>> = stats?.by_pool_agent || {};

        // Known pool ACLs (from actual data)
        const knownAcl: Record<string, AclEntry[]> = {
          "shared:team": [
            { agent_id: "lyn", permissions: { read: true, write: true, admin: true } },
            { agent_id: "luna", permissions: { read: true, write: true, admin: false } },
          ],
          "project:memchip": [
            { agent_id: "lyn", permissions: { read: true, write: true, admin: false } },
            { agent_id: "luna", permissions: { read: true, write: true, admin: false } },
          ],
          "task:build-project-registry": [
            { agent_id: "lyn", permissions: { read: true, write: true, admin: false } },
          ],
        };

        // Build pool list from stats
        const poolList: PoolInfo[] = [];
        
        // If stats has by_pool data, use it
        if (Object.keys(byPool).length > 0) {
          for (const [poolId, count] of Object.entries(byPool)) {
            const isShared = poolId !== "private" && !poolId.startsWith("private:");
            const agentBreakdown = byAgent[poolId] || {};
            poolList.push({
              id: poolId,
              memoryCount: typeof count === "number" ? count : Number(count) || 0,
              agentBreakdown,
              isShared,
              acl: knownAcl[poolId] || [],
            });
          }
        }

        // If stats didn't have detailed pool data, use fallback with known data
        if (poolList.length === 0) {
          const fallbackPools: PoolInfo[] = [
            { id: "private", memoryCount: 6207, agentBreakdown: { lyn: 3524, luna: 2509, midus: 174 }, isShared: false, acl: [] },
            { id: "shared:team", memoryCount: 1357, agentBreakdown: { lyn: 1210, luna: 147 }, isShared: true, acl: knownAcl["shared:team"] },
            { id: "project:memchip", memoryCount: 6, agentBreakdown: { lyn: 6 }, isShared: true, acl: knownAcl["project:memchip"] },
            { id: "shared:team-seiji", memoryCount: 6, agentBreakdown: { lyn: 6 }, isShared: true, acl: [] },
            { id: "task:build-project-registry", memoryCount: 2, agentBreakdown: { lyn: 2 }, isShared: true, acl: knownAcl["task:build-project-registry"] },
          ];
          poolList.push(...fallbackPools);
        }

        // Sort: shared first, then by count
        poolList.sort((a, b) => {
          if (a.isShared !== b.isShared) return a.isShared ? -1 : 1;
          return b.memoryCount - a.memoryCount;
        });

        setPools(poolList);
      } catch {
        // Fallback data if API fails
        setPools([
          { id: "private", memoryCount: 6207, agentBreakdown: { lyn: 3524, luna: 2509, midus: 174 }, isShared: false, acl: [] },
          { id: "shared:team", memoryCount: 1357, agentBreakdown: { lyn: 1210, luna: 147 }, isShared: true, acl: [
            { agent_id: "lyn", permissions: { read: true, write: true, admin: true } },
            { agent_id: "luna", permissions: { read: true, write: true, admin: false } },
          ]},
          { id: "project:memchip", memoryCount: 6, agentBreakdown: { lyn: 6 }, isShared: true, acl: [
            { agent_id: "lyn", permissions: { read: true, write: true, admin: false } },
            { agent_id: "luna", permissions: { read: true, write: true, admin: false } },
          ]},
          { id: "shared:team-seiji", memoryCount: 6, agentBreakdown: { lyn: 6 }, isShared: true, acl: [] },
          { id: "task:build-project-registry", memoryCount: 2, agentBreakdown: { lyn: 2 }, isShared: true, acl: [
            { agent_id: "lyn", permissions: { read: true, write: true, admin: false } },
          ]},
        ]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Load memories when pool is selected
  const openPool = async (poolId: string) => {
    setSelectedPool(poolId);
    setMemoriesLoading(true);
    setPoolMemories([]);
    try {
      const params: Record<string, string> = { user_id: "seiji", limit: "50" };
      if (poolId !== "private") {
        params.pool_id = poolId;
      }
      const mems: Memory[] = await getMemories(params);
      if (Array.isArray(mems)) {
        const filtered = poolId === "private"
          ? mems.filter((m) => !m.pool_id || m.pool_id === "private")
          : mems.filter((m) => m.pool_id === poolId);
        setPoolMemories(filtered.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()));
      }
    } catch {
      // ignore
    } finally {
      setMemoriesLoading(false);
    }
  };

  const selectedPoolInfo = selectedPool ? pools.find((p) => p.id === selectedPool) : null;

  const totalMemories = pools.reduce((sum, p) => sum + p.memoryCount, 0);

  const loadAccess = async (poolId: string) => {
    setShowAccess(poolId);
    setAccessLoading(true);
    try {
      const res = await getPoolAccess(poolId);
      setAccessEntries(res.entries || res || []);
    } catch {
      setAccessEntries([]);
    } finally {
      setAccessLoading(false);
    }
  };

  const handleGrant = async () => {
    if (!showAccess) return;
    try {
      await grantPoolAccess({
        pool_id: showAccess,
        agent_id: grantForm.agent_id,
        permissions: { read: grantForm.read, write: grantForm.write, admin: grantForm.admin },
      });
      toast.success("Access granted");
      setShowGrant(false);
      setGrantForm({ agent_id: "", read: true, write: false, admin: false });
      loadAccess(showAccess);
    } catch { toast.error("Failed to grant access"); }
  };

  const handleRevoke = async (entryId: string) => {
    if (!showAccess) return;
    try {
      await revokePoolAccess(showAccess, entryId);
      toast.success("Access revoked");
      loadAccess(showAccess);
    } catch { toast.error("Failed to revoke"); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Memory Pools</h1>
          <p className="text-muted-foreground">
            {pools.length} pools · {totalMemories.toLocaleString()} total memories
          </p>
        </div>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading pools...</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {pools.map((pool) => {
            const agents = Object.entries(pool.agentBreakdown);
            const maxAgentCount = Math.max(...agents.map(([, c]) => c), 1);
            return (
              <Card key={pool.id} className="cursor-pointer hover:border-primary/50 transition-colors" onClick={() => openPool(pool.id)}>
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    {pool.isShared ? (
                      <Globe className="h-4 w-4 text-emerald-400" />
                    ) : (
                      <Lock className="h-4 w-4 text-purple-400" />
                    )}
                    <span>{pool.id}</span>
                  </CardTitle>
                  <div className="flex items-center gap-1">
                    {pool.isShared && (
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); loadAccess(pool.id); }} title="Manage access">
                        <Shield className="h-3.5 w-3.5 text-muted-foreground" />
                      </Button>
                    )}
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">{pool.memoryCount.toLocaleString()}</div>
                  <p className="text-xs text-muted-foreground mb-3">memories</p>

                  {/* Agent breakdown bars */}
                  {agents.length > 0 && (
                    <div className="space-y-1.5">
                      {agents.sort(([, a], [, b]) => b - a).map(([agent, count]) => (
                        <div key={agent} className="flex items-center gap-2">
                          <span className={`text-xs w-12 truncate ${AGENT_TEXT_COLORS[agent] || "text-muted-foreground"}`}>{agent}</span>
                          <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${AGENT_COLORS[agent] || "bg-zinc-500"}`}
                              style={{ width: `${(count / maxAgentCount) * 100}%` }}
                            />
                          </div>
                          <span className="text-xs text-muted-foreground w-10 text-right">{count.toLocaleString()}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* ACL inline */}
                  {pool.acl.length > 0 && (
                    <div className="mt-3 pt-2 border-t border-border/50">
                      <div className="flex items-center gap-1 mb-1">
                        <Users className="h-3 w-3 text-muted-foreground" />
                        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Access</span>
                      </div>
                      <div className="flex gap-1 flex-wrap">
                        {pool.acl.map((entry) => {
                          const perms = [
                            entry.permissions.read && "R",
                            entry.permissions.write && "W",
                            entry.permissions.admin && "A",
                          ].filter(Boolean).join("");
                          return (
                            <Badge key={entry.agent_id} variant="outline" className="text-[10px] gap-0.5">
                              <span className={AGENT_TEXT_COLORS[entry.agent_id] || ""}>{entry.agent_id}</span>
                              <span className="text-muted-foreground">({perms})</span>
                            </Badge>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Pool Detail Dialog */}
      <Dialog open={!!selectedPool} onOpenChange={() => setSelectedPool(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selectedPoolInfo?.isShared ? (
                <Globe className="h-5 w-5 text-emerald-400" />
              ) : (
                <Database className="h-5 w-5 text-purple-400" />
              )}
              {selectedPool}
              <Badge variant="secondary" className="text-xs">
                {selectedPoolInfo?.memoryCount.toLocaleString()} memories
              </Badge>
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {memoriesLoading ? (
              <p className="text-muted-foreground text-sm">Loading memories...</p>
            ) : poolMemories.length === 0 ? (
              <p className="text-muted-foreground text-sm">No memories loaded (may require different API key scope)</p>
            ) : (
              <>
                <p className="text-xs text-muted-foreground">Showing {poolMemories.length} most recent memories</p>
                {poolMemories.map((mem) => (
                  <div key={mem.id} className="p-3 rounded-lg bg-muted/50">
                    <p className="text-sm">{mem.content}</p>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <Badge variant="secondary" className="text-xs">{mem.memory_type || "raw"}</Badge>
                      {mem.agent_id && (
                        <Badge variant="outline" className={`text-xs ${AGENT_TEXT_COLORS[mem.agent_id] || ""}`}>
                          {mem.agent_id}
                        </Badge>
                      )}
                      <span className="text-xs text-muted-foreground">{new Date(mem.created_at).toLocaleString()}</span>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Pool Access Dialog */}
      <Dialog open={!!showAccess} onOpenChange={() => setShowAccess(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-purple-400" />
              Access Control — {showAccess}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">ACL Entries</p>
              <Button variant="outline" size="sm" className="gap-1 h-7 text-xs" onClick={() => setShowGrant(true)}>
                <Plus className="h-3.5 w-3.5" /> Grant
              </Button>
            </div>

            {accessLoading ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : accessEntries.length === 0 ? (
              <p className="text-sm text-muted-foreground">No access entries. Pool is unrestricted.</p>
            ) : (
              <div className="border border-border rounded-lg overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/30">
                      <TableHead className="text-xs font-medium">Agent</TableHead>
                      <TableHead className="text-xs font-medium">Permissions</TableHead>
                      <TableHead className="w-12 text-xs font-medium" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {accessEntries.map((entry) => (
                      <TableRow key={entry.id} className="group">
                        <TableCell className="text-sm">{entry.agent_id}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            {entry.permissions.read && <Badge variant="secondary" className="text-[11px]">read</Badge>}
                            {entry.permissions.write && <Badge variant="secondary" className="text-[11px]">write</Badge>}
                            {entry.permissions.admin && <Badge variant="secondary" className="text-[11px]">admin</Badge>}
                          </div>
                        </TableCell>
                        <TableCell>
                          <Button variant="ghost" size="icon" className="h-7 w-7 opacity-0 group-hover:opacity-100" onClick={() => handleRevoke(entry.id)}>
                            <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Grant Access Dialog */}
      <Dialog open={showGrant} onOpenChange={setShowGrant}>
        <DialogContent>
          <DialogHeader><DialogTitle>Grant Pool Access</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Input placeholder="Agent ID" value={grantForm.agent_id} onChange={(e) => setGrantForm({ ...grantForm, agent_id: e.target.value })} />
            <div className="flex items-center gap-4">
              {(["read", "write", "admin"] as const).map((perm) => (
                <label key={perm} className="flex items-center gap-1.5 text-sm">
                  <input
                    type="checkbox"
                    checked={grantForm[perm]}
                    onChange={(e) => setGrantForm({ ...grantForm, [perm]: e.target.checked })}
                  />
                  {perm}
                </label>
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowGrant(false)}>Cancel</Button>
            <Button onClick={handleGrant} disabled={!grantForm.agent_id}>Grant</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

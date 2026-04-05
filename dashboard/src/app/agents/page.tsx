"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Users, Bot, RefreshCw, Trash2 } from "lucide-react";
import { getStats, getMemories } from "@/lib/api";
import { useRouter } from "next/navigation";

interface AgentInfo {
  id: string;
  memoryCount: number;
  lastUpdated: string;
  pools: string[];
}

const TABS = [
  { key: "AGENT", label: "AGENT", icon: Bot },
];

export default function EntitiesPage() {
  const router = useRouter();
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const stats = await getStats();
        const byAgent = (stats.by_agent || {}) as Record<string, number>;
        
        const infos: AgentInfo[] = Object.entries(byAgent).map(([id, count]) => ({
          id,
          memoryCount: count,
          lastUpdated: "",
          pools: [],
        }));

        // Get last updated for each agent
        for (const info of infos) {
          try {
            const mems = await getMemories({ user_id: "seiji", limit: "1" });
            if (Array.isArray(mems) && mems.length > 0) {
              const agentMems = mems.filter((m: { agent_id?: string }) => m.agent_id === info.id);
              if (agentMems.length > 0) {
                info.lastUpdated = agentMems[0].created_at;
              }
            }
          } catch {}
        }

        setAgents(infos);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Entities</h1>
        <Button variant="outline" size="sm" className="gap-1.5 text-xs h-8" onClick={() => window.location.reload()}>
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-border pb-0">
        {TABS.map((t) => (
          <button
            key={t.key}
            className="flex items-center gap-1.5 px-3 py-2 text-sm border-b-2 border-foreground text-foreground font-medium -mb-px"
          >
            <t.icon className="h-3.5 w-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="border border-border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="text-xs font-medium">Entity</TableHead>
              <TableHead className="w-32 text-xs font-medium">Memories</TableHead>
              <TableHead className="w-48 text-xs font-medium">Updated On</TableHead>
              <TableHead className="w-20 text-xs font-medium text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={4} className="text-center py-12 text-muted-foreground">Loading...</TableCell></TableRow>
            ) : agents.length === 0 ? (
              <TableRow><TableCell colSpan={4} className="text-center py-12 text-muted-foreground">No agents found</TableCell></TableRow>
            ) : (
              agents.map((agent) => (
                <TableRow
                  key={agent.id}
                  className="cursor-pointer hover:bg-muted/40"
                  onClick={() => router.push(`/memories?agent=${agent.id}`)}
                >
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Users className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">{agent.id}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{agent.memoryCount.toLocaleString()}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {agent.lastUpdated ? new Date(agent.lastUpdated + "Z").toLocaleString() : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="icon" className="h-7 w-7">
                      <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                    </Button>
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

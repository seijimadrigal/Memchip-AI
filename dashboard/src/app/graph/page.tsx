"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { GitBranch, Search, Filter } from "lucide-react";
import { getGraph, getAgentsList } from "@/lib/api";

interface GraphNode {
  id: string;
  label: string;
  type: string;
  connections: number;
  memory_count?: number;
}

interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  agent_id?: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
}

const GARBAGE_LABELS = new Set([
  "true", "false", "null", "none", "yes", "no", "undefined", "nan", "n/a", "na",
]);

function isGarbageNode(label: string): boolean {
  const lower = label.toLowerCase().trim();
  if (lower.length < 2) return true;
  if (GARBAGE_LABELS.has(lower)) return true;
  if (/^\d+$/.test(lower)) return true;
  return false;
}

const TYPE_COLORS: Record<string, string> = {
  person: "#8b5cf6",
  entity: "#3b82f6",
  location: "#10b981",
  organization: "#f59e0b",
  concept: "#ef4444",
  event: "#ec4899",
  technology: "#06b6d4",
  default: "#6b7280",
};

const AGENT_COLORS: Record<string, string> = {
  lyn: "#8b5cf6",
  luna: "#ec4899",
  midus: "#f59e0b",
};

function getTypeColor(type: string): string {
  const lower = type.toLowerCase();
  for (const [key, color] of Object.entries(TYPE_COLORS)) {
    if (lower.includes(key)) return color;
  }
  return TYPE_COLORS.default;
}

function inferType(label: string): string {
  const lower = label.toLowerCase();
  if (lower.match(/^(seiji|lyn|luna|lin|midus|cj)/)) return "person";
  if (lower.includes("org") || lower.includes("company") || lower.includes("team")) return "organization";
  if (lower.includes("city") || lower.includes("country") || lower.includes("location") || lower.includes("ho chi minh")) return "location";
  if (lower.includes("memchip") || lower.includes("openclaw") || lower.includes("api") || lower.includes("dashboard")) return "technology";
  return "entity";
}

export default function GraphPage() {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [limit, setLimit] = useState("500");
  const [agentFilter, setAgentFilter] = useState("all");
  const [agents, setAgents] = useState<string[]>([]);

  const loadGraph = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { user_id: "seiji", limit };
      if (agentFilter !== "all") params.agent_id = agentFilter;
      const res = await getGraph(params);
      setData(res);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [limit, agentFilter]);

  useEffect(() => { loadGraph(); }, [loadGraph]);

  useEffect(() => {
    getAgentsList().then((res) => {
      const list = Array.isArray(res) ? res.map((a: { agent_id?: string } | string) => typeof a === "string" ? a : a.agent_id || "") .filter(Boolean) : [];
      setAgents(list);
    }).catch(() => {});
  }, []);

  // Filter out garbage nodes
  const cleanNodes = useMemo(() => {
    if (!data) return [];
    return data.nodes.filter((n) => !isGarbageNode(n.label));
  }, [data]);

  const filteredNodes = useMemo(() => {
    if (!search) return cleanNodes;
    const q = search.toLowerCase();
    return cleanNodes.filter((n) => n.label.toLowerCase().includes(q));
  }, [cleanNodes, search]);

  const filteredNodeIds = useMemo(() => new Set(filteredNodes.map((n) => n.id)), [filteredNodes]);

  const filteredEdges = useMemo(() => {
    if (!data) return [];
    return data.edges.filter((e) => filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target));
  }, [data, filteredNodeIds]);

  const selectedEdges = useMemo(() => {
    if (!selectedNode || !data) return [];
    return data.edges.filter((e) => e.source === selectedNode || e.target === selectedNode);
  }, [data, selectedNode]);

  const connectedIds = useMemo(() => {
    const ids = new Set<string>();
    if (selectedNode) {
      ids.add(selectedNode);
      selectedEdges.forEach((e) => { ids.add(e.source); ids.add(e.target); });
    }
    return ids;
  }, [selectedNode, selectedEdges]);

  const topEntities = useMemo(() => {
    if (!cleanNodes.length) return [];
    return [...cleanNodes].sort((a, b) => b.connections - a.connections).slice(0, 20);
  }, [cleanNodes]);

  // Layout: place nodes in a spiral pattern
  const nodePositions = useMemo(() => {
    const positions = new Map<string, { x: number; y: number }>();
    const nodes = filteredNodes;
    const cx = 400, cy = 300;
    const n = nodes.length;
    if (n === 0) return positions;

    const sorted = [...nodes].sort((a, b) => b.connections - a.connections);
    sorted.forEach((node, i) => {
      if (i === 0) {
        positions.set(node.id, { x: cx, y: cy });
      } else {
        const angle = (i * 2.4);
        const r = Math.sqrt(i) * 45;
        positions.set(node.id, {
          x: cx + r * Math.cos(angle),
          y: cy + r * Math.sin(angle),
        });
      }
    });
    return positions;
  }, [filteredNodes]);

  const maxConn = useMemo(() => {
    if (!cleanNodes.length) return 1;
    return Math.max(...cleanNodes.map((n) => n.connections), 1);
  }, [cleanNodes]);

  const viewBox = useMemo(() => {
    if (nodePositions.size === 0) return `0 0 800 600`;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodePositions.forEach(({ x, y }) => {
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    });
    const pad = 60;
    return `${minX - pad} ${minY - pad} ${maxX - minX + pad * 2} ${maxY - minY + pad * 2}`;
  }, [nodePositions]);

  const garbageCount = useMemo(() => {
    if (!data) return 0;
    return data.nodes.length - cleanNodes.length;
  }, [data, cleanNodes]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Knowledge Graph</h1>
          <p className="text-muted-foreground">Entity relationships extracted from memories</p>
        </div>
      </div>

      {/* Stats */}
      {data && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Card>
            <CardContent className="pt-4 pb-3">
              <div className="text-2xl font-bold">{data.total_nodes.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">Total Entities</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 pb-3">
              <div className="text-2xl font-bold">{data.total_edges.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">Total Relations</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 pb-3">
              <div className="text-2xl font-bold">{filteredNodes.length}</div>
              <p className="text-xs text-muted-foreground">Visible Nodes</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 pb-3">
              <div className="text-2xl font-bold">{filteredEdges.length}</div>
              <p className="text-xs text-muted-foreground">Visible Edges</p>
            </CardContent>
          </Card>
          {garbageCount > 0 && (
            <Card>
              <CardContent className="pt-4 pb-3">
                <div className="text-2xl font-bold text-yellow-500">{garbageCount}</div>
                <p className="text-xs text-muted-foreground">Filtered Out</p>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search entities..."
            className="pl-9"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setSelectedNode(null); }}
          />
        </div>
        <div className="flex items-center gap-1.5">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <select
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
          >
            <option value="all">All Agents</option>
            {agents.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
        </div>
        <select
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          value={limit}
          onChange={(e) => setLimit(e.target.value)}
        >
          <option value="100">100 relations</option>
          <option value="200">200 relations</option>
          <option value="500">500 relations</option>
          <option value="1000">1000 relations</option>
          <option value="2000">2000 relations</option>
        </select>
        {selectedNode && (
          <Badge
            variant="secondary"
            className="cursor-pointer"
            onClick={() => setSelectedNode(null)}
          >
            ✕ {selectedNode}
          </Badge>
        )}
      </div>

      <div className="flex gap-4">
        {/* Graph SVG */}
        <Card className="flex-1 overflow-hidden">
          <CardContent className="p-0">
            {loading ? (
              <div className="flex items-center justify-center h-[600px] text-muted-foreground">Loading graph...</div>
            ) : filteredNodes.length === 0 ? (
              <div className="flex items-center justify-center h-[600px] text-muted-foreground">No entities found</div>
            ) : (
              <svg
                width="100%"
                height="600"
                viewBox={viewBox}
                className="bg-background"
              >
                {/* Edges */}
                {filteredEdges.map((edge, i) => {
                  const from = nodePositions.get(edge.source);
                  const to = nodePositions.get(edge.target);
                  if (!from || !to) return null;
                  const isHighlighted = selectedNode && (edge.source === selectedNode || edge.target === selectedNode);
                  const isDimmed = selectedNode && !isHighlighted;
                  const agentColor = edge.agent_id ? AGENT_COLORS[edge.agent_id] || "#6b7280" : "#374151";
                  return (
                    <g key={`e-${i}`}>
                      <line
                        x1={from.x}
                        y1={from.y}
                        x2={to.x}
                        y2={to.y}
                        stroke={isHighlighted ? "#8b5cf6" : agentColor}
                        strokeWidth={isHighlighted ? 2 : 0.5}
                        opacity={isDimmed ? 0.1 : isHighlighted ? 1 : 0.3}
                      />
                      {isHighlighted && (
                        <text
                          x={(from.x + to.x) / 2}
                          y={(from.y + to.y) / 2 - 4}
                          textAnchor="middle"
                          fontSize="7"
                          fill="#a78bfa"
                          className="pointer-events-none"
                        >
                          {edge.relation}
                        </text>
                      )}
                    </g>
                  );
                })}
                {/* Nodes */}
                {filteredNodes.map((node) => {
                  const pos = nodePositions.get(node.id);
                  if (!pos) return null;
                  const connRatio = node.connections / maxConn;
                  const r = 6 + connRatio * 22;
                  const type = node.type !== "entity" ? node.type : inferType(node.label);
                  const color = getTypeColor(type);
                  const isSelected = node.id === selectedNode;
                  const isConnected = connectedIds.has(node.id);
                  const isDimmed = selectedNode && !isConnected;
                  return (
                    <g
                      key={node.id}
                      className="cursor-pointer"
                      onClick={() => setSelectedNode(node.id === selectedNode ? null : node.id)}
                    >
                      {/* Glow for high-connection nodes */}
                      {connRatio > 0.3 && !isDimmed && (
                        <circle
                          cx={pos.x}
                          cy={pos.y}
                          r={r + 4}
                          fill="none"
                          stroke={color}
                          strokeWidth={1}
                          opacity={0.3}
                        />
                      )}
                      <circle
                        cx={pos.x}
                        cy={pos.y}
                        r={r}
                        fill={color}
                        opacity={isDimmed ? 0.15 : isSelected ? 1 : 0.5 + connRatio * 0.5}
                        stroke={isSelected ? "#fff" : "none"}
                        strokeWidth={isSelected ? 2 : 0}
                      />
                      <text
                        x={pos.x}
                        y={pos.y + r + 10}
                        textAnchor="middle"
                        fontSize="8"
                        fill={isDimmed ? "#4b5563" : "#d1d5db"}
                        fontWeight={connRatio > 0.5 ? "bold" : "normal"}
                        className="pointer-events-none select-none"
                      >
                        {node.label.length > 20 ? node.label.slice(0, 18) + "…" : node.label}
                      </text>
                      {/* Memory count badge */}
                      {node.memory_count && node.memory_count > 0 && !isDimmed && (
                        <text
                          x={pos.x}
                          y={pos.y + 3}
                          textAnchor="middle"
                          fontSize="7"
                          fill="#fff"
                          fontWeight="bold"
                          className="pointer-events-none select-none"
                        >
                          {node.memory_count}
                        </text>
                      )}
                    </g>
                  );
                })}
              </svg>
            )}
          </CardContent>
        </Card>

        {/* Sidebar */}
        <div className="w-64 space-y-4 hidden lg:block">
          {/* Selected node info */}
          {selectedNode && data && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">
                  {selectedNode}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <p className="text-xs text-muted-foreground">{selectedEdges.length} connections</p>
                <div className="space-y-1 max-h-48 overflow-y-auto">
                  {selectedEdges.map((e, i) => {
                    const other = e.source === selectedNode ? e.target : e.source;
                    const dir = e.source === selectedNode ? "→" : "←";
                    return (
                      <div
                        key={i}
                        className="text-xs p-1.5 rounded bg-muted/50 cursor-pointer hover:bg-muted"
                        onClick={() => setSelectedNode(other)}
                      >
                        <span className="text-muted-foreground">{dir}</span>{" "}
                        <span className="text-purple-400">{e.relation}</span>{" "}
                        <span>{other}</span>
                        {e.agent_id && (
                          <span className="ml-1 text-[10px]" style={{ color: AGENT_COLORS[e.agent_id] || "#6b7280" }}>
                            [{e.agent_id}]
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Agent Legend */}
          {agents.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">Agents</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-1">
                  {agents.map((agent) => (
                    <div
                      key={agent}
                      className={`flex items-center gap-2 text-xs cursor-pointer p-1 rounded hover:bg-muted ${agentFilter === agent ? "bg-muted" : ""}`}
                      onClick={() => setAgentFilter(agentFilter === agent ? "all" : agent)}
                    >
                      <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: AGENT_COLORS[agent] || "#6b7280" }} />
                      <span>{agent}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Top entities */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <GitBranch className="h-4 w-4 text-purple-400" />
                Top Entities
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-1 max-h-96 overflow-y-auto">
                {topEntities.map((node) => (
                  <div
                    key={node.id}
                    className={`text-xs p-1.5 rounded cursor-pointer hover:bg-muted flex items-center justify-between ${
                      node.id === selectedNode ? "bg-muted" : ""
                    }`}
                    onClick={() => setSelectedNode(node.id === selectedNode ? null : node.id)}
                  >
                    <div className="flex items-center gap-1.5 truncate">
                      <div
                        className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ backgroundColor: getTypeColor(node.type !== "entity" ? node.type : inferType(node.label)) }}
                      />
                      <span className="truncate">{node.label}</span>
                    </div>
                    <Badge variant="secondary" className="text-[10px] ml-1 flex-shrink-0">{node.connections}</Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Legend */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-medium text-muted-foreground">Entity Types</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-1">
                {Object.entries(TYPE_COLORS).filter(([k]) => k !== "default").map(([type, color]) => (
                  <div key={type} className="flex items-center gap-2 text-xs">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                    <span className="capitalize text-muted-foreground">{type}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

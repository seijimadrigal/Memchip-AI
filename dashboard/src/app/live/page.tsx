"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Radio, Wifi, WifiOff, Trash2, Pause, Play } from "lucide-react";
import { getWsUrl } from "@/lib/api";

interface LiveEvent {
  id: string;
  type: string;
  timestamp: string;
  agent_id?: string;
  pool_id?: string;
  content?: string;
  memory_id?: string;
  data?: Record<string, unknown>;
}

export default function LiveFeedPage() {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [paused, setPaused] = useState(false);
  const [agentFilter, setAgentFilter] = useState("all");
  const wsRef = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const eventIdRef = useRef(0);

  const connect = useCallback(() => {
    const url = getWsUrl();
    if (!url) return;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setEvents((prev) => [
          ...prev,
          {
            id: `sys-${eventIdRef.current++}`,
            type: "system",
            timestamp: new Date().toISOString(),
            content: "Connected to MemChip WebSocket",
          },
        ]);
      };

      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data);
          const event: LiveEvent = {
            id: `evt-${eventIdRef.current++}`,
            type: data.type || data.event || "message",
            timestamp: data.timestamp || new Date().toISOString(),
            agent_id: data.agent_id,
            pool_id: data.pool_id,
            content: data.content || data.message || JSON.stringify(data),
            memory_id: data.memory_id || data.id,
            data,
          };
          if (!paused) {
            setEvents((prev) => [...prev.slice(-500), event]);
          }
        } catch {
          setEvents((prev) => [
            ...prev.slice(-500),
            {
              id: `raw-${eventIdRef.current++}`,
              type: "raw",
              timestamp: new Date().toISOString(),
              content: evt.data,
            },
          ]);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        setEvents((prev) => [
          ...prev,
          {
            id: `sys-${eventIdRef.current++}`,
            type: "system",
            timestamp: new Date().toISOString(),
            content: "Disconnected. Reconnecting in 3s...",
          },
        ]);
        setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        setConnected(false);
      };
    } catch {
      setTimeout(connect, 3000);
    }
  }, [paused]);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  useEffect(() => {
    if (scrollRef.current && !paused) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, paused]);

  const filteredEvents = events.filter((e) => {
    if (agentFilter !== "all" && e.agent_id && e.agent_id !== agentFilter) return false;
    return true;
  });

  const typeColors: Record<string, string> = {
    "memory.added": "bg-green-500/20 text-green-400",
    "memory.updated": "bg-blue-500/20 text-blue-400",
    "memory.deleted": "bg-red-500/20 text-red-400",
    system: "bg-yellow-500/20 text-yellow-400",
    message: "bg-gray-500/20 text-gray-400",
    raw: "bg-gray-500/20 text-gray-400",
  };

  return (
    <div className="space-y-6 h-full flex flex-col">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Radio className="h-5 w-5" />
            Live Feed
          </h1>
          <div className="flex items-center gap-2 mt-1">
            {connected ? (
              <><Wifi className="h-3 w-3 text-green-400" /><span className="text-xs text-green-400">Connected</span></>
            ) : (
              <><WifiOff className="h-3 w-3 text-red-400" /><span className="text-xs text-red-400">Disconnected</span></>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Select value={agentFilter} onValueChange={(v) => setAgentFilter(v || "all")}>
            <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="lyn">lyn</SelectItem>
              <SelectItem value="luna">luna</SelectItem>
              <SelectItem value="system">system</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="icon" onClick={() => setPaused(!paused)}>
            {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
          </Button>
          <Button variant="outline" size="icon" onClick={() => setEvents([])}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <Card className="flex-1 min-h-0">
        <CardContent className="p-0 h-full">
          <div ref={scrollRef} className="h-[calc(100vh-240px)] overflow-y-auto font-mono text-sm p-4 space-y-1">
            {filteredEvents.length === 0 ? (
              <p className="text-muted-foreground text-center py-8">
                Waiting for events... Memories added/updated/deleted will appear here in real time.
              </p>
            ) : (
              filteredEvents.map((evt) => (
                <div key={evt.id} className="flex items-start gap-2 py-1 hover:bg-muted/30 rounded px-2 transition-colors">
                  <span className="text-xs text-muted-foreground shrink-0 w-20">
                    {new Date(evt.timestamp).toLocaleTimeString()}
                  </span>
                  <Badge variant="secondary" className={`text-xs shrink-0 ${typeColors[evt.type] || ""}`}>
                    {evt.type}
                  </Badge>
                  {evt.agent_id && (
                    <Badge variant="outline" className="text-xs shrink-0">{evt.agent_id}</Badge>
                  )}
                  <span className="text-sm truncate">{evt.content}</span>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

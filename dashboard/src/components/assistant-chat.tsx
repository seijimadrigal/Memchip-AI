"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Send, Loader2, ChevronDown, Clock, Search, Database } from "lucide-react";

interface AssistantSource {
  id: string;
  content: string;
  memory_type: string;
  score: number;
  created_at?: string;
}

interface AssistantResponse {
  answer: string;
  sources: AssistantSource[];
  query_used: string;
  search_time_ms: number;
  total_memories_searched: number;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: AssistantSource[];
  search_time_ms?: number;
  total_memories_searched?: number;
  query_used?: string;
}

interface AssistantChatProps {
  apiUrl?: string;
  apiKey?: string;
  userId?: string;
  agentId?: string;
  compact?: boolean;
}

export function AssistantChat({
  apiUrl = "/v1/assistant/chat/",
  apiKey,
  userId = "seiji",
  agentId,
  compact = false,
}: AssistantChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const getApiKey = useCallback(() => {
    if (apiKey) return apiKey;
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("memchip_api_key");
      if (stored) return stored;
    }
    // Default key for the hosted dashboard
    return "mc_d798cc892328f4e598803eac5f675cb1ad301fc16a78fd6e";
  }, [apiKey]);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const sendMessage = async () => {
    const msg = input.trim();
    if (!msg || loading) return;

    const key = getApiKey();
    if (!key) {
      setMessages((prev) => [
        ...prev,
        { role: "user", content: msg },
        {
          role: "assistant",
          content:
            "No API key configured. Set it in Settings or pass it as a prop.",
        },
      ]);
      setInput("");
      return;
    }

    const history = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    setInput("");
    setLoading(true);

    try {
      // Resolve API URL — if relative, use the configured base
      let url = apiUrl;
      if (url.startsWith("/")) {
        const base =
          typeof window !== "undefined"
            ? localStorage.getItem("memchip_api_url") || ""
            : "";
        url = base ? `${base.replace(/\/$/, "")}${url}` : url;
      }

      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${key}`,
        },
        body: JSON.stringify({
          message: msg,
          user_id: userId,
          agent_id: agentId || undefined,
          history,
        }),
      });

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
      }

      const data: AssistantResponse = await resp.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          sources: data.sources,
          search_time_ms: data.search_time_ms,
          total_memories_searched: data.total_memories_searched,
          query_used: data.query_used,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${err instanceof Error ? err.message : "Unknown error"}`,
        },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const typeColor: Record<string, string> = {
    triple: "bg-blue-500/20 text-blue-400",
    summary: "bg-green-500/20 text-green-400",
    profile: "bg-purple-500/20 text-purple-400",
    temporal: "bg-orange-500/20 text-orange-400",
    raw: "bg-zinc-500/20 text-zinc-400",
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            <p>Ask me anything about your memories or how to use MemChip.</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted"
              }`}
            >
              <div className="whitespace-pre-wrap">{msg.content}</div>

              {/* Sources section */}
              {msg.sources && msg.sources.length > 0 && (
                <Collapsible className="mt-2">
                  <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
                    <ChevronDown className="h-3 w-3" />
                    <Database className="h-3 w-3" />
                    {msg.sources.length} source{msg.sources.length !== 1 ? "s" : ""}
                    {msg.search_time_ms !== undefined && (
                      <span className="ml-1">
                        · {msg.search_time_ms}ms
                      </span>
                    )}
                  </CollapsibleTrigger>
                  <CollapsibleContent className="mt-2 space-y-2">
                    {/* Search metadata */}
                    <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                      {msg.total_memories_searched !== undefined && (
                        <span className="flex items-center gap-1">
                          <Search className="h-3 w-3" />
                          {msg.total_memories_searched} searched
                        </span>
                      )}
                      {msg.search_time_ms !== undefined && (
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {msg.search_time_ms}ms
                        </span>
                      )}
                    </div>

                    {/* Source cards */}
                    {msg.sources.map((src) => (
                      <div
                        key={src.id}
                        className="rounded border border-border/50 bg-background/50 p-2 space-y-1"
                      >
                        <div className="flex items-center gap-2">
                          <Badge
                            variant="secondary"
                            className={`text-[10px] px-1.5 py-0 ${typeColor[src.memory_type] || ""}`}
                          >
                            {src.memory_type}
                          </Badge>
                          <span className="text-[10px] text-muted-foreground font-mono">
                            {src.score.toFixed(4)}
                          </span>
                          <span className="text-[10px] text-muted-foreground ml-auto font-mono">
                            {src.id.slice(0, 8)}…
                          </span>
                        </div>
                        <p className="text-[11px] text-muted-foreground line-clamp-2">
                          {src.content}
                        </p>
                        {src.created_at && (
                          <p className="text-[10px] text-muted-foreground/60">
                            {new Date(src.created_at).toLocaleDateString()}
                          </p>
                        )}
                      </div>
                    ))}
                  </CollapsibleContent>
                </Collapsible>
              )}
            </div>
          </div>
        ))}

        {/* Loading indicator */}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-muted rounded-lg px-3 py-2 text-sm flex items-center gap-2">
              <Loader2 className="h-3 w-3 animate-spin" />
              <span className="text-muted-foreground">Thinking…</span>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-border p-3">
        <div className="flex gap-2">
          <Input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your memories…"
            disabled={loading}
            className={compact ? "text-sm h-9" : ""}
          />
          <Button
            size={compact ? "sm" : "default"}
            onClick={sendMessage}
            disabled={loading || !input.trim()}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

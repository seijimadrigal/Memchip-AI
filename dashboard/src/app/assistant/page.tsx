"use client";

import { AssistantChat } from "@/components/assistant-chat";
import { Bot } from "lucide-react";

export default function AssistantPage() {
  return (
    <div className="flex flex-col h-[calc(100vh-3rem)]">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-primary/10">
          <Bot className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-xl font-bold tracking-tight">MemChip Assistant</h1>
          <p className="text-sm text-muted-foreground">
            Ask questions about your memories or how to use MemChip
          </p>
        </div>
      </div>

      {/* Chat */}
      <div className="flex-1 rounded-lg border border-border bg-card overflow-hidden">
        <AssistantChat />
      </div>
    </div>
  );
}

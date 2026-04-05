"use client";

import { useState } from "react";
import { AssistantChat } from "@/components/assistant-chat";
import { Button } from "@/components/ui/button";
import { MessageCircle, X, Sparkles } from "lucide-react";

export function AssistantWidget() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Chat panel */}
      <div
        className={`fixed bottom-20 right-6 z-50 w-[400px] h-[500px] rounded-xl border border-border bg-card shadow-2xl flex flex-col overflow-hidden transition-all duration-300 ease-out ${
          open
            ? "opacity-100 translate-y-0 pointer-events-auto"
            : "opacity-0 translate-y-4 pointer-events-none"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/50">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold">MemChip Assistant</span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => setOpen(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Chat body */}
        <div className="flex-1 overflow-hidden">
          <AssistantChat compact />
        </div>
      </div>

      {/* Floating button */}
      <Button
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-6 right-6 z-50 h-12 w-12 rounded-full shadow-lg p-0"
        size="icon"
      >
        {open ? (
          <X className="h-5 w-5" />
        ) : (
          <div className="relative">
            <MessageCircle className="h-5 w-5" />
            <span className="absolute -top-1.5 -right-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[9px] font-bold text-primary-foreground">
              AI
            </span>
          </div>
        )}
      </Button>
    </>
  );
}

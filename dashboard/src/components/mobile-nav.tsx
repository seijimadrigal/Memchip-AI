"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Cpu, Menu } from "lucide-react";
// Button removed — using plain span for SheetTrigger compatibility
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  LayoutDashboard,
  Brain,
  Users,
  Database,
  Activity,
  Settings,
  BarChart3,
  FileText,
  MessageSquare,
  Webhook,
  FileJson,
  BookOpen,
  Timer,
  GitBranch,
  Radio,
  Bell,
  FolderKanban,
} from "lucide-react";

const activityNav = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/activity", label: "Requests", icon: Activity },
  { href: "/agents", label: "Entities", icon: Users },
  { href: "/memories", label: "Memories", icon: Brain },
  { href: "/pools", label: "Pools", icon: Database },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/audit", label: "Audit Log", icon: FileText },
  { href: "/graph", label: "Graph", icon: GitBranch },
  { href: "/events", label: "Events", icon: Radio },
];

const managementNav = [
  { href: "/sessions", label: "Sessions", icon: MessageSquare },
  { href: "/webhooks", label: "Webhooks", icon: Webhook },
  { href: "/schemas", label: "Schemas", icon: FileJson },
  { href: "/instructions", label: "Instructions", icon: BookOpen },
  { href: "/decay", label: "Decay", icon: Timer },
  { href: "/subscriptions", label: "Subscriptions", icon: Bell },
];

const accountNav = [
  { href: "/settings", label: "Settings", icon: Settings },
];

export function MobileNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const NavLink = ({ href, label, icon: Icon }: { href: string; label: string; icon: React.ComponentType<{ className?: string }> }) => {
    const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
    return (
      <Link
        href={href}
        onClick={() => setOpen(false)}
        className={cn(
          "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
          active
            ? "bg-accent text-accent-foreground font-medium"
            : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
        )}
      >
        <Icon className="h-4 w-4" />
        {label}
      </Link>
    );
  };

  return (
    <div className="md:hidden flex items-center gap-2 px-4 py-3 border-b border-border bg-card">
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger>
          <span className="inline-flex items-center justify-center h-8 w-8 rounded-md hover:bg-accent">
            <Menu className="h-5 w-5" />
          </span>
        </SheetTrigger>
        <SheetContent side="left" className="w-64 p-0">
          <SheetHeader className="border-b border-border px-5 py-4">
            <SheetTitle className="flex items-center gap-2">
              <Cpu className="h-5 w-5 text-primary" />
              <span className="text-base font-bold tracking-tight">MemChip</span>
              <span className="text-[11px] text-muted-foreground ml-auto">v0.4.0</span>
            </SheetTitle>
          </SheetHeader>

          <nav className="flex-1 px-3 pt-5 space-y-5 overflow-y-auto">
            <div>
              <p className="px-3 mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                Activity
              </p>
              <div className="space-y-0.5">
                {activityNav.map((item) => (
                  <NavLink key={item.href} {...item} />
                ))}
              </div>
            </div>

            <div>
              <p className="px-3 mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                Management
              </p>
              <div className="space-y-0.5">
                {managementNav.map((item) => (
                  <NavLink key={item.href} {...item} />
                ))}
              </div>
            </div>

            <div>
              <p className="px-3 mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                Account
              </p>
              <div className="space-y-0.5">
                {accountNav.map((item) => (
                  <NavLink key={item.href} {...item} />
                ))}
              </div>
            </div>
          </nav>
        </SheetContent>
      </Sheet>
      <Cpu className="h-5 w-5 text-primary" />
      <span className="font-bold">MemChip</span>
    </div>
  );
}

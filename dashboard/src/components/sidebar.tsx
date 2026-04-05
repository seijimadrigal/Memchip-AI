"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Brain,
  Users,
  Database,
  Activity,
  Settings,
  Cpu,
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
  Bot,
} from "lucide-react";

const activityNav = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/assistant", label: "Assistant", icon: Bot },
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
  { href: "/docs", label: "Docs", icon: BookOpen },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  const NavLink = ({ href, label, icon: Icon }: { href: string; label: string; icon: React.ComponentType<{ className?: string }> }) => {
    const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
    return (
      <Link
        href={href}
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
    <aside className="hidden md:flex w-56 flex-col border-r border-border bg-card">
      {/* Logo */}
      <div className="flex items-center gap-2 px-5 py-4 border-b border-border">
        <Cpu className="h-5 w-5 text-primary" />
        <span className="text-base font-bold tracking-tight">MemChip</span>
      </div>

      {/* Nav Sections */}
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

      {/* Footer */}
      <div className="px-5 py-3 border-t border-border">
        <p className="text-[11px] text-muted-foreground">MemChip v0.4.0</p>
      </div>
    </aside>
  );
}

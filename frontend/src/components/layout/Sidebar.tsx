"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  MessageSquare,
  ShoppingBag,
  Users,
  Package,
  Bot,
  Radio,
  Zap,
  BarChart3,
  Layers,
  Settings,
  Lock,
  Menu,
  X,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";

export interface NavItem {
  title: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  status: "active" | "coming_soon" | "locked";
  badge?: string;
}

const activeNavItems: NavItem[] = [
  {
    title: "Dashboard",
    href: "/",
    icon: LayoutDashboard,
    status: "active",
  },
  {
    title: "Chat WhatsApp",
    href: "/chat",
    icon: MessageSquare,
    status: "active",
  },
  {
    title: "Pesanan",
    href: "/orders",
    icon: ShoppingBag,
    status: "active",
  },
  {
    title: "Customer",
    href: "/customers",
    icon: Users,
    status: "active",
  },
  {
    title: "Produk",
    href: "/products",
    icon: Package,
    status: "active",
  },
  {
    title: "Integrations",
    href: "/integrations",
    icon: Layers,
    status: "active",
  },
];

const comingSoonNavItems: NavItem[] = [
  {
    title: "AI Team",
    href: "/ai-team",
    icon: Bot,
    status: "coming_soon",
  },
  {
    title: "Broadcast",
    href: "/broadcast",
    icon: Radio,
    status: "coming_soon",
  },
  {
    title: "Automasi",
    href: "/automation",
    icon: Zap,
    status: "coming_soon",
  },
  {
    title: "Analytics",
    href: "/analytics",
    icon: BarChart3,
    status: "coming_soon",
  },
];

const systemNavItems: NavItem[] = [
  {
    title: "Pengaturan",
    href: "/settings",
    icon: Settings,
    status: "active",
  },
];

export const Sidebar: React.FC = () => {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const renderNavLink = (item: NavItem) => {
    const isActive =
      item.href === "/"
        ? pathname === "/"
        : pathname.startsWith(item.href);

    const isComingSoon = item.status === "coming_soon";

    return (
      <Link
        key={item.href}
        href={item.href}
        onClick={() => setMobileOpen(false)}
        className={cn(
          "flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-medium transition-all group relative",
          isActive
            ? "bg-blue-600/15 text-blue-400 border border-blue-500/20 font-semibold shadow-sm"
            : isComingSoon
            ? "text-slate-500 hover:text-slate-300 hover:bg-slate-900/60"
            : "text-slate-300 hover:text-slate-100 hover:bg-slate-800/60"
        )}
      >
        <div className="flex items-center gap-3 min-w-0">
          <item.icon
            className={cn(
              "w-4 h-4 shrink-0 transition-colors",
              isActive
                ? "text-blue-400"
                : isComingSoon
                ? "text-slate-600 group-hover:text-slate-400"
                : "text-slate-400 group-hover:text-slate-200"
            )}
          />
          <span className="truncate">{item.title}</span>
        </div>

        {isComingSoon && (
          <span className="flex items-center gap-1 text-[10px] text-slate-500 bg-slate-900/80 px-1.5 py-0.5 rounded border border-slate-800 font-medium">
            <Lock className="w-2.5 h-2.5" />
            <span>SOON</span>
          </span>
        )}
      </Link>
    );
  };

  return (
    <>
      {/* Mobile Toggle Button */}
      <div className="lg:hidden fixed top-3 left-4 z-50">
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Toggle navigation menu"
          className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 hover:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Backdrop overlay for mobile */}
      {mobileOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-40 transition-opacity"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={cn(
          "fixed top-0 bottom-0 left-0 z-40 w-64 bg-[#0b1120] border-r border-slate-800/80 flex flex-col transition-transform duration-200 ease-in-out lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
      >
        {/* Brand Header */}
        <div className="h-16 px-6 flex items-center gap-3 border-b border-slate-800/60 shrink-0">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center shadow-md shadow-blue-900/30">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5">
              <span className="font-bold text-base tracking-tight text-white">AI BOS</span>
              <Badge variant="default" size="sm" className="text-[9px] px-1.5 py-0 font-bold">
                MVP
              </Badge>
            </div>
            <span className="text-[11px] text-slate-400 font-medium">AI Business OS</span>
          </div>
        </div>

        {/* Navigation Menu Links */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
          {/* Active Navigation */}
          <div>
            <div className="px-3 mb-2 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              Utama
            </div>
            <nav className="space-y-1">{activeNavItems.map(renderNavLink)}</nav>
          </div>

          {/* Coming Soon Navigation */}
          <div>
            <div className="px-3 mb-2 text-[11px] font-semibold text-slate-500 uppercase tracking-wider flex items-center justify-between">
              <span>Fitur Lanjutan</span>
              <span className="text-[9px] text-slate-600 bg-slate-900 px-1 py-0.2 rounded border border-slate-800">
                PRO
              </span>
            </div>
            <nav className="space-y-1">{comingSoonNavItems.map(renderNavLink)}</nav>
          </div>

          {/* System Navigation */}
          <div>
            <div className="px-3 mb-2 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              Sistem
            </div>
            <nav className="space-y-1">{systemNavItems.map(renderNavLink)}</nav>
          </div>
        </div>

        {/* Footer / Status Indicator */}
        <div className="p-4 border-t border-slate-800/60 shrink-0">
          <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800/80 flex items-center gap-3">
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse shrink-0" />
            <div className="flex flex-col min-w-0">
              <span className="text-xs font-medium text-slate-300 truncate">System Active</span>
              <span className="text-[10px] text-slate-500 truncate">Core v1.0 • Step 5</span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
};

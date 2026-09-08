"use client";

import React from "react";
import { Bell, ChevronDown, Building2 } from "lucide-react";
import { Avatar } from "@/components/ui/Avatar";

export const Header: React.FC = () => {
  return (
    <header className="h-16 border-b border-slate-800/80 bg-slate-950/70 backdrop-blur-md sticky top-0 z-30 px-4 sm:px-6 flex items-center justify-between">
      {/* Left: Tenant/Business Context Display Placeholder */}
      <div className="flex items-center gap-3 pl-10 lg:pl-0">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 transition-colors cursor-pointer group">
          <div className="w-6 h-6 rounded bg-blue-600/20 text-blue-400 flex items-center justify-center border border-blue-500/30">
            <Building2 className="w-3.5 h-3.5" />
          </div>
          <div className="flex flex-col text-left">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-slate-200 group-hover:text-white transition-colors">
                Demo Merchant Tenant
              </span>
              <ChevronDown className="w-3 h-3 text-slate-500 group-hover:text-slate-300" />
            </div>
            <span className="text-[10px] text-slate-500 font-medium">Demo Tenant ID: demo-tenant-01</span>
          </div>
        </div>
      </div>

      {/* Right: Notifications & User Avatar Placeholder */}
      <div className="flex items-center gap-3">
        {/* Notification Bell Placeholder */}
        <button
          aria-label="Notifikasi"
          className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent hover:border-slate-800 transition-all relative"
        >
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-blue-500 rounded-full ring-2 ring-slate-950" />
        </button>

        <div className="h-4 w-px bg-slate-800 mx-0.5" />

        {/* User Identity Profile Placeholder */}
        <div className="flex items-center gap-2.5 pl-1 cursor-pointer">
          <Avatar name="Owner Account" size="sm" />
          <div className="hidden md:flex flex-col text-left">
            <span className="text-xs font-medium text-slate-200 leading-none">Business Owner</span>
            <span className="text-[10px] text-slate-500 mt-0.5">Owner Account (Demo)</span>
          </div>
        </div>
      </div>
    </header>
  );
};

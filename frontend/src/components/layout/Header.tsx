"use client";

import React, { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Bell, ChevronDown, Building2, LogOut, Check, ArrowRightLeft } from "lucide-react";
import { Avatar } from "@/components/ui/Avatar";
import { useAuth } from "@/lib/auth-context";

/**
 * App Shell Header with active tenant context indicator & switcher integration.
 * Triggers `POST /api/v1/auth/select-tenant` via `selectTenant` from `useAuth()`.
 */
export const Header: React.FC = () => {
  const { user, tenants, activeTenant, selectTenant, logout } = useAuth();
  const [showTenantMenu, setShowTenantMenu] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);

  const tenantMenuRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  const router = useRouter();

  // Close menus when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (tenantMenuRef.current && !tenantMenuRef.current.contains(event.target as Node)) {
        setShowTenantMenu(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setShowUserMenu(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelectBusiness = async (tenantId: string) => {
    setShowTenantMenu(false);
    try {
      const { redirectTo } = await selectTenant(tenantId);
      router.push(redirectTo);
    } catch {
      // Handled in auth context
    }
  };

  const handleLogout = async () => {
    setShowUserMenu(false);
    await logout();
    router.push("/login");
  };

  const userNameDisplay = user?.email ? user.email.split("@")[0] : "Account";

  return (
    <header className="h-16 border-b border-slate-800/80 bg-slate-950/70 backdrop-blur-md sticky top-0 z-30 px-4 sm:px-6 flex items-center justify-between">
      {/* Left: Active Business Context & Switcher */}
      <div className="flex items-center gap-3 pl-10 lg:pl-0 relative" ref={tenantMenuRef}>
        <button
          type="button"
          aria-label="Active Business Selector"
          onClick={() => setShowTenantMenu(!showTenantMenu)}
          className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 transition-colors group focus:outline-none"
        >
          <div className="w-6 h-6 rounded bg-blue-600/20 text-blue-400 flex items-center justify-center border border-blue-500/30">
            <Building2 className="w-3.5 h-3.5" />
          </div>
          <div className="flex flex-col text-left">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-slate-200 group-hover:text-white transition-colors">
                {activeTenant?.name || "Select Business"}
              </span>
              {tenants.length > 1 && (
                <ChevronDown className="w-3 h-3 text-slate-500 group-hover:text-slate-300" />
              )}
            </div>
            <span className="text-[10px] text-slate-500 font-medium font-mono">
              {activeTenant?.slug || "No Business Context"}
            </span>
          </div>
        </button>

        {/* Tenant Switcher Dropdown */}
        {showTenantMenu && tenants.length > 0 && (
          <div className="absolute top-full left-10 lg:left-0 mt-2 w-64 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl p-1.5 z-50 animate-in fade-in zoom-in-95 duration-100">
            <div className="px-3 py-2 border-b border-slate-800 mb-1">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Your Businesses ({tenants.length})
              </span>
            </div>
            <div className="space-y-0.5 max-h-60 overflow-y-auto">
              {tenants.map((tenant) => {
                const isActive = activeTenant?.id === tenant.id;
                return (
                  <button
                    key={tenant.id}
                    type="button"
                    onClick={() => handleSelectBusiness(tenant.id)}
                    className={`w-full text-left px-3 py-2 rounded-lg text-xs flex items-center justify-between transition-colors ${
                      isActive
                        ? "bg-blue-600/10 text-blue-400 font-medium"
                        : "text-slate-300 hover:bg-slate-800/80 hover:text-white"
                    }`}
                  >
                    <div className="flex flex-col">
                      <span className="font-semibold">{tenant.name}</span>
                      <span className="text-[10px] text-slate-500 font-mono">{tenant.slug}</span>
                    </div>
                    {isActive && <Check className="w-4 h-4 text-blue-400" />}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Right: Notifications & User Profile */}
      <div className="flex items-center gap-3">
        {/* Notification Bell */}
        <button
          type="button"
          aria-label="Notifications"
          className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent hover:border-slate-800 transition-all relative"
        >
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-blue-500 rounded-full ring-2 ring-slate-950" />
        </button>

        <div className="h-4 w-px bg-slate-800 mx-0.5" />

        {/* User Identity Profile Menu */}
        <div className="relative" ref={userMenuRef}>
          <button
            type="button"
            aria-label="User Profile Menu"
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-2.5 pl-1 cursor-pointer focus:outline-none group text-left"
          >
            <Avatar name={userNameDisplay} size="sm" />
            <div className="hidden md:flex flex-col text-left">
              <span className="text-xs font-medium text-slate-200 group-hover:text-white transition-colors leading-none">
                {userNameDisplay}
              </span>
              <span className="text-[10px] text-slate-500 mt-0.5 truncate max-w-[140px]">
                {user?.email || "Authenticated Owner"}
              </span>
            </div>
            <ChevronDown className="w-3 h-3 text-slate-500 group-hover:text-slate-300 hidden md:block" />
          </button>

          {/* User Menu Dropdown */}
          {showUserMenu && (
            <div className="absolute top-full right-0 mt-2 w-56 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl p-1.5 z-50 animate-in fade-in zoom-in-95 duration-100">
              <div className="px-3 py-2.5 border-b border-slate-800 mb-1">
                <p className="text-xs font-medium text-slate-200 truncate">{user?.email}</p>
                <p className="text-[10px] text-slate-500 mt-0.5 capitalize">
                  Active: {activeTenant?.name || "No Business Selected"}
                </p>
              </div>

              {tenants.length > 1 && (
                <button
                  type="button"
                  onClick={() => {
                    setShowUserMenu(false);
                    router.push("/select-tenant");
                  }}
                  className="w-full text-left px-3 py-2 rounded-lg text-xs text-slate-300 hover:bg-slate-800 hover:text-white flex items-center gap-2 transition-colors mb-0.5"
                >
                  <ArrowRightLeft className="w-3.5 h-3.5 text-slate-400" />
                  <span>Switch Business</span>
                </button>
              )}

              <button
                type="button"
                onClick={handleLogout}
                className="w-full text-left px-3 py-2 rounded-lg text-xs text-red-400 hover:bg-red-950/40 hover:text-red-300 flex items-center gap-2 transition-colors"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Sign Out</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

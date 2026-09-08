"use client";

import React, { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

const PUBLIC_ROUTES = ["/login"];

export const AuthGuard: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, activeTenant, isLoading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;

    const isPublic = PUBLIC_ROUTES.includes(pathname);

    if (!isAuthenticated && !isPublic) {
      router.replace("/login");
      return;
    }

    if (isAuthenticated) {
      if (!activeTenant && pathname !== "/select-tenant") {
        router.replace("/select-tenant");
        return;
      }

      if (activeTenant && (pathname === "/login" || pathname === "/select-tenant")) {
        router.replace("/");
        return;
      }
    }
  }, [isAuthenticated, activeTenant, isLoading, pathname, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#090d16] flex items-center justify-center text-slate-400">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-xs font-medium text-slate-400 tracking-wider">AI BOS Loading...</span>
        </div>
      </div>
    );
  }

  // Hide protected page content while redirecting
  const isPublic = PUBLIC_ROUTES.includes(pathname);
  if (!isAuthenticated && !isPublic) {
    return null;
  }

  if (isAuthenticated && !activeTenant && pathname !== "/select-tenant") {
    return null;
  }

  return <>{children}</>;
};

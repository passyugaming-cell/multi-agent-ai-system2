"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Building2, ArrowRight, Sparkles, AlertCircle } from "lucide-react";

export default function SelectTenantPage() {
  const { tenants, selectTenant, authError } = useAuth();
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null);
  const router = useRouter();

  const handleSelect = async (tenantId: string) => {
    setSelectedTenantId(tenantId);
    try {
      const { redirectTo } = await selectTenant(tenantId);
      router.push(redirectTo);
    } catch {
      setSelectedTenantId(null);
    }
  };

  return (
    <div className="min-h-screen w-full bg-[#090d16] flex items-center justify-center p-4 sm:p-6 lg:p-8">
      {/* Background glow */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-xl relative z-10 space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-600/10 border border-blue-500/20 text-blue-400 text-xs font-semibold mb-1">
            <Sparkles className="w-3.5 h-3.5" />
            <span>AI Business OS</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Select your business
          </h1>
          <p className="text-sm text-slate-400">
            Choose which business you want to manage.
          </p>
        </div>

        {authError && (
          <div className="p-3.5 rounded-lg bg-red-950/40 border border-red-800/60 text-red-300 text-xs flex items-center gap-2.5">
            <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
            <span>{authError}</span>
          </div>
        )}

        {/* Business Cards List */}
        <div className="space-y-3.5">
          {tenants.map((tenant) => {
            const isLoading = selectedTenantId === tenant.id;

            return (
              <Card
                key={tenant.id}
                className="bg-[#0b1120]/90 border-slate-800/90 hover:border-blue-500/50 transition-all p-5 backdrop-blur-md group"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="flex items-start gap-3.5">
                    <div className="w-10 h-10 rounded-xl bg-blue-600/15 border border-blue-500/30 text-blue-400 flex items-center justify-center shrink-0 mt-0.5 group-hover:scale-105 transition-transform">
                      <Building2 className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <h2 className="text-base font-semibold text-slate-100 group-hover:text-white transition-colors">
                          {tenant.name}
                        </h2>
                        <Badge variant="outline" className="text-[10px] uppercase font-mono py-0.5 px-1.5 border-slate-700 text-slate-400">
                          {tenant.lifecycle_state || "Active"}
                        </Badge>
                      </div>
                      <p className="text-xs text-slate-400 mt-1">
                        Business &bull; <span className="font-mono text-slate-500">{tenant.slug}</span>
                      </p>
                    </div>
                  </div>

                  <Button
                    onClick={() => handleSelect(tenant.id)}
                    disabled={isLoading || selectedTenantId !== null}
                    className="w-full sm:w-auto px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-medium text-xs rounded-lg shadow-md shadow-blue-600/10 transition-all flex items-center justify-center gap-2 shrink-0"
                  >
                    {isLoading ? (
                      <>
                        <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        <span>Opening...</span>
                      </>
                    ) : (
                      <>
                        <span>Open Business</span>
                        <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                      </>
                    )}
                  </Button>
                </div>
              </Card>
            );
          })}

          {tenants.length === 0 && (
            <Card className="bg-[#0b1120]/90 border-slate-800 p-8 text-center text-slate-400">
              <Building2 className="w-8 h-8 text-slate-600 mx-auto mb-2" />
              <p className="text-sm font-medium text-slate-300">No authorized businesses found.</p>
              <p className="text-xs text-slate-500 mt-1">
                Please contact support or your account administrator to assign business access.
              </p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

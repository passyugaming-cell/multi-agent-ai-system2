import React from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { ComingSoon } from "@/components/ui/ComingSoon";
import { Bot } from "lucide-react";

export default function AITeamPage() {
  return (
    <MainLayout>
      <div className="space-y-6">
        <div className="pb-2 border-b border-slate-800/60">
          <h1 className="text-2xl font-bold tracking-tight text-white">AI Team</h1>
          <p className="text-sm text-slate-400">
            Pusat agen specialist AI (Sales, Support, Client Manager, Data Manager, Analyst).
          </p>
        </div>

        <ComingSoon
          title="Modul AI Team"
          description="Fitur AI Team akan memvisualisasikan performa dan koordinasi dari 5 agent specialist AI BOS."
          icon={<Bot className="w-8 h-8 text-purple-400" />}
          badgeLabel="COMING SOON"
          status="coming_soon"
        />
      </div>
    </MainLayout>
  );
}

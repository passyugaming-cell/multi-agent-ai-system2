import React from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { ComingSoon } from "@/components/ui/ComingSoon";
import { Zap } from "lucide-react";

export default function AutomationPage() {
  return (
    <MainLayout>
      <div className="space-y-6">
        <div className="pb-2 border-b border-slate-800/60">
          <h1 className="text-2xl font-bold tracking-tight text-white">Automasi Workflow</h1>
          <p className="text-sm text-slate-400">
            Alur kerja otomatisasi bisnis, event bus, dan sistem persetujuan.
          </p>
        </div>

        <ComingSoon
          title="Modul Automasi Workflow"
          description="Fitur Automasi akan mengkonfigurasi trigger, event bus streams, dan workflow engine tanpa coding."
          icon={<Zap className="w-8 h-8 text-amber-400" />}
          badgeLabel="COMING SOON"
          status="coming_soon"
        />
      </div>
    </MainLayout>
  );
}

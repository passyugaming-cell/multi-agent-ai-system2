import React from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { ComingSoon } from "@/components/ui/ComingSoon";
import { BarChart3 } from "lucide-react";

export default function AnalyticsPage() {
  return (
    <MainLayout>
      <div className="space-y-6">
        <div className="pb-2 border-b border-slate-800/60">
          <h1 className="text-2xl font-bold tracking-tight text-white">Analytics & Intelligence</h1>
          <p className="text-sm text-slate-400">
            Laporan eksekutif, analisis tren, dan kalkulasi kesehatan bisnis.
          </p>
        </div>

        <ComingSoon
          title="Modul Business Analytics"
          description="Fitur Analytics akan menyajikan grafik performa penjualan, tren percakapan, dan laporan harian AI."
          icon={<BarChart3 className="w-8 h-8 text-emerald-400" />}
          badgeLabel="COMING SOON"
          status="coming_soon"
        />
      </div>
    </MainLayout>
  );
}

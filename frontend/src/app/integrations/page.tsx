import React from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { ComingSoon } from "@/components/ui/ComingSoon";
import { Layers } from "lucide-react";

export default function IntegrationsPage() {
  return (
    <MainLayout>
      <div className="space-y-6">
        <div className="pb-2 border-b border-slate-800/60">
          <h1 className="text-2xl font-bold tracking-tight text-white">Integrasi Platform</h1>
          <p className="text-sm text-slate-400">
            Konektor Google Sheets, Google Calendar, Midtrans, dan WhatsApp Cloud API.
          </p>
        </div>

        <ComingSoon
          title="Modul Universal Integrations"
          description="Fitur Integrations akan mengelola status koneksi dan otorisasi OAuth/API key platform eksternal."
          icon={<Layers className="w-8 h-8 text-cyan-400" />}
          badgeLabel="COMING SOON"
          status="coming_soon"
        />
      </div>
    </MainLayout>
  );
}

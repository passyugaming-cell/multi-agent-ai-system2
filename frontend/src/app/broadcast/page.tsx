import React from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { ComingSoon } from "@/components/ui/ComingSoon";
import { Radio } from "lucide-react";

export default function BroadcastPage() {
  return (
    <MainLayout>
      <div className="space-y-6">
        <div className="pb-2 border-b border-slate-800/60">
          <h1 className="text-2xl font-bold tracking-tight text-white">Broadcast</h1>
          <p className="text-sm text-slate-400">
            Kirim pesan massal terkonfirmasi dan kampanye tersegmen.
          </p>
        </div>

        <ComingSoon
          title="Modul Broadcast WhatsApp"
          description="Fitur Broadcast akan memungkinkan pengiriman pesan massal terjangkau ke ribuan pelanggan berlisensi."
          icon={<Radio className="w-8 h-8 text-blue-400" />}
          badgeLabel="COMING SOON"
          status="coming_soon"
        />
      </div>
    </MainLayout>
  );
}

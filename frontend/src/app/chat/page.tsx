import React from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { MessageSquare, Search, MessageCircleCode } from "lucide-react";

export default function ChatPage() {
  return (
    <MainLayout>
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-800/60">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h1 className="text-2xl font-bold tracking-tight text-white">Chat WhatsApp</h1>
              <Badge variant="default" size="sm">Active Module</Badge>
            </div>
            <p className="text-sm text-slate-400">
              Layanan inbox terpadu dan riwayat percakapan pelanggan via WhatsApp.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[600px]">
          {/* Conversation List Shell */}
          <Card variant="default" className="lg:col-span-1 flex flex-col p-4">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
              <span className="text-sm font-semibold text-slate-200">Inbox Chat</span>
              <Badge variant="secondary" size="sm">0 Chat</Badge>
            </div>

            <div className="relative mb-4">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Cari pesan atau kontak..."
                disabled
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-300 placeholder-slate-600 focus:outline-none cursor-not-allowed"
              />
            </div>

            <div className="flex-1 flex flex-col items-center justify-center p-6 text-center text-slate-500 border border-dashed border-slate-800/80 rounded-lg">
              <MessageCircleCode className="w-8 h-8 mb-2 text-slate-600" />
              <p className="text-xs font-medium text-slate-400 mb-1">Belum Ada Percakapan</p>
              <p className="text-[11px]">Pesan masuk dari pelanggan akan tampil secara otomatis di sini.</p>
            </div>
          </Card>

          {/* Active Chat Detail Shell */}
          <Card variant="default" className="lg:col-span-2 flex flex-col items-center justify-center p-8 text-center">
            <div className="w-16 h-16 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center mb-4 text-blue-400">
              <MessageSquare className="w-8 h-8" />
            </div>
            <h3 className="text-lg font-semibold text-slate-200 mb-1">Pratinjau Ruang Chat</h3>
            <p className="text-xs text-slate-400 max-w-sm mb-4">
              Pilih salah satu percakapan dari daftar di sebelah kiri untuk melihat pesan dan berinteraksi.
            </p>
            <Badge variant="outline" size="sm">WhatsApp Cloud API Ready</Badge>
          </Card>
        </div>
      </div>
    </MainLayout>
  );
}

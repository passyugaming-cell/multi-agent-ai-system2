import React from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Filter, ArrowUpDown, Inbox } from "lucide-react";

export default function OrdersPage() {
  return (
    <MainLayout>
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-800/60">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h1 className="text-2xl font-bold tracking-tight text-white">Pesanan</h1>
              <Badge variant="default" size="sm">Active Module</Badge>
            </div>
            <p className="text-sm text-slate-400">
              Daftar transaksi, status pembayaran, dan pesanan masuk.
            </p>
          </div>
        </div>

        <Card variant="default">
          <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
            <div>
              <CardTitle>Daftar Pesanan Terkini</CardTitle>
              <CardDescription>Seluruh data transaksi terdaftar</CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <button disabled className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-400 flex items-center gap-1.5 opacity-60 cursor-not-allowed">
                <Filter className="w-3.5 h-3.5" />
                <span>Filter</span>
              </button>
              <button disabled className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-400 flex items-center gap-1.5 opacity-60 cursor-not-allowed">
                <ArrowUpDown className="w-3.5 h-3.5" />
                <span>Urutkan</span>
              </button>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-slate-800/80 rounded-xl bg-slate-950/40">
              <div className="p-3 rounded-full bg-slate-900 border border-slate-800 text-slate-500 mb-3">
                <Inbox className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-semibold text-slate-300 mb-1">Belum Ada Pesanan Masuk</h3>
              <p className="text-xs text-slate-500 max-w-sm">
                Transaksi yang dibuat via WhatsApp atau sistem pembayaran akan secara otomatis tercatat di halaman ini.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </MainLayout>
  );
}

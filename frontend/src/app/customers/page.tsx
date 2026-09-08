import React from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Search, UserX } from "lucide-react";

export default function CustomersPage() {
  return (
    <MainLayout>
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-800/60">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h1 className="text-2xl font-bold tracking-tight text-white">Customer</h1>
              <Badge variant="default" size="sm">Active Module</Badge>
            </div>
            <p className="text-sm text-slate-400">
              Database kontak dan profil pelanggan bisnis Anda.
            </p>
          </div>
        </div>

        <Card variant="default">
          <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
            <div>
              <CardTitle>Direktori Pelanggan</CardTitle>
              <CardDescription>Semua kontak terdaftar di Universal Customer Store</CardDescription>
            </div>
            <div className="relative">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Cari nama atau telepon..."
                disabled
                className="bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-300 placeholder-slate-600 focus:outline-none cursor-not-allowed"
              />
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-slate-800/80 rounded-xl bg-slate-950/40">
              <div className="p-3 rounded-full bg-slate-900 border border-slate-800 text-slate-500 mb-3">
                <UserX className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-semibold text-slate-300 mb-1">Belum Ada Customer Terdaftar</h3>
              <p className="text-xs text-slate-500 max-w-sm">
                Setiap pelanggan baru yang menghubungi via WhatsApp akan secara otomatis dibuatkan profil pelanggan.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </MainLayout>
  );
}

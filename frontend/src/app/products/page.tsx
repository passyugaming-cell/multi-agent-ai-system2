import React from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Package, Tag, Layers, Layers3 } from "lucide-react";

export default function ProductsPage() {
  return (
    <MainLayout>
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-800/60">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h1 className="text-2xl font-bold tracking-tight text-white">Produk & Varian</h1>
              <Badge variant="success" size="sm">Active Feature</Badge>
            </div>
            <p className="text-sm text-slate-400">
              Kelola katalog produk, varian harga, dan ketersediaan stok bisnis.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card variant="glass" className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-400">Total Produk</span>
              <Package className="w-4 h-4 text-blue-400" />
            </div>
            <div className="text-xl font-bold text-white">0 Items</div>
          </Card>
          <Card variant="glass" className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-400">Varian Aktif</span>
              <Tag className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-xl font-bold text-white">0 Variants</div>
          </Card>
          <Card variant="glass" className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-400">Kategori</span>
              <Layers className="w-4 h-4 text-amber-400" />
            </div>
            <div className="text-xl font-bold text-white">0 Categories</div>
          </Card>
        </div>

        <Card variant="default">
          <CardHeader>
            <CardTitle>Katalog Produk Utama</CardTitle>
            <CardDescription>
              Modul produk ini aktif dan unlocked sebagai antarmuka manajemen inventory MVP.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-slate-800/80 rounded-xl bg-slate-950/40">
              <div className="p-3 rounded-full bg-slate-900 border border-slate-800 text-slate-500 mb-3">
                <Layers3 className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-semibold text-slate-300 mb-1">Katalog Masih Kosong</h3>
              <p className="text-xs text-slate-500 max-w-sm mb-4">
                Daftar produk dan varian item yang Anda tambahkan akan menjadi sumber data AI dalam menjawab pertanyaan harga dan stok.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </MainLayout>
  );
}

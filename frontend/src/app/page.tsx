import React from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { MessageSquare, ShoppingBag, Users, Package, ArrowUpRight, Activity } from "lucide-react";
import Link from "next/link";

export default function DashboardPage() {
  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Welcome Header Shell */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-800/60">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h1 className="text-2xl font-bold tracking-tight text-white">Dashboard Overview</h1>
              <Badge variant="default" size="sm">System Ready</Badge>
            </div>
            <p className="text-sm text-slate-400">
              Selamat datang di AI Business OS. Ringkasan aktivitas dan performa bisnis Anda.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800 flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-emerald-400" />
              <span>Status Multi-Tenant Active</span>
            </span>
          </div>
        </div>

        {/* Quick Shell Stat Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card variant="glass" className="p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Chat WhatsApp</span>
              <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400">
                <MessageSquare className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold text-white mb-1">Active Shell</div>
            <p className="text-xs text-slate-500">Koneksi WhatsApp Cloud API</p>
          </Card>

          <Card variant="glass" className="p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Pesanan</span>
              <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                <ShoppingBag className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold text-white mb-1">0 Orders</div>
            <p className="text-xs text-slate-500">Pemesanan realtime</p>
          </Card>

          <Card variant="glass" className="p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Customer</span>
              <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400">
                <Users className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold text-white mb-1">0 Contacts</div>
            <p className="text-xs text-slate-500">Database pelanggan</p>
          </Card>

          <Card variant="glass" className="p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Katalog Produk</span>
              <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400">
                <Package className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold text-white mb-1">Active</div>
            <p className="text-xs text-slate-500">Manajemen varian & stok</p>
          </Card>
        </div>

        {/* Navigation Shortcut Cards */}
        <Card variant="default">
          <CardHeader>
            <CardTitle>Fitur Utama MVP</CardTitle>
            <CardDescription>Akses cepat ke modul fungsional utama AI BOS</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <Link href="/chat" className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-slate-700 hover:bg-slate-850 transition-all group">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2.5 font-semibold text-slate-200 group-hover:text-blue-400 transition-colors">
                    <MessageSquare className="w-4 h-4 text-blue-400" />
                    <span>Chat WhatsApp</span>
                  </div>
                  <ArrowUpRight className="w-4 h-4 text-slate-500 group-hover:text-blue-400 transition-colors" />
                </div>
                <p className="text-xs text-slate-400">Layanan pesan terpusat & riwayat interaksi WhatsApp.</p>
              </Link>

              <Link href="/orders" className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-slate-700 hover:bg-slate-850 transition-all group">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2.5 font-semibold text-slate-200 group-hover:text-emerald-400 transition-colors">
                    <ShoppingBag className="w-4 h-4 text-emerald-400" />
                    <span>Pesanan</span>
                  </div>
                  <ArrowUpRight className="w-4 h-4 text-slate-500 group-hover:text-emerald-400 transition-colors" />
                </div>
                <p className="text-xs text-slate-400">Manajemen status transaksi dan transaksi pelanggan.</p>
              </Link>

              <Link href="/products" className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-slate-700 hover:bg-slate-850 transition-all group">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2.5 font-semibold text-slate-200 group-hover:text-amber-400 transition-colors">
                    <Package className="w-4 h-4 text-amber-400" />
                    <span>Produk & Varian</span>
                  </div>
                  <Badge variant="success" size="sm" className="text-[9px]">Unlocked</Badge>
                </div>
                <p className="text-xs text-slate-400">Kelola katalog produk, harga, dan ketersediaan stok.</p>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </MainLayout>
  );
}

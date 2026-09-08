"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { MainLayout } from "@/components/layout/MainLayout";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth-context";
import { apiGet, ApiError } from "@/lib/api";
import {
  Users,
  ShoppingBag,
  Package,
  MessageSquare,
  TrendingUp,
  ArrowUpRight,
  RefreshCw,
  AlertTriangle,
  Sparkles,
  Clock,
  CheckCircle2,
  ShieldCheck,
  Building,
} from "lucide-react";

interface CustomerItem {
  id: string;
  name?: string;
  phone?: string;
  email?: string;
  created_at?: string;
}

interface OrderItem {
  id: string;
  total_amount?: number | string;
  currency?: string;
  status?: string;
  created_at?: string;
}

interface ProductItem {
  id: string;
  name: string;
  price?: number | string;
  is_active?: boolean;
}

interface ConversationItem {
  id: string;
  status?: string;
  last_message_at?: string;
  unread_count?: number;
}

interface BusinessReadiness {
  ready?: boolean;
  readiness_status?: string;
  score?: number;
  percentage?: number;
}

interface FinancialData {
  total_revenue?: number;
  currency?: string;
  total_orders?: number;
}

export default function DashboardPage() {
  const { user, activeTenant } = useAuth();

  const [customers, setCustomers] = useState<CustomerItem[]>([]);
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [products, setProducts] = useState<ProductItem[]>([]);
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [readiness, setReadiness] = useState<BusinessReadiness | null>(null);
  const [financials, setFinancials] = useState<FinancialData | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadDashboardData = useCallback(async () => {
    if (!activeTenant) return;

    setIsLoading(true);
    setErrorMsg(null);

    try {
      const [
        customersRes,
        ordersRes,
        productsRes,
        conversationsRes,
        readinessRes,
        financialsRes,
      ] = await Promise.allSettled([
        apiGet<CustomerItem[]>("/customers"),
        apiGet<OrderItem[]>("/orders"),
        apiGet<ProductItem[]>("/products"),
        apiGet<ConversationItem[]>("/conversations"),
        apiGet<BusinessReadiness>("/business/readiness"),
        apiGet<FinancialData>("/analytics/financial"),
      ]);

      const failedEndpoints: string[] = [];

      if (customersRes.status === "fulfilled") {
        setCustomers(customersRes.value || []);
      } else {
        failedEndpoints.push("Customer");
      }

      if (ordersRes.status === "fulfilled") {
        setOrders(ordersRes.value || []);
      } else {
        failedEndpoints.push("Pesanan");
      }

      if (productsRes.status === "fulfilled") {
        setProducts(productsRes.value || []);
      } else {
        failedEndpoints.push("Produk");
      }

      if (conversationsRes.status === "fulfilled") {
        setConversations(conversationsRes.value || []);
      } else {
        failedEndpoints.push("Percakapan");
      }

      if (readinessRes.status === "fulfilled") {
        setReadiness(readinessRes.value);
      }

      if (financialsRes.status === "fulfilled") {
        setFinancials(financialsRes.value);
      }

      if (failedEndpoints.length > 0) {
        setErrorMsg(`Sebagian data (${failedEndpoints.join(", ")}) belum dapat dimuat. Menyajikan data yang tersedia.`);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg("Terjadi kesalahan sistem saat memuat data dashboard.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [activeTenant]);

  useEffect(() => {
    /* eslint-disable-next-line react-hooks/set-state-in-effect */
    loadDashboardData();
  }, [loadDashboardData]);

  const formatCurrency = (val?: number) => {
    if (val === undefined || val === null) return "Rp 0";
    return new Intl.NumberFormat("id-ID", {
      style: "currency",
      currency: "IDR",
      maximumFractionDigits: 0,
    }).format(val);
  };

  // Sort orders descending by created_at date for "Pesanan Terbaru" list
  const recentOrders = [...orders].sort((a, b) => {
    const timeA = a.created_at ? new Date(a.created_at).getTime() : 0;
    const timeB = b.created_at ? new Date(b.created_at).getTime() : 0;
    return timeB - timeA;
  }).slice(0, 5);

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Top Header & Tenant Info Banner */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap mb-1">
              <h1 className="text-2xl font-bold tracking-tight text-white">Dashboard Overview</h1>
              <Badge variant="secondary" size="sm" className="bg-blue-900/40 text-blue-300 border-blue-700/50">
                <Building className="w-3 h-3 mr-1" />
                {activeTenant?.name || "Business Context"}
              </Badge>
              {readiness?.readiness_status && (
                <Badge
                  variant={readiness.ready ? "success" : "warning"}
                  size="sm"
                  className="text-[10px] uppercase font-mono"
                >
                  Readiness: {readiness.readiness_status} ({readiness.percentage ?? readiness.score ?? 0}%)
                </Badge>
              )}
            </div>
            <p className="text-xs sm:text-sm text-slate-400">
              Pengelola operasional bisnis &bull; User:{" "}
              <span className="text-slate-200 font-medium">{user?.email || "Owner"}</span>
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={loadDashboardData}
              disabled={isLoading}
              className="text-xs bg-slate-900/80 border-slate-800 hover:border-slate-700 text-slate-300"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${isLoading ? "animate-spin text-blue-400" : ""}`} />
              <span>SINKRONKAN DATA</span>
            </Button>
          </div>
        </div>

        {/* Error Alert Banner */}
        {errorMsg && (
          <div className="p-4 rounded-xl bg-red-950/50 border border-red-800/80 text-red-200 text-xs sm:text-sm flex items-start justify-between gap-3 shadow-lg">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-red-300">Status Sinkronisasi Data</p>
                <p className="text-xs text-red-400 mt-0.5">{errorMsg}</p>
              </div>
            </div>
            <Button variant="danger" size="sm" onClick={loadDashboardData} className="shrink-0 text-xs">
              Coba Lagi
            </Button>
          </div>
        )}

        {/* Overview Metric Cards Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Total Customers */}
          <Card variant="glass" className="p-5 relative overflow-hidden group">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Total Customer
              </span>
              <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20">
                <Users className="w-4 h-4" />
              </div>
            </div>

            {isLoading ? (
              <div className="space-y-2">
                <div className="h-7 w-20 bg-slate-800/80 rounded animate-pulse" />
                <div className="h-3 w-32 bg-slate-800/60 rounded animate-pulse" />
              </div>
            ) : (
              <>
                <div className="text-2xl font-bold text-white mb-1">
                  {customers.length}
                </div>
                <p className="text-xs text-slate-500">
                  {customers.length === 0 ? "Belum ada customer terdaftar" : "Customer aktif terdata"}
                </p>
              </>
            )}
          </Card>

          {/* Total Orders */}
          <Card variant="glass" className="p-5 relative overflow-hidden group">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Total Pesanan
              </span>
              <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <ShoppingBag className="w-4 h-4" />
              </div>
            </div>

            {isLoading ? (
              <div className="space-y-2">
                <div className="h-7 w-20 bg-slate-800/80 rounded animate-pulse" />
                <div className="h-3 w-32 bg-slate-800/60 rounded animate-pulse" />
              </div>
            ) : (
              <>
                <div className="text-2xl font-bold text-white mb-1">
                  {orders.length}
                </div>
                <p className="text-xs text-slate-500">
                  {orders.length === 0 ? "Belum ada pesanan masuk" : "Transaksi tercatat di sistem"}
                </p>
              </>
            )}
          </Card>

          {/* Catalog Products */}
          <Card variant="glass" className="p-5 relative overflow-hidden group">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Katalog Produk
              </span>
              <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
                <Package className="w-4 h-4" />
              </div>
            </div>

            {isLoading ? (
              <div className="space-y-2">
                <div className="h-7 w-20 bg-slate-800/80 rounded animate-pulse" />
                <div className="h-3 w-32 bg-slate-800/60 rounded animate-pulse" />
              </div>
            ) : (
              <>
                <div className="text-2xl font-bold text-white mb-1">
                  {products.length}
                </div>
                <p className="text-xs text-slate-500">
                  {products.length === 0 ? "Belum ada produk dibuat" : "Produk dalam katalog"}
                </p>
              </>
            )}
          </Card>

          {/* Revenue / Financial Metric */}
          <Card variant="glass" className="p-5 relative overflow-hidden group">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Total Pendapatan
              </span>
              <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20">
                <TrendingUp className="w-4 h-4" />
              </div>
            </div>

            {isLoading ? (
              <div className="space-y-2">
                <div className="h-7 w-28 bg-slate-800/80 rounded animate-pulse" />
                <div className="h-3 w-32 bg-slate-800/60 rounded animate-pulse" />
              </div>
            ) : (
              <>
                <div className="text-2xl font-bold text-white mb-1">
                  {financials?.total_revenue !== undefined
                    ? formatCurrency(financials.total_revenue)
                    : "Rp 0"}
                </div>
                <p className="text-xs text-slate-500">
                  {financials?.total_revenue ? "Pendapatan kumulatif" : "Data belum tersedia"}
                </p>
              </>
            )}
          </Card>
        </div>

        {/* Section: Quick Actions & Navigation Shortcuts */}
        <Card variant="default">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-blue-400" />
                  <span>Aksi Cepat Modul MVP</span>
                </CardTitle>
                <CardDescription>Akses langsung ke area operasional bisnis</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <Link
                href="/chat"
                className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 hover:border-blue-500/50 hover:bg-slate-850 transition-all group"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 font-semibold text-slate-200 group-hover:text-blue-400 transition-colors text-sm">
                    <MessageSquare className="w-4 h-4 text-blue-400" />
                    <span>Chat WhatsApp</span>
                  </div>
                  <ArrowUpRight className="w-4 h-4 text-slate-500 group-hover:text-blue-400 transition-colors" />
                </div>
                <p className="text-xs text-slate-400">
                  {conversations.length > 0
                    ? `${conversations.length} percakapan aktif`
                    : "Inisialisasi pesan masuk"}
                </p>
              </Link>

              <Link
                href="/orders"
                className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 hover:border-emerald-500/50 hover:bg-slate-850 transition-all group"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 font-semibold text-slate-200 group-hover:text-emerald-400 transition-colors text-sm">
                    <ShoppingBag className="w-4 h-4 text-emerald-400" />
                    <span>Lihat Pesanan</span>
                  </div>
                  <ArrowUpRight className="w-4 h-4 text-slate-500 group-hover:text-emerald-400 transition-colors" />
                </div>
                <p className="text-xs text-slate-400">
                  {orders.length > 0 ? `${orders.length} pesanan terdata` : "Kelola transaksi & status"}
                </p>
              </Link>

              <Link
                href="/customers"
                className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 hover:border-purple-500/50 hover:bg-slate-850 transition-all group"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 font-semibold text-slate-200 group-hover:text-purple-400 transition-colors text-sm">
                    <Users className="w-4 h-4 text-purple-400" />
                    <span>Lihat Customer</span>
                  </div>
                  <ArrowUpRight className="w-4 h-4 text-slate-500 group-hover:text-purple-400 transition-colors" />
                </div>
                <p className="text-xs text-slate-400">
                  {customers.length > 0 ? `${customers.length} kontak tersimpan` : "Direktori & histori customer"}
                </p>
              </Link>

              <Link
                href="/products"
                className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 hover:border-amber-500/50 hover:bg-slate-850 transition-all group"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 font-semibold text-slate-200 group-hover:text-amber-400 transition-colors text-sm">
                    <Package className="w-4 h-4 text-amber-400" />
                    <span>Kelola Produk</span>
                  </div>
                  <ArrowUpRight className="w-4 h-4 text-slate-500 group-hover:text-amber-400 transition-colors" />
                </div>
                <p className="text-xs text-slate-400">
                  {products.length > 0 ? `${products.length} item aktif` : "Katalog & varian harga"}
                </p>
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* Section: Recent Activity / Transaction Status */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Recent Orders List / Empty State */}
          <Card variant="default">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <ShoppingBag className="w-4 h-4 text-emerald-400" />
                  <span>Pesanan Terbaru</span>
                </CardTitle>
                <Link
                  href="/orders"
                  className="text-xs text-blue-400 hover:text-blue-300 transition-colors font-medium flex items-center gap-1"
                >
                  <span>Lihat Semua</span>
                  <ArrowUpRight className="w-3 h-3" />
                </Link>
              </div>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-12 bg-slate-900/60 rounded-lg animate-pulse" />
                  ))}
                </div>
              ) : recentOrders.length > 0 ? (
                <div className="space-y-2.5">
                  {recentOrders.map((order) => (
                    <div
                      key={order.id}
                      className="p-3 rounded-lg bg-slate-900/60 border border-slate-800/80 flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded bg-emerald-500/10 text-emerald-400">
                          <ShoppingBag className="w-3.5 h-3.5" />
                        </div>
                        <div>
                          <p className="font-semibold text-slate-200">
                            Pesanan #{order.id.substring(0, 8)}
                          </p>
                          <p className="text-[10px] text-slate-500">
                            {order.created_at
                              ? new Date(order.created_at).toLocaleDateString("id-ID")
                              : "Transaksi Baru"}
                          </p>
                        </div>
                      </div>

                      <div className="text-right">
                        <p className="font-semibold text-slate-100">
                          {formatCurrency(
                            typeof order.total_amount === "number"
                              ? order.total_amount
                              : Number(order.total_amount || 0)
                          )}
                        </p>
                        <Badge
                          variant="outline"
                          size="sm"
                          className="text-[9px] uppercase border-slate-700 text-slate-400 mt-0.5"
                        >
                          {order.status || "PENDING"}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-8 text-center space-y-2">
                  <Clock className="w-8 h-8 text-slate-600 mx-auto" />
                  <p className="text-xs font-semibold text-slate-300">Belum ada pesanan terbaru</p>
                  <p className="text-[11px] text-slate-500 max-w-xs mx-auto">
                    Pesanan baru yang diterima melalui WhatsApp atau sistem akan ditampilkan di sini.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* System Status & Business Health */}
          <Card variant="default">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-blue-400" />
                <span>Kesiapan & Proteksi Bisnis</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400 font-medium">Status Integrasi Tenant</span>
                  <Badge variant={activeTenant ? "success" : "danger"} size="sm">
                    {activeTenant ? "Aktif & Terhubung" : "Tidak Terhubung"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400 font-medium">Tenant ID</span>
                  <span className="font-mono text-[11px] text-slate-300 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                    {activeTenant?.id || "N/A"}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400 font-medium">Otorisasi Sesi JWT</span>
                  <span className="text-emerald-400 font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Terverifikasi Server
                  </span>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-blue-950/20 border border-blue-900/40 space-y-1.5">
                <p className="text-xs font-semibold text-blue-300 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-blue-400" />
                  AI BOS Universal Core
                </p>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Isolasi data bisnis dan akses role RBAC terintegrasi secara ketat di sisi backend. Perubahan konteks bisnis dikonfirmasi melalui token JWT terenkripsi.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </MainLayout>
  );
}

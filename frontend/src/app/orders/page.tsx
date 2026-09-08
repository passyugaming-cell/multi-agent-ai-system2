"use client";

import React, { useEffect, useState, useCallback } from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth-context";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import {
  ShoppingBag,
  Plus,
  RefreshCw,
  AlertTriangle,
  Search,
  Inbox,
  X,
  CheckCircle,
  User,
  Trash2,
} from "lucide-react";

interface CustomerItem {
  id: string;
  name?: string | null;
  phone?: string | null;
  email?: string | null;
}

interface ProductItem {
  id: string;
  name: string;
  price: number;
  stock: number;
  unit?: string | null;
}

interface OrderItemResponse {
  id: string;
  product_id?: string | null;
  product_name_snapshot: string;
  unit_price: number;
  quantity: number;
  subtotal: number;
}

interface OrderItem {
  id: string;
  tenant_id: string;
  customer_id: string;
  status: string;
  subtotal: number;
  total: number;
  currency: string;
  items: OrderItemResponse[];
  created_at: string;
}

interface OrderFormLine {
  product_id: string;
  quantity: number;
}

export default function OrdersPage() {
  const { activeTenant } = useAuth();

  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [customers, setCustomers] = useState<CustomerItem[]>([]);
  const [products, setProducts] = useState<ProductItem[]>([]);

  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Modal & Form State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [selectedCustomerId, setSelectedCustomerId] = useState<string>("");
  const [orderLines, setOrderLines] = useState<OrderFormLine[]>([
    { product_id: "", quantity: 1 },
  ]);

  const loadData = useCallback(async () => {
    if (!activeTenant) return;

    setIsLoading(true);
    setErrorMsg(null);

    try {
      const [ordersRes, customersRes, productsRes] = await Promise.all([
        apiGet<OrderItem[]>("/orders"),
        apiGet<CustomerItem[]>("/customers"),
        apiGet<ProductItem[]>("/products"),
      ]);

      setOrders(ordersRes || []);
      setCustomers(customersRes || []);
      setProducts(productsRes || []);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg("Gagal memuat data pesanan.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [activeTenant]);

  useEffect(() => {
    /* eslint-disable-next-line react-hooks/set-state-in-effect */
    loadData();
  }, [loadData]);

  const handleAddLine = () => {
    setOrderLines([...orderLines, { product_id: "", quantity: 1 }]);
  };

  const handleRemoveLine = (index: number) => {
    if (orderLines.length <= 1) return;
    setOrderLines(orderLines.filter((_, i) => i !== index));
  };

  const handleLineChange = (index: number, field: "product_id" | "quantity", value: string | number) => {
    const updated = [...orderLines];
    if (field === "product_id") {
      updated[index].product_id = String(value);
    } else {
      updated[index].quantity = Math.max(1, Number(value) || 1);
    }
    setOrderLines(updated);
  };

  const handleCreateOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!selectedCustomerId) {
      setFormError("Silakan pilih customer terlebih dahulu. Jika belum ada, buat customer baru di menu Customer.");
      return;
    }

    const validItems = orderLines.filter((l) => l.product_id.trim() !== "");
    if (validItems.length === 0) {
      setFormError("Pilih minimal 1 produk untuk pesanan.");
      return;
    }

    setIsSubmitting(true);

    try {
      const payload = {
        customer_id: selectedCustomerId,
        currency: "IDR",
        items: validItems.map((item) => ({
          product_id: item.product_id,
          quantity: item.quantity,
        })),
      };

      await apiPost<OrderItem>("/orders", payload);

      setSuccessMsg("Pesanan baru berhasil dibuat.");
      setIsModalOpen(false);
      setSelectedCustomerId("");
      setOrderLines([{ product_id: "", quantity: 1 }]);
      loadData();

      setTimeout(() => setSuccessMsg(null), 5000);
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.message);
      } else {
        setFormError("Gagal membuat pesanan. Silakan periksa kembali data masukan.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat("id-ID", {
      style: "currency",
      currency: "IDR",
      maximumFractionDigits: 0,
    }).format(val);
  };

  const getCustomerName = (customerId: string) => {
    const found = customers.find((c) => c.id === customerId);
    if (!found) return `Customer #${customerId.substring(0, 8)}`;
    return found.name || found.phone || found.email || `Customer #${customerId.substring(0, 8)}`;
  };

  const filteredOrders = orders.filter((o) => {
    const q = searchQuery.toLowerCase();
    const orderIdMatch = o.id.toLowerCase().includes(q);
    const customerMatch = getCustomerName(o.customer_id).toLowerCase().includes(q);
    const statusMatch = o.status.toLowerCase().includes(q);
    return orderIdMatch || customerMatch || statusMatch;
  });

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Header */}
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

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={loadData}
              disabled={isLoading}
              className="text-xs bg-slate-900/80 border-slate-800 text-slate-300"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${isLoading ? "animate-spin text-blue-400" : ""}`} />
              <span>Refresh</span>
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setFormError(null);
                setIsModalOpen(true);
              }}
              className="text-xs bg-blue-600 hover:bg-blue-500 text-white font-medium"
            >
              <Plus className="w-4 h-4 mr-1.5" />
              <span>Buat Pesanan</span>
            </Button>
          </div>
        </div>

        {/* Notifications */}
        {successMsg && (
          <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-800/80 text-emerald-200 text-sm flex items-center justify-between shadow-lg">
            <div className="flex items-center gap-2.5">
              <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0" />
              <span>{successMsg}</span>
            </div>
            <button onClick={() => setSuccessMsg(null)} className="text-emerald-400 hover:text-emerald-200">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {errorMsg && (
          <div className="p-4 rounded-xl bg-red-950/50 border border-red-800/80 text-red-200 text-sm flex items-center justify-between shadow-lg">
            <div className="flex items-center gap-2.5">
              <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
              <span>{errorMsg}</span>
            </div>
            <Button variant="danger" size="sm" onClick={loadData} className="text-xs">
              Coba Lagi
            </Button>
          </div>
        )}

        {/* Orders Card */}
        <Card variant="default">
          <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
            <div>
              <CardTitle>Daftar Pesanan Terkini</CardTitle>
              <CardDescription>
                {orders.length} total pesanan terdaftar di sistem
              </CardDescription>
            </div>
            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Cari ID pesanan, customer, status..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            {isLoading ? (
              <div className="space-y-3 py-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-12 bg-slate-900/60 rounded-lg animate-pulse" />
                ))}
              </div>
            ) : filteredOrders.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-slate-300">
                  <thead className="bg-slate-950 text-slate-400 uppercase font-mono text-[10px] tracking-wider border-b border-slate-800">
                    <tr>
                      <th className="px-4 py-3">ID Pesanan</th>
                      <th className="px-4 py-3">Customer</th>
                      <th className="px-4 py-3">Jumlah Item</th>
                      <th className="px-4 py-3">Total Transaksi</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Tanggal</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {filteredOrders.map((o) => (
                      <tr key={o.id} className="hover:bg-slate-900/40 transition-colors">
                        <td className="px-4 py-3.5 font-mono text-slate-300 font-medium">
                          #{o.id.substring(0, 8)}
                        </td>
                        <td className="px-4 py-3.5 font-medium text-white flex items-center gap-2">
                          <User className="w-3.5 h-3.5 text-purple-400" />
                          <span>{getCustomerName(o.customer_id)}</span>
                        </td>
                        <td className="px-4 py-3.5 text-slate-400 font-mono">
                          {o.items ? o.items.length : 0} item
                        </td>
                        <td className="px-4 py-3.5 font-semibold text-emerald-400 font-mono">
                          {formatCurrency(Number(o.total))}
                        </td>
                        <td className="px-4 py-3.5">
                          <Badge variant="outline" size="sm" className="text-[9px] uppercase border-slate-700 text-slate-300">
                            {o.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3.5 text-slate-400">
                          {o.created_at ? new Date(o.created_at).toLocaleDateString("id-ID") : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-slate-800/80 rounded-xl bg-slate-950/40">
                <div className="p-3 rounded-full bg-slate-900 border border-slate-800 text-slate-500 mb-3">
                  <Inbox className="w-6 h-6" />
                </div>
                <h3 className="text-sm font-semibold text-slate-300 mb-1">
                  {searchQuery ? "Tidak ada pesanan sesuai pencarian" : "Belum Ada Pesanan Masuk"}
                </h3>
                <p className="text-xs text-slate-500 max-w-sm mb-4">
                  {searchQuery
                    ? "Coba gunakan kata kunci pencarian yang lain."
                    : "Transaksi yang dibuat secara manual atau via WhatsApp akan secara otomatis tercatat di halaman ini."}
                </p>
                {!searchQuery && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      setFormError(null);
                      setIsModalOpen(true);
                    }}
                    className="text-xs bg-blue-600 hover:bg-blue-500 text-white"
                  >
                    <Plus className="w-4 h-4 mr-1.5" />
                    <span>Buat Pesanan Pertama</span>
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Modal Create Order */}
        {isModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-lg overflow-hidden shadow-2xl">
              <div className="flex items-center justify-between p-4 border-b border-slate-800">
                <h2 className="text-base font-semibold text-white flex items-center gap-2">
                  <ShoppingBag className="w-4 h-4 text-emerald-400" />
                  <span>Buat Pesanan Baru</span>
                </h2>
                <button
                  onClick={() => setIsModalOpen(false)}
                  className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleCreateOrder} className="p-4 space-y-4 max-h-[80vh] overflow-y-auto">
                {formError && (
                  <div className="p-3 rounded-lg bg-red-950/50 border border-red-800/80 text-red-300 text-xs flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
                    <span>{formError}</span>
                  </div>
                )}

                {/* Customer Selection */}
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Pilih Customer <span className="text-red-400">*</span>
                  </label>
                  <select
                    required
                    value={selectedCustomerId}
                    onChange={(e) => setSelectedCustomerId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                  >
                    <option value="">-- Pilih Customer --</option>
                    {customers.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name || c.phone || c.email || c.id} {c.phone ? `(${c.phone})` : ""}
                      </option>
                    ))}
                  </select>
                  {customers.length === 0 && (
                    <p className="text-[11px] text-amber-400 mt-1">
                      Belum ada customer terdaftar. Silakan buat customer di halaman Customer terlebih dahulu.
                    </p>
                  )}
                </div>

                {/* Order Items */}
                <div className="space-y-3 pt-2">
                  <div className="flex items-center justify-between">
                    <label className="block text-xs font-medium text-slate-300">
                      Item Pesanan & Kuantitas <span className="text-red-400">*</span>
                    </label>
                    <button
                      type="button"
                      onClick={handleAddLine}
                      className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 font-medium"
                    >
                      <Plus className="w-3 h-3" />
                      <span>Tambah Item</span>
                    </button>
                  </div>

                  {orderLines.map((line, idx) => (
                    <div key={idx} className="flex items-center gap-2 bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                      <div className="flex-1">
                        <select
                          required
                          value={line.product_id}
                          onChange={(e) => handleLineChange(idx, "product_id", e.target.value)}
                          className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                        >
                          <option value="">-- Pilih Produk --</option>
                          {products.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.name} - {formatCurrency(Number(p.price))} (Stok: {p.stock})
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="w-20">
                        <input
                          type="number"
                          min="1"
                          required
                          value={line.quantity}
                          onChange={(e) => handleLineChange(idx, "quantity", e.target.value)}
                          className="w-full bg-slate-900 border border-slate-800 rounded px-2 py-1.5 text-xs text-white text-center focus:outline-none focus:border-blue-500 font-mono"
                        />
                      </div>

                      {orderLines.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveLine(idx)}
                          className="p-1.5 text-red-400 hover:text-red-300 hover:bg-red-950/40 rounded transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  ))}

                  {products.length === 0 && (
                    <p className="text-[11px] text-amber-400">
                      Belum ada produk di katalog. Silakan tambah produk di halaman Produk terlebih dahulu.
                    </p>
                  )}
                </div>

                <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setIsModalOpen(false)}
                    disabled={isSubmitting}
                    className="text-xs bg-slate-950 border-slate-800 text-slate-300"
                  >
                    Batal
                  </Button>
                  <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    disabled={isSubmitting || customers.length === 0 || products.length === 0}
                    className="text-xs bg-blue-600 hover:bg-blue-500 text-white"
                  >
                    {isSubmitting ? "Memproses..." : "Simpan Pesanan"}
                  </Button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </MainLayout>
  );
}

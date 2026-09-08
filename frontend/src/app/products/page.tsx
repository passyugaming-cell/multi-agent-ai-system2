"use client";

import React, { useEffect, useState, useCallback } from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth-context";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import {
  Package,
  Tag,
  Layers,
  Layers3,
  Plus,
  RefreshCw,
  AlertTriangle,
  Search,
  X,
  CheckCircle,
  DollarSign,
} from "lucide-react";

interface ProductVariantResponse {
  id: string;
  name: string;
  sku?: string | null;
  price_override?: number | null;
  stock: number;
  is_active: boolean;
}

interface ProductItem {
  id: string;
  tenant_id: string;
  name: string;
  type: string;
  description?: string | null;
  sku?: string | null;
  category?: string | null;
  price: number;
  currency: string;
  stock: number;
  stock_status?: string | null;
  unit?: string | null;
  is_active: boolean;
  variants?: ProductVariantResponse[];
  created_at: string;
}

export default function ProductsPage() {
  const { activeTenant } = useAuth();

  const [products, setProducts] = useState<ProductItem[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Modal & Form State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    name: "",
    type: "PRODUCT",
    category: "",
    price: "",
    stock: "",
    unit: "pcs",
    sku: "",
    description: "",
  });

  const loadProducts = useCallback(async () => {
    if (!activeTenant) return;

    setIsLoading(true);
    setErrorMsg(null);

    try {
      const data = await apiGet<ProductItem[]>("/products");
      setProducts(data || []);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg("Gagal memuat katalog produk.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [activeTenant]);

  useEffect(() => {
    /* eslint-disable-next-line react-hooks/set-state-in-effect */
    loadProducts();
  }, [loadProducts]);

  const handleCreateProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!formData.name.trim()) {
      setFormError("Nama produk wajib diisi.");
      return;
    }

    const priceNum = parseFloat(formData.price);
    if (isNaN(priceNum) || priceNum < 0) {
      setFormError("Harga produk harus berupa angka bernilai 0 atau lebih.");
      return;
    }

    const stockNum = parseInt(formData.stock || "0", 10);
    if (isNaN(stockNum) || stockNum < 0) {
      setFormError("Jumlah stok harus berupa angka bulat 0 atau lebih.");
      return;
    }

    setIsSubmitting(true);

    try {
      const payload: Record<string, unknown> = {
        name: formData.name.trim(),
        type: formData.type,
        price: priceNum,
        currency: "IDR",
        stock: stockNum,
        unit: formData.unit.trim() || "pcs",
        stock_status: stockNum > 0 ? "IN_STOCK" : "OUT_OF_STOCK",
        is_active: true,
      };

      if (formData.category.trim()) payload.category = formData.category.trim();
      if (formData.sku.trim()) payload.sku = formData.sku.trim();
      if (formData.description.trim()) payload.description = formData.description.trim();

      await apiPost<ProductItem>("/products", payload);

      setSuccessMsg(`Produk "${formData.name.trim()}" berhasil ditambahkan ke katalog.`);
      setIsModalOpen(false);
      setFormData({
        name: "",
        type: "PRODUCT",
        category: "",
        price: "",
        stock: "",
        unit: "pcs",
        sku: "",
        description: "",
      });
      loadProducts();

      setTimeout(() => setSuccessMsg(null), 5000);
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.message);
      } else {
        setFormError("Gagal menambahkan produk. Silakan coba lagi.");
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

  // Metrics calculation
  const totalProductsCount = products.length;
  const activeVariantsCount = products.reduce((acc, p) => acc + (p.variants ? p.variants.filter((v) => v.is_active).length : 0), 0);
  const uniqueCategoriesCount = new Set(products.map((p) => p.category).filter(Boolean)).size;

  const filteredProducts = products.filter((p) => {
    const q = searchQuery.toLowerCase();
    const nameMatch = p.name ? p.name.toLowerCase().includes(q) : false;
    const catMatch = p.category ? p.category.toLowerCase().includes(q) : false;
    const skuMatch = p.sku ? p.sku.toLowerCase().includes(q) : false;
    return nameMatch || catMatch || skuMatch;
  });

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Header */}
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

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={loadProducts}
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
              <span>Tambah Produk</span>
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
            <Button variant="danger" size="sm" onClick={loadProducts} className="text-xs">
              Coba Lagi
            </Button>
          </div>
        )}

        {/* Dynamic Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card variant="glass" className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-400">Total Produk</span>
              <Package className="w-4 h-4 text-blue-400" />
            </div>
            <div className="text-xl font-bold text-white">{totalProductsCount} Items</div>
          </Card>
          <Card variant="glass" className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-400">Varian Aktif</span>
              <Tag className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-xl font-bold text-white">{activeVariantsCount} Variants</div>
          </Card>
          <Card variant="glass" className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-400">Kategori</span>
              <Layers className="w-4 h-4 text-amber-400" />
            </div>
            <div className="text-xl font-bold text-white">{uniqueCategoriesCount} Categories</div>
          </Card>
        </div>

        {/* Product List Card */}
        <Card variant="default">
          <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
            <div>
              <CardTitle>Katalog Produk Utama</CardTitle>
              <CardDescription>
                Data katalog produk aktif untuk informasi harga dan ketersediaan AI
              </CardDescription>
            </div>
            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Cari produk, kategori, SKU..."
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
            ) : filteredProducts.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-slate-300">
                  <thead className="bg-slate-950 text-slate-400 uppercase font-mono text-[10px] tracking-wider border-b border-slate-800">
                    <tr>
                      <th className="px-4 py-3">Nama Produk</th>
                      <th className="px-4 py-3">Tipe</th>
                      <th className="px-4 py-3">Kategori</th>
                      <th className="px-4 py-3">Harga</th>
                      <th className="px-4 py-3">Stok</th>
                      <th className="px-4 py-3">SKU</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {filteredProducts.map((p) => (
                      <tr key={p.id} className="hover:bg-slate-900/40 transition-colors">
                        <td className="px-4 py-3.5 font-medium text-white flex items-center gap-2">
                          <div className="p-1.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                            <Package className="w-3.5 h-3.5" />
                          </div>
                          <div>
                            <p>{p.name}</p>
                            {p.description && (
                              <p className="text-[11px] text-slate-500 truncate max-w-xs">{p.description}</p>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3.5">
                          <Badge variant="outline" size="sm" className="text-[9px] uppercase border-slate-700 text-slate-400">
                            {p.type}
                          </Badge>
                        </td>
                        <td className="px-4 py-3.5 text-slate-300">
                          {p.category || "-"}
                        </td>
                        <td className="px-4 py-3.5 font-semibold text-emerald-400 font-mono">
                          {formatCurrency(Number(p.price))}
                        </td>
                        <td className="px-4 py-3.5">
                          <span
                            className={`font-mono px-2 py-0.5 rounded text-[11px] ${
                              p.stock > 0
                                ? "bg-emerald-950/60 text-emerald-300 border border-emerald-800/60"
                                : "bg-red-950/60 text-red-300 border border-red-800/60"
                            }`}
                          >
                            {p.stock} {p.unit || "pcs"}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 text-slate-500 font-mono text-[11px]">
                          {p.sku || "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-slate-800/80 rounded-xl bg-slate-950/40">
                <div className="p-3 rounded-full bg-slate-900 border border-slate-800 text-slate-500 mb-3">
                  <Layers3 className="w-6 h-6" />
                </div>
                <h3 className="text-sm font-semibold text-slate-300 mb-1">
                  {searchQuery ? "Tidak ada produk sesuai pencarian" : "Katalog Masih Kosong"}
                </h3>
                <p className="text-xs text-slate-500 max-w-sm mb-4">
                  {searchQuery
                    ? "Coba sesuaikan kata kunci pencarian."
                    : "Daftar produk dan varian item yang Anda tambahkan akan menjadi sumber data AI dalam menjawab pertanyaan harga dan stok."}
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
                    <span>Tambah Produk Pertama</span>
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Modal Create Product */}
        {isModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-lg overflow-hidden shadow-2xl">
              <div className="flex items-center justify-between p-4 border-b border-slate-800">
                <h2 className="text-base font-semibold text-white flex items-center gap-2">
                  <Package className="w-4 h-4 text-blue-400" />
                  <span>Tambah Produk Baru</span>
                </h2>
                <button
                  onClick={() => setIsModalOpen(false)}
                  className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleCreateProduct} className="p-4 space-y-4 max-h-[80vh] overflow-y-auto">
                {formError && (
                  <div className="p-3 rounded-lg bg-red-950/50 border border-red-800/80 text-red-300 text-xs flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
                    <span>{formError}</span>
                  </div>
                )}

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Nama Produk <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="Contoh: Kopi Susu Aren 250ml"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Tipe Produk
                    </label>
                    <select
                      value={formData.type}
                      onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                    >
                      <option value="PRODUCT">Produk Fisik (PRODUCT)</option>
                      <option value="SERVICE">Layanan / Jasa (SERVICE)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Kategori
                    </label>
                    <input
                      type="text"
                      placeholder="Contoh: Minuman"
                      value={formData.category}
                      onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Harga (IDR) <span className="text-red-400">*</span>
                    </label>
                    <div className="relative">
                      <DollarSign className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
                      <input
                        type="number"
                        min="0"
                        step="1000"
                        required
                        placeholder="25000"
                        value={formData.price}
                        onChange={(e) => setFormData({ ...formData, price: e.target.value })}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-2 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500 font-mono"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Stok
                    </label>
                    <input
                      type="number"
                      min="0"
                      placeholder="50"
                      value={formData.stock}
                      onChange={(e) => setFormData({ ...formData, stock: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500 font-mono"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Satuan
                    </label>
                    <input
                      type="text"
                      placeholder="pcs, botol, dll"
                      value={formData.unit}
                      onChange={(e) => setFormData({ ...formData, unit: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Kode SKU (Opsional)
                  </label>
                  <input
                    type="text"
                    placeholder="Contoh: KSA-250"
                    value={formData.sku}
                    onChange={(e) => setFormData({ ...formData, sku: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500 font-mono"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Deskripsi Produk (Opsional)
                  </label>
                  <textarea
                    rows={2}
                    placeholder="Deskripsi singkat produk..."
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500 resize-none"
                  />
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
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
                    disabled={isSubmitting}
                    className="text-xs bg-blue-600 hover:bg-blue-500 text-white"
                  >
                    {isSubmitting ? "Menyimpan..." : "Simpan Produk"}
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

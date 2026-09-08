"use client";

import React, { useEffect, useState, useCallback } from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth-context";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import { Search, UserX, Plus, RefreshCw, AlertTriangle, User, Phone, Mail, X, CheckCircle } from "lucide-react";

interface CustomerItem {
  id: string;
  tenant_id: string;
  name?: string | null;
  phone?: string | null;
  email?: string | null;
  external_id?: string | null;
  created_at: string;
}

export default function CustomersPage() {
  const { activeTenant } = useAuth();

  const [customers, setCustomers] = useState<CustomerItem[]>([]);
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
    phone: "",
    email: "",
  });

  const loadCustomers = useCallback(async () => {
    if (!activeTenant) return;

    setIsLoading(true);
    setErrorMsg(null);

    try {
      const data = await apiGet<CustomerItem[]>("/customers");
      setCustomers(data || []);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg("Gagal memuat daftar pelanggan.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [activeTenant]);

  useEffect(() => {
    /* eslint-disable-next-line react-hooks/set-state-in-effect */
    loadCustomers();
  }, [loadCustomers]);

  const handleCreateCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    // Validation: at least name or phone or email must be provided
    if (!formData.name.trim() && !formData.phone.trim() && !formData.email.trim()) {
      setFormError("Setidaknya isi salah satu: Nama, Nomor Telepon, atau Email.");
      return;
    }

    setIsSubmitting(true);

    try {
      const payload: Record<string, string> = {};
      if (formData.name.trim()) payload.name = formData.name.trim();
      if (formData.phone.trim()) payload.phone = formData.phone.trim();
      if (formData.email.trim()) payload.email = formData.email.trim();

      await apiPost<CustomerItem>("/customers", payload);

      setSuccessMsg(`Pelanggan "${formData.name.trim() || formData.phone.trim() || formData.email.trim()}" berhasil ditambahkan.`);
      setIsModalOpen(false);
      setFormData({ name: "", phone: "", email: "" });
      loadCustomers();

      setTimeout(() => setSuccessMsg(null), 5000);
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.message);
      } else {
        setFormError("Gagal menambahkan pelanggan. Silakan coba lagi.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredCustomers = customers.filter((c) => {
    const q = searchQuery.toLowerCase();
    const nameMatch = c.name ? c.name.toLowerCase().includes(q) : false;
    const phoneMatch = c.phone ? c.phone.toLowerCase().includes(q) : false;
    const emailMatch = c.email ? c.email.toLowerCase().includes(q) : false;
    return nameMatch || phoneMatch || emailMatch;
  });

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Header */}
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

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={loadCustomers}
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
              <span>Tambah Customer</span>
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
            <Button variant="danger" size="sm" onClick={loadCustomers} className="text-xs">
              Coba Lagi
            </Button>
          </div>
        )}

        {/* Main Content Card */}
        <Card variant="default">
          <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
            <div>
              <CardTitle>Direktori Pelanggan</CardTitle>
              <CardDescription>
                {customers.length} kontak terdaftar di Universal Customer Store
              </CardDescription>
            </div>
            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Cari nama, telepon, email..."
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
            ) : filteredCustomers.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-slate-300">
                  <thead className="bg-slate-950 text-slate-400 uppercase font-mono text-[10px] tracking-wider border-b border-slate-800">
                    <tr>
                      <th className="px-4 py-3">Nama</th>
                      <th className="px-4 py-3">No. HP / WhatsApp</th>
                      <th className="px-4 py-3">Email</th>
                      <th className="px-4 py-3">ID Pelanggan</th>
                      <th className="px-4 py-3">Terdaftar</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {filteredCustomers.map((c) => (
                      <tr key={c.id} className="hover:bg-slate-900/40 transition-colors">
                        <td className="px-4 py-3.5 font-medium text-white flex items-center gap-2">
                          <div className="p-1.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">
                            <User className="w-3.5 h-3.5" />
                          </div>
                          <span>{c.name || "Tanpa Nama"}</span>
                        </td>
                        <td className="px-4 py-3.5 text-slate-300 font-mono">
                          {c.phone || "-"}
                        </td>
                        <td className="px-4 py-3.5 text-slate-400">
                          {c.email || "-"}
                        </td>
                        <td className="px-4 py-3.5 text-slate-500 font-mono text-[11px]">
                          {c.id.substring(0, 8)}...
                        </td>
                        <td className="px-4 py-3.5 text-slate-400">
                          {c.created_at ? new Date(c.created_at).toLocaleDateString("id-ID") : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-slate-800/80 rounded-xl bg-slate-950/40">
                <div className="p-3 rounded-full bg-slate-900 border border-slate-800 text-slate-500 mb-3">
                  <UserX className="w-6 h-6" />
                </div>
                <h3 className="text-sm font-semibold text-slate-300 mb-1">
                  {searchQuery ? "Tidak ada customer sesuai pencarian" : "Belum Ada Customer Terdaftar"}
                </h3>
                <p className="text-xs text-slate-500 max-w-sm mb-4">
                  {searchQuery
                    ? "Coba gunakan kata kunci pencarian yang lain."
                    : "Tambah customer baru secara manual atau customer akan otomatis dibuat saat mengirim pesan via WhatsApp."}
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
                    <span>Tambah Customer Pertama</span>
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Modal Create Customer */}
        {isModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-md overflow-hidden shadow-2xl">
              <div className="flex items-center justify-between p-4 border-b border-slate-800">
                <h2 className="text-base font-semibold text-white flex items-center gap-2">
                  <User className="w-4 h-4 text-blue-400" />
                  <span>Tambah Customer Baru</span>
                </h2>
                <button
                  onClick={() => setIsModalOpen(false)}
                  className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleCreateCustomer} className="p-4 space-y-4">
                {formError && (
                  <div className="p-3 rounded-lg bg-red-950/50 border border-red-800/80 text-red-300 text-xs flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
                    <span>{formError}</span>
                  </div>
                )}

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Nama Lengkap
                  </label>
                  <div className="relative">
                    <User className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                    <input
                      type="text"
                      placeholder="Contoh: Budi Santoso"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Nomor Telepon / WhatsApp
                  </label>
                  <div className="relative">
                    <Phone className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                    <input
                      type="text"
                      placeholder="Contoh: +628123456789"
                      value={formData.phone}
                      onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Email (Opsional)
                  </label>
                  <div className="relative">
                    <Mail className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                    <input
                      type="email"
                      placeholder="Contoh: budi@example.com"
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500"
                    />
                  </div>
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
                    {isSubmitting ? "Menyimpan..." : "Simpan Customer"}
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

"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { MainLayout } from "@/components/layout/MainLayout";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth-context";
import { apiGet, apiPut, ApiError } from "@/lib/api";
import {
  Building2,
  UserCheck,
  CreditCard,
  CheckCircle2,
  AlertCircle,
  Save,
  RefreshCw,
  Sparkles,
  ShieldCheck,
  ChevronRight,
  XCircle,
  Building,
  Sliders,
  Check,
} from "lucide-react";

interface BusinessProfile {
  id?: string;
  tenant_id?: string;
  business_name?: string;
  business_type?: string;
  description?: string;
  phone?: string;
  email?: string;
  website?: string;
  address?: string;
  city?: string;
  province?: string;
  country?: string;
  return_policy?: string;
  exchange_policy?: string;
  refund_policy?: string;
}

interface SubscriptionData {
  id?: string;
  tenant_id?: string;
  plan_code?: string;
  status?: string;
  billing_cycle?: string;
  amount?: number;
  currency?: string;
  started_at?: string;
  current_period_end?: string;
  trial_end?: string;
}

interface UsageMetricItem {
  metric: string;
  current_usage: number;
  limit: number;
}

interface ReadinessData {
  ready?: boolean;
  readiness_status?: string;
  score?: number;
  percentage?: number;
  completed_requirements?: string[];
  incomplete_requirements?: string[];
  blocking_requirements?: string[];
}

export default function SettingsPage() {
  const { user, activeTenant, tenants, selectTenant } = useAuth();

  // Active Tab State
  const [activeTab, setActiveTab] = useState<"profile" | "account" | "tenant" | "package" | "readiness">("profile");

  // Profile Form State
  const [profile, setProfile] = useState<BusinessProfile>({
    business_name: "",
    business_type: "",
    description: "",
    phone: "",
    email: "",
    website: "",
    address: "",
    city: "",
    province: "",
    country: "",
    return_policy: "",
    exchange_policy: "",
    refund_policy: "",
  });

  // Data Loading States
  const [isProfileLoading, setIsProfileLoading] = useState<boolean>(true);
  const [isSavingProfile, setIsSavingProfile] = useState<boolean>(false);
  const [profileSuccessMsg, setProfileSuccessMsg] = useState<string | null>(null);
  const [profileErrorMsg, setProfileErrorMsg] = useState<string | null>(null);

  const [subscription, setSubscription] = useState<SubscriptionData | null>(null);
  const [usageMetrics, setUsageMetrics] = useState<UsageMetricItem[]>([]);
  const [isSubscriptionLoading, setIsSubscriptionLoading] = useState<boolean>(true);
  const [subscriptionError, setSubscriptionError] = useState<string | null>(null);

  const [readiness, setReadiness] = useState<ReadinessData | null>(null);
  const [isReadinessLoading, setIsReadinessLoading] = useState<boolean>(true);

  // Tenant Switcher Dropdown State
  const [switchingTenantId, setSwitchingTenantId] = useState<string | null>(null);

  // Load Business Profile
  const loadProfile = useCallback(async () => {
    if (!activeTenant) return;
    setIsProfileLoading(true);
    setProfileErrorMsg(null);

    try {
      const data = await apiGet<BusinessProfile>("/business");
      setProfile({
        business_name: data.business_name || activeTenant.name || "",
        business_type: data.business_type || "",
        description: data.description || "",
        phone: data.phone || "",
        email: data.email || "",
        website: data.website || "",
        address: data.address || "",
        city: data.city || "",
        province: data.province || "",
        country: data.country || "",
        return_policy: data.return_policy || "",
        exchange_policy: data.exchange_policy || "",
        refund_policy: data.refund_policy || "",
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // Business profile doesn't exist yet, pre-fill with tenant name
        setProfile((prev) => ({
          ...prev,
          business_name: activeTenant.name || "",
        }));
      } else if (err instanceof ApiError) {
        setProfileErrorMsg(err.message);
      } else {
        setProfileErrorMsg("Gagal memuat profil bisnis.");
      }
    } finally {
      setIsProfileLoading(false);
    }
  }, [activeTenant]);

  // Load Subscription & Usage
  const loadSubscriptionData = useCallback(async () => {
    if (!activeTenant) return;
    setIsSubscriptionLoading(true);
    setSubscriptionError(null);

    try {
      const [subRes, usageRes] = await Promise.allSettled([
        apiGet<SubscriptionData>("/billing/subscription"),
        apiGet<UsageMetricItem[]>("/billing/usage"),
      ]);

      if (subRes.status === "fulfilled") {
        setSubscription(subRes.value);
      } else {
        setSubscription(null);
        setSubscriptionError("Informasi paket belum tersedia");
      }

      if (usageRes.status === "fulfilled") {
        setUsageMetrics(usageRes.value || []);
      }
    } catch {
      setSubscriptionError("Informasi paket belum tersedia");
    } finally {
      setIsSubscriptionLoading(false);
    }
  }, [activeTenant]);

  // Load Readiness
  const loadReadiness = useCallback(async () => {
    if (!activeTenant) return;
    setIsReadinessLoading(true);

    try {
      const data = await apiGet<ReadinessData>("/business/readiness");
      setReadiness(data);
    } catch {
      setReadiness(null);
    } finally {
      setIsReadinessLoading(false);
    }
  }, [activeTenant]);

  // Initial & Tenant Change Data Load
  useEffect(() => {
    /* eslint-disable-next-line react-hooks/set-state-in-effect */
    loadProfile();
    loadSubscriptionData();
    loadReadiness();
  }, [loadProfile, loadSubscriptionData, loadReadiness]);

  // Save Business Profile Handler
  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSavingProfile(true);
    setProfileSuccessMsg(null);
    setProfileErrorMsg(null);

    try {
      const updated = await apiPut<BusinessProfile>("/business", profile);
      setProfile((prev) => ({
        ...prev,
        ...updated,
      }));
      setProfileSuccessMsg("Profil bisnis berhasil diperbarui.");
      // Refresh readiness state
      loadReadiness();
    } catch (err) {
      if (err instanceof ApiError) {
        setProfileErrorMsg(err.message);
      } else {
        setProfileErrorMsg("Gagal menyimpan perubahan profil bisnis.");
      }
    } finally {
      setIsSavingProfile(false);
    }
  };

  const handleSelectBusiness = async (tenantId: string) => {
    if (tenantId === activeTenant?.id) return;
    setSwitchingTenantId(tenantId);
    try {
      await selectTenant(tenantId);
    } catch {
      // Auth context handles error
    } finally {
      setSwitchingTenantId(null);
    }
  };

  const formatMetricName = (name: string) => {
    switch (name.toLowerCase()) {
      case "ai_credits":
        return "AI Credits";
      case "whatsapp_connections":
        return "WhatsApp Connections";
      case "active_customers":
        return "Active Customers";
      case "outbound_messages":
        return "Outbound Messages";
      case "automation_runs":
        return "Automation Runs";
      default:
        return name.replace(/_/g, " ").toUpperCase();
    }
  };

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Page Title & Context Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap mb-1">
              <h1 className="text-2xl font-bold tracking-tight text-white">Pengaturan Sistem</h1>
              <Badge variant="secondary" size="sm" className="bg-blue-900/40 text-blue-300 border-blue-700/50">
                <Building className="w-3 h-3 mr-1" />
                {activeTenant?.name || "Business Context"}
              </Badge>
            </div>
            <p className="text-xs sm:text-sm text-slate-400">
              Kelola profil bisnis, akun pemilik, lisensi paket, dan kesiapan operasional AI BOS.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                loadProfile();
                loadSubscriptionData();
                loadReadiness();
              }}
              className="text-xs bg-slate-900/80 border-slate-800 hover:border-slate-700 text-slate-300"
            >
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
              <span>SINKRONKAN</span>
            </Button>
          </div>
        </div>

        {/* Tab Navigation Menu */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 border-b border-slate-800">
          <button
            type="button"
            onClick={() => setActiveTab("profile")}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
              activeTab === "profile"
                ? "bg-blue-600/15 text-blue-400 border border-blue-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <Building2 className="w-4 h-4" />
            <span>Profil Bisnis</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("account")}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
              activeTab === "account"
                ? "bg-blue-600/15 text-blue-400 border border-blue-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <UserCheck className="w-4 h-4" />
            <span>Akun Pengguna</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("tenant")}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
              activeTab === "tenant"
                ? "bg-blue-600/15 text-blue-400 border border-blue-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <Sliders className="w-4 h-4" />
            <span>Tenant & Akses</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("package")}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
              activeTab === "package"
                ? "bg-blue-600/15 text-blue-400 border border-blue-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <CreditCard className="w-4 h-4" />
            <span>Paket & Lisensi</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("readiness")}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
              activeTab === "readiness"
                ? "bg-blue-600/15 text-blue-400 border border-blue-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <ShieldCheck className="w-4 h-4" />
            <span>Kesiapan Bisnis</span>
            {readiness?.percentage !== undefined && (
              <Badge variant={readiness.ready ? "success" : "warning"} size="sm" className="text-[10px] ml-1">
                {readiness.percentage}%
              </Badge>
            )}
          </button>
        </div>

        {/* TAB 1: BUSINESS PROFILE FORM */}
        {activeTab === "profile" && (
          <Card variant="default">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Building2 className="w-4 h-4 text-blue-400" />
                    <span>Profil Operasional Bisnis</span>
                  </CardTitle>
                  <CardDescription>
                    Informasi profil digunakan oleh AI BOS sebagai konteks utama layanan pelanggan.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {isProfileLoading ? (
                <div className="space-y-4 py-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="h-10 bg-slate-900 rounded-lg animate-pulse" />
                    <div className="h-10 bg-slate-900 rounded-lg animate-pulse" />
                  </div>
                  <div className="h-20 bg-slate-900 rounded-lg animate-pulse" />
                </div>
              ) : (
                <form onSubmit={handleSaveProfile} className="space-y-5">
                  {/* Status Banners */}
                  {profileSuccessMsg && (
                    <div className="p-3.5 rounded-xl bg-emerald-950/60 border border-emerald-800 text-emerald-200 text-xs flex items-center gap-2.5">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                      <span>{profileSuccessMsg}</span>
                    </div>
                  )}

                  {profileErrorMsg && (
                    <div className="p-3.5 rounded-xl bg-red-950/60 border border-red-800 text-red-200 text-xs flex items-center gap-2.5">
                      <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
                      <span>{profileErrorMsg}</span>
                    </div>
                  )}

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Business Name */}
                    <div>
                      <label className="text-xs font-semibold text-slate-300 block mb-1.5">
                        Nama Bisnis <span className="text-red-400">*</span>
                      </label>
                      <input
                        type="text"
                        value={profile.business_name || ""}
                        onChange={(e) => setProfile({ ...profile, business_name: e.target.value })}
                        required
                        placeholder="Contoh: Toko Kopi Sejahtera"
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-blue-500 transition-colors"
                      />
                    </div>

                    {/* Business Type */}
                    <div>
                      <label className="text-xs font-semibold text-slate-300 block mb-1.5">
                        Kategori / Tipe Bisnis
                      </label>
                      <input
                        type="text"
                        value={profile.business_type || ""}
                        onChange={(e) => setProfile({ ...profile, business_type: e.target.value })}
                        placeholder="Contoh: F&B / Retail / Jasa"
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-blue-500 transition-colors"
                      />
                    </div>
                  </div>

                  {/* Description */}
                  <div>
                    <label className="text-xs font-semibold text-slate-300 block mb-1.5">
                      Deskripsi Ringkas Bisnis
                    </label>
                    <textarea
                      value={profile.description || ""}
                      onChange={(e) => setProfile({ ...profile, description: e.target.value })}
                      rows={3}
                      placeholder="Jelaskan produk utama, jam operasional, atau keunggulan bisnis Anda..."
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-blue-500 transition-colors"
                    />
                  </div>

                  {/* Contact Info */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className="text-xs font-semibold text-slate-300 block mb-1.5">
                        Nomor Telepon Bisnis
                      </label>
                      <input
                        type="text"
                        value={profile.phone || ""}
                        onChange={(e) => setProfile({ ...profile, phone: e.target.value })}
                        placeholder="08123456789"
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-blue-500 transition-colors"
                      />
                    </div>

                    <div>
                      <label className="text-xs font-semibold text-slate-300 block mb-1.5">
                        Email Resmi
                      </label>
                      <input
                        type="email"
                        value={profile.email || ""}
                        onChange={(e) => setProfile({ ...profile, email: e.target.value })}
                        placeholder="info@bisnis.com"
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-blue-500 transition-colors"
                      />
                    </div>

                    <div>
                      <label className="text-xs font-semibold text-slate-300 block mb-1.5">
                        Website
                      </label>
                      <input
                        type="text"
                        value={profile.website || ""}
                        onChange={(e) => setProfile({ ...profile, website: e.target.value })}
                        placeholder="https://bisnis.com"
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-blue-500 transition-colors"
                      />
                    </div>
                  </div>

                  {/* Address Info */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs font-semibold text-slate-300 block mb-1.5">
                        Alamat Lengkap
                      </label>
                      <input
                        type="text"
                        value={profile.address || ""}
                        onChange={(e) => setProfile({ ...profile, address: e.target.value })}
                        placeholder="Jl. Merdeka No. 123"
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-blue-500 transition-colors"
                      />
                    </div>

                    <div>
                      <label className="text-xs font-semibold text-slate-300 block mb-1.5">
                        Kota / Kabupaten
                      </label>
                      <input
                        type="text"
                        value={profile.city || ""}
                        onChange={(e) => setProfile({ ...profile, city: e.target.value })}
                        placeholder="Jakarta Selatan"
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-blue-500 transition-colors"
                      />
                    </div>
                  </div>

                  {/* Policies Section */}
                  <div className="pt-2 border-t border-slate-800 space-y-3">
                    <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                      Kebijakan Toko & Layanan
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div>
                        <label className="text-xs font-semibold text-slate-400 block mb-1">
                          Kebijakan Pengembalian
                        </label>
                        <textarea
                          value={profile.return_policy || ""}
                          onChange={(e) => setProfile({ ...profile, return_policy: e.target.value })}
                          rows={2}
                          placeholder="Aturan pengembalian barang..."
                          className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
                        />
                      </div>

                      <div>
                        <label className="text-xs font-semibold text-slate-400 block mb-1">
                          Kebijakan Penukaran
                        </label>
                        <textarea
                          value={profile.exchange_policy || ""}
                          onChange={(e) => setProfile({ ...profile, exchange_policy: e.target.value })}
                          rows={2}
                          placeholder="Syarat penukaran ukuran/varian..."
                          className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
                        />
                      </div>

                      <div>
                        <label className="text-xs font-semibold text-slate-400 block mb-1">
                          Kebijakan Refund
                        </label>
                        <textarea
                          value={profile.refund_policy || ""}
                          onChange={(e) => setProfile({ ...profile, refund_policy: e.target.value })}
                          rows={2}
                          placeholder="Syarat dan mekanisme refund dana..."
                          className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Submit Action */}
                  <div className="pt-3 flex items-center justify-end">
                    <Button
                      type="submit"
                      disabled={isSavingProfile}
                      variant="primary"
                      className="text-xs px-5 py-2"
                    >
                      {isSavingProfile ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5 mr-2 animate-spin" />
                          <span>MENYIMPAN...</span>
                        </>
                      ) : (
                        <>
                          <Save className="w-3.5 h-3.5 mr-2" />
                          <span>SIMPAN PERUBAHAN</span>
                        </>
                      )}
                    </Button>
                  </div>
                </form>
              )}
            </CardContent>
          </Card>
        )}

        {/* TAB 2: ACCOUNT INFO */}
        {activeTab === "account" && (
          <div className="space-y-6">
            <Card variant="default">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <UserCheck className="w-4 h-4 text-emerald-400" />
                  <span>Akun Terautentikasi</span>
                </CardTitle>
                <CardDescription>
                  Identitas pemilik/pengelola yang sedang aktif di platform
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <span className="text-[11px] font-semibold uppercase text-slate-500 tracking-wider">
                      Email Sesi Utama
                    </span>
                    <p className="text-sm font-semibold text-slate-100">{user?.email || "N/A"}</p>
                  </div>

                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <span className="text-[11px] font-semibold uppercase text-slate-500 tracking-wider">
                      ID Pengguna (User ID)
                    </span>
                    <p className="text-xs font-mono text-slate-300">{user?.id || "N/A"}</p>
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                  <div>
                    <p className="text-xs font-semibold text-slate-200">Hak Akses Server (Role)</p>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      Memiliki wewenang penuh atas konfigurasi bisnis & integrasi
                    </p>
                  </div>
                  <Badge variant="success" size="sm" className="uppercase font-mono text-[10px]">
                    OWNER / ADMIN
                  </Badge>
                </div>

                <div className="p-4 rounded-xl bg-blue-950/20 border border-blue-900/40 space-y-1">
                  <p className="text-xs font-semibold text-blue-300 flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-blue-400" />
                    Proteksi Otorisasi Sesi
                  </p>
                  <p className="text-[11px] text-slate-400 leading-relaxed">
                    Sesi Anda diawasi langsung oleh sistem enkripsi server. Kredensial rahasia tidak pernah ditampilkan secara langsung pada halaman web.
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* TAB 3: TENANT CONTEXT */}
        {activeTab === "tenant" && (
          <div className="space-y-6">
            <Card variant="default">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Sliders className="w-4 h-4 text-purple-400" />
                  <span>Informasi Tenant Bisnis</span>
                </CardTitle>
                <CardDescription>
                  Detail konteks bisnis aktif dan daftar bisnis terdaftar pada akun Anda
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <span className="text-[11px] font-semibold uppercase text-slate-500 tracking-wider">
                      Nama Bisnis Aktif
                    </span>
                    <p className="text-sm font-semibold text-slate-100">{activeTenant?.name || "N/A"}</p>
                  </div>

                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <span className="text-[11px] font-semibold uppercase text-slate-500 tracking-wider">
                      Slug Identifikasi
                    </span>
                    <p className="text-xs font-mono text-slate-300">{activeTenant?.slug || "N/A"}</p>
                  </div>

                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <span className="text-[11px] font-semibold uppercase text-slate-500 tracking-wider">
                      Active Tenant ID
                    </span>
                    <p className="text-xs font-mono text-blue-400">{activeTenant?.id || "N/A"}</p>
                  </div>

                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <span className="text-[11px] font-semibold uppercase text-slate-500 tracking-wider">
                      Status Siklus Hidup (Lifecycle)
                    </span>
                    <div>
                      <Badge variant="outline" size="sm" className="uppercase font-mono text-[10px] border-slate-700 text-slate-300 mt-0.5">
                        {activeTenant?.lifecycle_state || "ACTIVE"}
                      </Badge>
                    </div>
                  </div>
                </div>

                {/* Available Tenants Switcher List */}
                <div className="pt-2 border-t border-slate-800 space-y-3">
                  <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Daftar Bisnis Anda ({tenants.length})
                  </p>

                  <div className="space-y-2">
                    {tenants.map((t) => {
                      const isActive = activeTenant?.id === t.id;
                      const isSwitching = switchingTenantId === t.id;

                      return (
                        <div
                          key={t.id}
                          className={`p-3.5 rounded-xl border flex items-center justify-between transition-all ${
                            isActive
                              ? "bg-blue-950/20 border-blue-500/40"
                              : "bg-slate-950 border-slate-800 hover:border-slate-700"
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-slate-900 text-slate-300 border border-slate-800">
                              <Building2 className="w-4 h-4" />
                            </div>
                            <div>
                              <p className="text-xs font-semibold text-slate-200">{t.name}</p>
                              <p className="text-[10px] text-slate-500 font-mono">{t.slug}</p>
                            </div>
                          </div>

                          <div>
                            {isActive ? (
                              <span className="text-xs font-semibold text-blue-400 flex items-center gap-1">
                                <Check className="w-4 h-4" /> Bisnis Aktif
                              </span>
                            ) : (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleSelectBusiness(t.id)}
                                disabled={!!switchingTenantId}
                                className="text-xs"
                              >
                                {isSwitching ? (
                                  <RefreshCw className="w-3 h-3 animate-spin" />
                                ) : (
                                  "Ganti Bisnis"
                                )}
                              </Button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* TAB 4: PACKAGE & SUBSCRIPTION */}
        {activeTab === "package" && (
          <div className="space-y-6">
            <Card variant="default">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <CreditCard className="w-4 h-4 text-amber-400" />
                  <span>Informasi Paket & Lisensi</span>
                </CardTitle>
                <CardDescription>
                  Status paket langganan dan batasan kuota penggunaan
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                {isSubscriptionLoading ? (
                  <div className="space-y-3">
                    <div className="h-12 bg-slate-900 rounded-lg animate-pulse" />
                    <div className="h-24 bg-slate-900 rounded-lg animate-pulse" />
                  </div>
                ) : subscription ? (
                  <>
                    <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-lg font-bold text-white uppercase">
                            Paket {subscription.plan_code}
                          </span>
                          <Badge variant="success" size="sm" className="uppercase text-[10px]">
                            {subscription.status || "ACTIVE"}
                          </Badge>
                        </div>
                        <p className="text-xs text-slate-400">
                          Siklus Tagihan:{" "}
                          <span className="text-slate-200 font-medium">
                            {subscription.billing_cycle || "MONTHLY"}
                          </span>
                        </p>
                      </div>

                      <div className="text-left sm:text-right">
                        <p className="text-xs text-slate-500">Masa Berlaku Hingga</p>
                        <p className="text-xs font-semibold text-slate-200 mt-0.5">
                          {subscription.current_period_end
                            ? new Date(subscription.current_period_end).toLocaleDateString("id-ID", {
                                year: "numeric",
                                month: "long",
                                day: "numeric",
                              })
                            : "Tidak Terbatas"}
                        </p>
                      </div>
                    </div>

                    {/* Usage Metrics */}
                    {usageMetrics.length > 0 && (
                      <div className="space-y-3">
                        <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                          Penggunaan Kuota Layanan
                        </p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                          {usageMetrics.map((item) => {
                            const percent = item.limit > 0 ? Math.min(100, Math.round((item.current_usage / item.limit) * 100)) : 0;
                            return (
                              <div key={item.metric} className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                                <div className="flex items-center justify-between text-xs">
                                  <span className="text-slate-400 font-medium">
                                    {formatMetricName(item.metric)}
                                  </span>
                                  <span className="font-mono text-slate-200">
                                    {item.current_usage} / {item.limit > 0 ? item.limit : "∞"}
                                  </span>
                                </div>
                                {item.limit > 0 && (
                                  <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                                    <div
                                      className="bg-blue-500 h-full rounded-full transition-all"
                                      style={{ width: `${percent}%` }}
                                    />
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="p-6 rounded-xl bg-slate-950 border border-slate-800 text-center space-y-2">
                    <AlertCircle className="w-8 h-8 text-amber-400 mx-auto" />
                    <p className="text-xs font-semibold text-slate-200">Informasi paket belum tersedia</p>
                    <p className="text-[11px] text-slate-500 max-w-sm mx-auto">
                      {subscriptionError || "Tenant belum memiliki langganan aktif yang terdaftar di sistem billing."}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* TAB 5: BUSINESS READINESS OVERVIEW */}
        {activeTab === "readiness" && (
          <div className="space-y-6">
            <Card variant="default">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <ShieldCheck className="w-4 h-4 text-emerald-400" />
                      <span>Status Kesiapan Bisnis (Business Readiness)</span>
                    </CardTitle>
                    <CardDescription>
                      Evaluasi kesiapan konfigurasi tenant sebelum menjalankan AI BOS secara otomatis
                    </CardDescription>
                  </div>
                  {readiness?.readiness_status && (
                    <Badge
                      variant={readiness.ready ? "success" : "warning"}
                      size="sm"
                      className="uppercase font-mono text-[10px]"
                    >
                      {readiness.readiness_status}
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-6">
                {isReadinessLoading ? (
                  <div className="space-y-3">
                    <div className="h-6 bg-slate-900 rounded animate-pulse" />
                    <div className="h-20 bg-slate-900 rounded animate-pulse" />
                  </div>
                ) : readiness ? (
                  <>
                    {/* Overall Score Progress Bar */}
                    <div className="p-5 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-slate-300 uppercase tracking-wider">
                          Skor Kesiapan Sistem
                        </span>
                        <span className="text-lg font-bold text-white font-mono">
                          {readiness.percentage ?? readiness.score ?? 0}%
                        </span>
                      </div>

                      <div className="w-full bg-slate-900 rounded-full h-3 overflow-hidden p-0.5 border border-slate-800">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            readiness.ready
                              ? "bg-emerald-500"
                              : (readiness.percentage ?? readiness.score ?? 0) >= 60
                              ? "bg-amber-500"
                              : "bg-blue-500"
                          }`}
                          style={{ width: `${readiness.percentage ?? readiness.score ?? 0}%` }}
                        />
                      </div>

                      <p className="text-[11px] text-slate-400">
                        {readiness.ready
                          ? "✓ Seluruh konfigurasi kritis siap digerakkan oleh AI BOS."
                          : "Lengkapi item yang belum dikonfigurasi untuk mencapai tingkat kesiapan optimal."}
                      </p>
                    </div>

                    {/* Requirements Checklist */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {/* Completed Items */}
                      <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                        <p className="text-xs font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                          <CheckCircle2 className="w-4 h-4" />
                          Syarat Terpenuhi ({readiness.completed_requirements?.length || 0})
                        </p>

                        <div className="space-y-1.5">
                          {(readiness.completed_requirements || []).length > 0 ? (
                            readiness.completed_requirements?.map((req, idx) => (
                              <div key={idx} className="flex items-center gap-2 text-xs text-slate-300">
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
                                <span>{req}</span>
                              </div>
                            ))
                          ) : (
                            <p className="text-xs text-slate-500">Belum ada syarat yang diselesaikan.</p>
                          )}
                        </div>
                      </div>

                      {/* Incomplete / Blocking Items */}
                      <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                        <p className="text-xs font-semibold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                          <AlertCircle className="w-4 h-4" />
                          Syarat Perlu Dikonfigurasi ({readiness.incomplete_requirements?.length || 0})
                        </p>

                        <div className="space-y-1.5">
                          {(readiness.incomplete_requirements || []).length > 0 ? (
                            readiness.incomplete_requirements?.map((req, idx) => {
                              const isBlocking = readiness.blocking_requirements?.includes(req);
                              return (
                                <div key={idx} className="flex items-center justify-between text-xs text-slate-300">
                                  <div className="flex items-center gap-2">
                                    <XCircle className={`w-3.5 h-3.5 shrink-0 ${isBlocking ? "text-red-400" : "text-amber-400"}`} />
                                    <span>{req}</span>
                                  </div>
                                  {isBlocking && (
                                    <Badge variant="danger" size="sm" className="text-[9px] uppercase">
                                      BLOCKING
                                    </Badge>
                                  )}
                                </div>
                              );
                            })
                          ) : (
                            <p className="text-xs text-slate-500">Tidak ada syarat yang tertunda.</p>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Direct Call to Action */}
                    <div className="p-4 rounded-xl bg-blue-950/20 border border-blue-900/40 flex items-center justify-between gap-4">
                      <div className="space-y-0.5">
                        <p className="text-xs font-semibold text-blue-300 flex items-center gap-1.5">
                          <Sparkles className="w-4 h-4 text-blue-400" />
                          Integrasi Platform Eksternal
                        </p>
                        <p className="text-[11px] text-slate-400">
                          Hubungkan WhatsApp Cloud API dan Google Workspace untuk mengaktifkan AI BOS secara otomatis.
                        </p>
                      </div>

                      <Link href="/integrations">
                        <Button variant="primary" size="sm" className="text-xs shrink-0">
                          <span>Buka Integrations</span>
                          <ChevronRight className="w-3.5 h-3.5 ml-1" />
                        </Button>
                      </Link>
                    </div>
                  </>
                ) : (
                  <div className="p-6 text-center text-xs text-slate-500">
                    Gagal memuat status kesiapan bisnis.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </MainLayout>
  );
}

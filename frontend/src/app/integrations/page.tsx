"use client";

import React, { useEffect, useState, useCallback } from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth-context";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import {
  MessageSquare,
  Calendar,
  CreditCard,
  FileSpreadsheet,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Sparkles,
  Unplug,
  ShieldCheck,
  Check,
  X,
  Lock,
} from "lucide-react";

interface IntegrationDefinition {
  id: string;
  integration_key: string;
  provider_key: string;
  display_name: string;
  category: string;
  status?: string;
  is_enabled: boolean;
}

interface IntegrationConnection {
  id: string;
  tenant_id: string;
  integration_id: string;
  status: string;
  external_account_id?: string | null;
  meta_data?: Record<string, unknown> | null;
  last_connected_at?: string | null;
  last_success_at?: string | null;
  last_error_at?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

interface WhatsAppConnectResponse {
  connection_id: string;
  status: string;
  phone_number_id: string;
  waba_id?: string;
  is_verified: boolean;
}

interface WhatsAppVerifyResponse {
  connection_id: string;
  status: string;
  is_verified: boolean;
  phone_number_id?: string;
  message: string;
}

export default function IntegrationsPage() {
  const { activeTenant } = useAuth();

  const [definitions, setDefinitions] = useState<IntegrationDefinition[]>([]);
  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // WhatsApp Setup Modal State
  const [showWaModal, setShowWaModal] = useState<boolean>(false);
  const [waPhoneNumberId, setWaPhoneNumberId] = useState<string>("");
  const [waWabaId, setWaWabaId] = useState<string>("");
  const [waAccessToken, setWaAccessToken] = useState<string>("");
  const [waAppSecret, setWaAppSecret] = useState<string>("");

  const [isSubmittingWa, setIsSubmittingWa] = useState<boolean>(false);
  const [waFeedbackMsg, setWaFeedbackMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Load Both Integration Definitions & Tenant Connections
  const loadData = useCallback(async () => {
    if (!activeTenant) return;
    setIsLoading(true);
    setErrorMsg(null);

    try {
      const [defsRes, connsRes] = await Promise.allSettled([
        apiGet<IntegrationDefinition[]>("/integrations"),
        apiGet<IntegrationConnection[]>("/integrations/connections"),
      ]);

      if (defsRes.status === "fulfilled") {
        setDefinitions(defsRes.value || []);
      }
      if (connsRes.status === "fulfilled") {
        setConnections(connsRes.value || []);
      }

      if (defsRes.status === "rejected" && connsRes.status === "rejected") {
        setErrorMsg("Gagal memuat daftar integrasi dan koneksi tenant.");
      }
    } catch {
      setErrorMsg("Gagal memuat status integrasi tenant.");
    } finally {
      setIsLoading(false);
    }
  }, [activeTenant]);

  useEffect(() => {
    /* eslint-disable-next-line react-hooks/set-state-in-effect */
    loadData();
  }, [loadData]);

  // Helper to find definition for a provider
  const getDefinition = (providerKey: string): IntegrationDefinition | undefined => {
    return definitions.find(
      (d) =>
        d.provider_key.toLowerCase() === providerKey.toLowerCase() ||
        d.integration_key.toLowerCase() === providerKey.toLowerCase()
    );
  };

  // Helper to find connection for a provider
  const getConnection = (providerKey: string): IntegrationConnection | undefined => {
    const def = getDefinition(providerKey);
    if (!def) return undefined;
    return connections.find((c) => c.integration_id === def.id);
  };

  const getStatusBadge = (status?: string) => {
    const s = (status || "DISCONNECTED").toUpperCase();
    if (s === "CONNECTED" || s === "ACTIVE") {
      return <Badge variant="success" size="sm"><Check className="w-3 h-3 mr-1" /> Terhubung</Badge>;
    }
    if (s === "CONNECTING" || s === "PENDING") {
      return <Badge variant="warning" size="sm">Menghubungkan</Badge>;
    }
    if (s === "ERROR" || s === "EXPIRED" || s === "REVOKED") {
      return <Badge variant="danger" size="sm">Perlu Otorisasi Ulang</Badge>;
    }
    return <Badge variant="outline" size="sm" className="text-slate-400 border-slate-800">Belum Terhubung</Badge>;
  };

  // WhatsApp Connect Action
  const handleConnectWhatsApp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeTenant) return;

    setIsSubmittingWa(true);
    setWaFeedbackMsg(null);

    try {
      const res = await apiPost<WhatsAppConnectResponse>(
        `/tenants/${activeTenant.id}/onboarding/whatsapp/connect`,
        {
          phone_number_id: waPhoneNumberId.trim(),
          waba_id: waWabaId.trim() || undefined,
          access_token: waAccessToken.trim(),
          app_secret: waAppSecret.trim() || undefined,
        }
      );

      setWaFeedbackMsg({
        type: "success",
        text: `Koneksi WhatsApp berhasil dibuat! Status: ${res.status}. ID Koneksi: ${res.connection_id.substring(0, 8)}...`,
      });

      // Clear credential form state for security
      setWaAccessToken("");
      setWaAppSecret("");

      // Reload connection list
      await loadData();
    } catch (err) {
      if (err instanceof ApiError) {
        setWaFeedbackMsg({ type: "error", text: err.message });
      } else {
        setWaFeedbackMsg({ type: "error", text: "Gagal menghubungkan WhatsApp Cloud API." });
      }
    } finally {
      setIsSubmittingWa(false);
    }
  };

  // WhatsApp Verify Action
  const handleVerifyWhatsApp = async (connectionId: string) => {
    if (!activeTenant) return;
    setIsSubmittingWa(true);
    setWaFeedbackMsg(null);

    try {
      const res = await apiPost<WhatsAppVerifyResponse>(
        `/tenants/${activeTenant.id}/onboarding/whatsapp/verify?connection_id=${connectionId}`
      );

      setWaFeedbackMsg({
        type: "success",
        text: `Verifikasi WhatsApp: ${res.message || "Koneksi terverifikasi aktif."}`,
      });

      await loadData();
    } catch (err) {
      if (err instanceof ApiError) {
        setWaFeedbackMsg({ type: "error", text: err.message });
      } else {
        setWaFeedbackMsg({ type: "error", text: "Gagal memverifikasi status WhatsApp." });
      }
    } finally {
      setIsSubmittingWa(false);
    }
  };

  // WhatsApp Disconnect Action
  const handleDisconnectWhatsApp = async (connectionId: string) => {
    if (!activeTenant) return;
    if (!confirm("Apakah Anda yakin ingin memutuskan integrasi WhatsApp Cloud API?")) return;

    setIsSubmittingWa(true);
    setWaFeedbackMsg(null);

    try {
      await apiPost(
        `/tenants/${activeTenant.id}/onboarding/whatsapp/disconnect?connection_id=${connectionId}`
      );

      setWaFeedbackMsg({
        type: "success",
        text: "Integrasi WhatsApp berhasil diputuskan.",
      });

      await loadData();
    } catch (err) {
      if (err instanceof ApiError) {
        setWaFeedbackMsg({ type: "error", text: err.message });
      } else {
        setWaFeedbackMsg({ type: "error", text: "Gagal memutuskan koneksi WhatsApp." });
      }
    } finally {
      setIsSubmittingWa(false);
    }
  };

  const waConn = getConnection("whatsapp_cloud_api") || getConnection("whatsapp");
  const gcalConn = getConnection("google_calendar");
  const midtransConn = getConnection("midtrans");
  const gsheetsConn = getConnection("google_sheets");

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Header & Page Title */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h1 className="text-2xl font-bold tracking-tight text-white">Integrasi Platform</h1>
              <Badge variant="secondary" size="sm" className="bg-cyan-950/60 text-cyan-300 border-cyan-800/60">
                Pusat Konektor
              </Badge>
            </div>
            <p className="text-xs sm:text-sm text-slate-400">
              Kelola status koneksi WhatsApp Cloud API, Google Calendar, Midtrans, dan Google Sheets.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={loadData}
              disabled={isLoading}
              className="text-xs bg-slate-900/80 border-slate-800 hover:border-slate-700 text-slate-300"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${isLoading ? "animate-spin text-blue-400" : ""}`} />
              <span>SINKRONKAN INTEGRASI</span>
            </Button>
          </div>
        </div>

        {/* Error Alert Banner */}
        {errorMsg && (
          <div className="p-4 rounded-xl bg-red-950/50 border border-red-800/80 text-red-200 text-xs flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
              <span>{errorMsg}</span>
            </div>
            <Button variant="danger" size="sm" onClick={loadData} className="text-xs shrink-0">
              Coba Lagi
            </Button>
          </div>
        )}

        {/* Integration Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* CARD 1: WHATSAPP CLOUD API */}
          <Card variant="default" className="flex flex-col justify-between">
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <MessageSquare className="w-5 h-5" />
                  </div>
                  <div>
                    <CardTitle className="text-base">WhatsApp Cloud API</CardTitle>
                    <CardDescription>Saluran utama pesan masuk & otomatisasi respons pelanggan</CardDescription>
                  </div>
                </div>
                {getStatusBadge(waConn?.status)}
              </div>
            </CardHeader>
            <CardContent className="space-y-4 flex-1 flex flex-col justify-between">
              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Status Koneksi Tenant:</span>
                  <span className="font-medium text-slate-200">
                    {waConn?.status || "DISCONNECTED"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">ID Koneksi:</span>
                  <span className="font-mono text-slate-300">
                    {waConn?.id ? `${waConn.id.substring(0, 8)}...` : "Belum Dibuat"}
                  </span>
                </div>
              </div>

              <div className="pt-2 flex items-center justify-between gap-2">
                {waConn?.status === "CONNECTED" || waConn?.status === "ACTIVE" ? (
                  <div className="flex items-center gap-2 w-full">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleVerifyWhatsApp(waConn.id)}
                      disabled={isSubmittingWa}
                      className="text-xs flex-1"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5 mr-1 text-emerald-400" />
                      <span>Verifikasi Health</span>
                    </Button>

                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => handleDisconnectWhatsApp(waConn.id)}
                      disabled={isSubmittingWa}
                      className="text-xs"
                    >
                      <Unplug className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                ) : (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      setWaFeedbackMsg(null);
                      setShowWaModal(true);
                    }}
                    className="text-xs w-full"
                  >
                    <span>Konfigurasi WhatsApp</span>
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          {/* CARD 2: GOOGLE CALENDAR */}
          <Card variant="default" className="flex flex-col justify-between">
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
                    <Calendar className="w-5 h-5" />
                  </div>
                  <div>
                    <CardTitle className="text-base">Google Calendar</CardTitle>
                    <CardDescription>Penyelarasan jadwal janji temu & kalender bisnis</CardDescription>
                  </div>
                </div>
                {getStatusBadge(gcalConn?.status)}
              </div>
            </CardHeader>
            <CardContent className="space-y-4 flex-1 flex flex-col justify-between">
              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Status Otorisasi OAuth:</span>
                  <span className="font-medium text-slate-200">
                    {gcalConn?.status === "CONNECTED" ? "Terotentikasi" : "Belum Terhubung"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Modul Operasional:</span>
                  <span className="text-slate-300">Google Calendar Adapter</span>
                </div>
              </div>

              <div className="pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled
                  className="text-xs w-full bg-slate-900 border-slate-800 text-slate-500 cursor-not-allowed"
                >
                  <Lock className="w-3.5 h-3.5 mr-1.5" />
                  <span>{gcalConn?.status === "CONNECTED" ? "Terhubung via Backend" : "OAuth Flow Terjadwal"}</span>
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* CARD 3: MIDTRANS PAYMENT GATEWAY */}
          <Card variant="default" className="flex flex-col justify-between">
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
                    <CreditCard className="w-5 h-5" />
                  </div>
                  <div>
                    <CardTitle className="text-base">Midtrans Payment</CardTitle>
                    <CardDescription>Payment gateway otomatisasi invoice Snap & Core API</CardDescription>
                  </div>
                </div>
                {getStatusBadge(midtransConn?.status)}
              </div>
            </CardHeader>
            <CardContent className="space-y-4 flex-1 flex flex-col justify-between">
              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Modul Pembayaran:</span>
                  <span className="font-medium text-slate-200">Midtrans Provider Engine</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Metode Didukung:</span>
                  <span className="text-slate-300">QRIS, Bank Transfer, E-Wallet</span>
                </div>
              </div>

              <div className="pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled
                  className="text-xs w-full bg-slate-900 border-slate-800 text-slate-500 cursor-not-allowed"
                >
                  <Lock className="w-3.5 h-3.5 mr-1.5" />
                  <span>{midtransConn?.status === "CONNECTED" ? "Terhubung via Backend" : "Konfigurasi Server Direct"}</span>
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* CARD 4: GOOGLE SHEETS */}
          <Card variant="default" className="flex flex-col justify-between">
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
                    <FileSpreadsheet className="w-5 h-5" />
                  </div>
                  <div>
                    <CardTitle className="text-base">Google Sheets</CardTitle>
                    <CardDescription>Pencatatan & ekspor otomatis data pesanan ke Spreadsheet</CardDescription>
                  </div>
                </div>
                {getStatusBadge(gsheetsConn?.status)}
              </div>
            </CardHeader>
            <CardContent className="space-y-4 flex-1 flex flex-col justify-between">
              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Akses Spreadsheet:</span>
                  <span className="font-medium text-slate-200">
                    {gsheetsConn?.status === "CONNECTED" ? "Terhubung" : "Belum Terkoneksi"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Izin Workflow:</span>
                  <span className="text-slate-300">Append Rows & Export Orders</span>
                </div>
              </div>

              <div className="pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled
                  className="text-xs w-full bg-slate-900 border-slate-800 text-slate-500 cursor-not-allowed"
                >
                  <Lock className="w-3.5 h-3.5 mr-1.5" />
                  <span>{gsheetsConn?.status === "CONNECTED" ? "Terhubung via Backend" : "OAuth Flow Terjadwal"}</span>
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Security Info Card */}
        <div className="p-4 rounded-xl bg-blue-950/20 border border-blue-900/40 space-y-1">
          <p className="text-xs font-semibold text-blue-300 flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-blue-400" />
            Keamanan Kredensial & Enkripsi Server
          </p>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            Seluruh kunci API, token otorisasi, dan rahasia aplikasi tersimpan secara aman dalam Credential Vault dengan enkripsi Fernet HMAC-SHA256. Kredensial tidak pernah dapat dibaca ulang melalui antarmuka frontend.
          </p>
        </div>

        {/* MODAL: WHATSAPP CLOUD API SETUP */}
        {showWaModal && (
          <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
              <div className="p-5 border-b border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                    <MessageSquare className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-white">Konfigurasi WhatsApp Cloud API</h3>
                    <p className="text-[11px] text-slate-400">Masukkan kredensial resmi Meta Developer Console</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setShowWaModal(false)}
                  className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleConnectWhatsApp} className="p-5 space-y-4">
                {/* Feedback Alert */}
                {waFeedbackMsg && (
                  <div
                    className={`p-3 rounded-xl border text-xs flex items-center gap-2 ${
                      waFeedbackMsg.type === "success"
                        ? "bg-emerald-950/60 border-emerald-800 text-emerald-200"
                        : "bg-red-950/60 border-red-800 text-red-200"
                    }`}
                  >
                    {waFeedbackMsg.type === "success" ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                    ) : (
                      <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
                    )}
                    <span>{waFeedbackMsg.text}</span>
                  </div>
                )}

                {/* Phone Number ID */}
                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">
                    Phone Number ID <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="text"
                    value={waPhoneNumberId}
                    onChange={(e) => setWaPhoneNumberId(e.target.value)}
                    required
                    placeholder="Contoh: 1029384756102"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 text-xs text-slate-100 focus:outline-none focus:border-blue-500"
                  />
                </div>

                {/* WABA ID */}
                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">
                    WhatsApp Business Account ID (WABA ID)
                  </label>
                  <input
                    type="text"
                    value={waWabaId}
                    onChange={(e) => setWaWabaId(e.target.value)}
                    placeholder="Contoh: 9876543210987"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 text-xs text-slate-100 focus:outline-none focus:border-blue-500"
                  />
                </div>

                {/* System Access Token */}
                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">
                    Graph API Permanent Access Token <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="password"
                    value={waAccessToken}
                    onChange={(e) => setWaAccessToken(e.target.value)}
                    required
                    placeholder="EAAG..."
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 text-xs text-slate-100 focus:outline-none focus:border-blue-500 font-mono"
                  />
                  <p className="text-[10px] text-slate-500 mt-1">
                    Token akan dienkripsi secara aman dan tidak ditampilkan kembali.
                  </p>
                </div>

                {/* App Secret */}
                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">
                    App Secret (Opsional)
                  </label>
                  <input
                    type="password"
                    value={waAppSecret}
                    onChange={(e) => setWaAppSecret(e.target.value)}
                    placeholder="Digunakan untuk verifikasi tanda tangan Webhook HMAC"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 text-xs text-slate-100 focus:outline-none focus:border-blue-500 font-mono"
                  />
                </div>

                {/* Form Actions */}
                <div className="pt-3 border-t border-slate-800 flex items-center justify-end gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setShowWaModal(false)}
                    className="text-xs"
                  >
                    Batal
                  </Button>

                  <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    disabled={isSubmittingWa}
                    className="text-xs"
                  >
                    {isSubmittingWa ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                        <span>PROSES...</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-3.5 h-3.5 mr-1.5" />
                        <span>SIMPAN KONEKSI</span>
                      </>
                    )}
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

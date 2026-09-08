import React from "react";
import { MainLayout } from "@/components/layout/MainLayout";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Sliders, Shield, Key } from "lucide-react";

export default function SettingsPage() {
  return (
    <MainLayout>
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-800/60">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h1 className="text-2xl font-bold tracking-tight text-white">Pengaturan</h1>
              <Badge variant="secondary" size="sm">System Shell</Badge>
            </div>
            <p className="text-sm text-slate-400">
              Pengaturan tenant, preferensi sistem, dan integrasi kredensial.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card variant="default">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-blue-400" />
                <CardTitle>Profil Tenant (Demo Placeholder)</CardTitle>
              </div>
              <CardDescription>Pratinjau struktur identitas bisnis</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-xs font-medium text-slate-400 block mb-1">Nama Tenant Placeholder</label>
                <input
                  type="text"
                  value="Demo Merchant Tenant"
                  readOnly
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none cursor-default"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-400 block mb-1">Demo Tenant ID</label>
                <input
                  type="text"
                  value="demo-tenant-01"
                  readOnly
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-400 font-mono focus:outline-none cursor-default"
                />
              </div>
            </CardContent>
          </Card>

          <Card variant="default">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Shield className="w-4 h-4 text-emerald-400" />
                <CardTitle>Keamanan & Hak Akses</CardTitle>
              </div>
              <CardDescription>Konfigurasi keamanan multi-tenant</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950 border border-slate-800">
                <div className="flex items-center gap-2.5">
                  <Key className="w-4 h-4 text-slate-400" />
                  <span className="text-xs font-medium text-slate-300">Isolasi Tenant DB</span>
                </div>
                <Badge variant="outline" size="sm">Backend Core Ready</Badge>
              </div>
              <p className="text-xs text-slate-500">
                Pengaturan integrasi dan auth backend akan dikonfigurasi pada tahap berikutnya.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </MainLayout>
  );
}

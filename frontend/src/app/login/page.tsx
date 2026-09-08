"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Lock, Mail, AlertCircle, Info, Sparkles } from "lucide-react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showForgotModal, setShowForgotModal] = useState(false);

  const { login, authError, clearError } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;

    setIsSubmitting(true);
    clearError();

    try {
      const { redirectTo } = await login(email, password);
      router.push(redirectTo);
    } catch {
      // Error handled via authError state in AuthContext
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen w-full bg-[#090d16] flex items-center justify-center p-4 sm:p-6 lg:p-8">
      {/* Background ambient lighting */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

      <Card className="w-full max-w-md bg-[#0b1120]/90 border-slate-800/90 shadow-2xl backdrop-blur-xl p-6 sm:p-8 relative z-10">
        {/* Header Branding */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-blue-600/20 border border-blue-500/30 text-blue-400 mb-3 shadow-inner">
            <Sparkles className="w-6 h-6" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">AI BOS</h1>
          <p className="text-xs font-semibold text-blue-400 tracking-wider uppercase mt-0.5">
            AI Business Operating System
          </p>

          <div className="mt-6 text-center">
            <h2 className="text-lg font-semibold text-slate-100">Welcome back</h2>
            <p className="text-xs text-slate-400 mt-1">Sign in to your account</p>
          </div>
        </div>

        {/* Error / Alert Banners */}
        {authError && (
          <div
            className={`mb-6 p-3.5 rounded-lg border text-xs flex items-start gap-2.5 ${
              authError.includes("expired")
                ? "bg-amber-950/40 border-amber-800/60 text-amber-300"
                : "bg-red-950/40 border-red-800/60 text-red-300"
            }`}
          >
            {authError.includes("expired") ? (
              <Info className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
            )}
            <div className="flex-1">
              <span className="font-medium">{authError}</span>
            </div>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">Email</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-500">
                <Mail className="w-4 h-4" />
              </div>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="owner@business.com"
                className="w-full pl-9 pr-3 py-2.5 rounded-lg bg-slate-900/90 border border-slate-800 text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">Password</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-500">
                <Lock className="w-4 h-4" />
              </div>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-9 pr-3 py-2.5 rounded-lg bg-slate-900/90 border border-slate-800 text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
              />
            </div>
          </div>

          <Button
            type="submit"
            disabled={isSubmitting}
            className="w-full mt-2 py-2.5 bg-blue-600 hover:bg-blue-500 text-white font-medium text-sm rounded-lg shadow-lg shadow-blue-600/20 transition-all flex items-center justify-center gap-2"
          >
            {isSubmitting ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Signing in...</span>
              </>
            ) : (
              <span>Sign In</span>
            )}
          </Button>
        </form>

        {/* Forgot Password Link */}
        <div className="mt-6 text-center">
          <button
            type="button"
            onClick={() => setShowForgotModal(true)}
            className="text-xs text-slate-400 hover:text-blue-400 transition-colors font-medium focus:outline-none"
          >
            Forgot password?
          </button>
        </div>
      </Card>

      {/* Forgot Password Modal */}
      {showForgotModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <Card className="w-full max-w-sm bg-slate-900 border-slate-800 p-6 space-y-4 text-center">
            <h3 className="text-base font-semibold text-slate-100">Password Reset</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Password resets are managed securely by your organization administrator or platform owner. Please contact support or your account administrator to update your credentials.
            </p>
            <Button
              type="button"
              onClick={() => setShowForgotModal(false)}
              className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg"
            >
              Close
            </Button>
          </Card>
        </div>
      )}
    </div>
  );
}

"use client";

import React from "react";
import { AuthProvider } from "@/lib/auth-context";
import { AuthGuard } from "@/components/auth/AuthGuard";

export const AppProviders: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <AuthProvider>
      <AuthGuard>{children}</AuthGuard>
    </AuthProvider>
  );
};

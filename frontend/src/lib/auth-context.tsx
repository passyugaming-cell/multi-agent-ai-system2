"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import {
  apiPost,
  apiGet,
  setAuthToken,
  getAuthToken,
  setActiveTenantId,
  getActiveTenantId,
  setUnauthorizedHandler,
  ApiError,
} from "@/lib/api";

export interface TenantUser {
  id: string;
  email: string;
}

export interface TenantInfo {
  id: string;
  name: string;
  slug: string;
  lifecycle_state: string;
}

export interface AuthResponse {
  access_token: string;
  token_type?: string;
  user: TenantUser;
  tenants: TenantInfo[];
  active_tenant_id: string | null;
}

export interface SelectTenantResponse {
  access_token: string;
  token_type?: string;
  active_tenant_id: string;
}

interface AuthContextType {
  user: TenantUser | null;
  tenants: TenantInfo[];
  activeTenant: TenantInfo | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  authError: string | null;
  login: (email: string, password: string) => Promise<{ redirectTo: string }>;
  selectTenant: (tenantId: string) => Promise<{ redirectTo: string }>;
  logout: () => Promise<void>;
  clearError: () => void;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<TenantUser | null>(null);
  const [tenants, setTenants] = useState<TenantInfo[]>([]);
  const [activeTenant, setActiveTenant] = useState<TenantInfo | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [authError, setAuthError] = useState<string | null>(null);

  const clearAuthState = useCallback(() => {
    setUser(null);
    setTenants([]);
    setActiveTenant(null);
    setAuthToken(null);
    setActiveTenantId(null);
  }, []);

  const clearError = useCallback(() => {
    setAuthError(null);
  }, []);

  const refreshSession = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      clearAuthState();
      setIsLoading(false);
      return;
    }

    try {
      const data = await apiGet<AuthResponse>("/auth/me", { skipTenantHeader: true });
      setAuthToken(data.access_token);
      setUser(data.user);
      setTenants(data.tenants || []);

      const currentActiveId = getActiveTenantId() || data.active_tenant_id;
      const validTenants = data.tenants || [];

      let matchedTenant: TenantInfo | null = null;
      if (currentActiveId) {
        matchedTenant = validTenants.find((t) => t.id === currentActiveId) || null;
      }

      if (!matchedTenant && validTenants.length === 1) {
        matchedTenant = validTenants[0];
      }

      if (matchedTenant) {
        setActiveTenant(matchedTenant);
        setActiveTenantId(matchedTenant.id);
      } else {
        setActiveTenant(null);
        setActiveTenantId(null);
      }
    } catch (err) {
      clearAuthState();
      if (err instanceof ApiError && err.status === 401) {
        setAuthError("Sesi Anda telah berakhir. Silakan login kembali.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [clearAuthState]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearAuthState();
      setAuthError("Sesi Anda telah berakhir. Silakan login kembali.");
    });

    // Initial session hydration
    /* eslint-disable-next-line react-hooks/set-state-in-effect */
    refreshSession();

    return () => {
      setUnauthorizedHandler(null);
    };
  }, [refreshSession, clearAuthState]);

  const login = async (email: string, password: string): Promise<{ redirectTo: string }> => {
    setAuthError(null);
    try {
      const data = await apiPost<AuthResponse>(
        "/auth/login",
        { email, password },
        { skipTenantHeader: true }
      );

      setAuthToken(data.access_token);
      setUser(data.user);
      const tenantList = data.tenants || [];
      setTenants(tenantList);

      let targetTenant: TenantInfo | null = null;
      if (data.active_tenant_id) {
        targetTenant = tenantList.find((t) => t.id === data.active_tenant_id) || null;
      } else if (tenantList.length === 1) {
        targetTenant = tenantList[0];
      }

      if (targetTenant) {
        setActiveTenant(targetTenant);
        setActiveTenantId(targetTenant.id);
        return { redirectTo: "/" };
      } else {
        setActiveTenant(null);
        setActiveTenantId(null);
        return { redirectTo: "/select-tenant" };
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setAuthError(err.message);
      } else {
        setAuthError("Gagal melakukan login. Silakan coba lagi.");
      }
      throw err;
    }
  };

  const selectTenant = async (tenantId: string): Promise<{ redirectTo: string }> => {
    setAuthError(null);
    try {
      const data = await apiPost<SelectTenantResponse>(
        "/auth/select-tenant",
        { tenant_id: tenantId },
        { skipTenantHeader: true }
      );

      setAuthToken(data.access_token);
      setActiveTenantId(data.active_tenant_id);

      const targetTenant = tenants.find((t) => t.id === data.active_tenant_id) || null;
      setActiveTenant(targetTenant);

      return { redirectTo: "/" };
    } catch (err) {
      if (err instanceof ApiError) {
        setAuthError(err.message);
      } else {
        setAuthError("Gagal memilih bisnis. Silakan coba lagi.");
      }
      throw err;
    }
  };

  const logout = async (): Promise<void> => {
    try {
      await apiPost("/auth/logout", {}, { skipTenantHeader: true });
    } catch {
      // Ignore logout errors
    } finally {
      clearAuthState();
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        tenants,
        activeTenant,
        isAuthenticated: !!user,
        isLoading,
        authError,
        login,
        selectTenant,
        logout,
        clearError,
        refreshSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};

/**
 * Centralized API Client for AI BOS Frontend.
 * Ensures all requests include:
 * - Authorization: Bearer <JWT>
 * - X-Tenant-ID: <Active Tenant ID>
 */

export interface ApiErrorDetail {
  code?: string;
  message: string;
  status: number;
}

export class ApiError extends Error {
  public status: number;
  public code?: string;
  public isNetworkError: boolean;

  constructor(message: string, status: number, code?: string, isNetworkError: boolean = false) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.isNetworkError = isNetworkError;
  }
}

type UnauthorizedHandler = () => void;

let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  unauthorizedHandler = handler;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("aibos_token");
}

export function setAuthToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) {
    localStorage.setItem("aibos_token", token);
  } else {
    localStorage.removeItem("aibos_token");
  }
}

export function getActiveTenantId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("aibos_active_tenant_id");
}

export function setActiveTenantId(tenantId: string | null) {
  if (typeof window === "undefined") return;
  if (tenantId) {
    localStorage.setItem("aibos_active_tenant_id", tenantId);
  } else {
    localStorage.removeItem("aibos_active_tenant_id");
  }
}

export interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
  skipTenantHeader?: boolean;
}

export async function apiFetch<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, skipTenantHeader = false, headers: customHeaders, ...restOptions } = options;

  let url = endpoint.startsWith("http") ? endpoint : `${API_BASE_URL}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
        searchParams.append(key, String(value));
      }
    });
    const queryString = searchParams.toString();
    if (queryString) {
      url += (url.includes("?") ? "&" : "?") + queryString;
    }
  }

  const token = getAuthToken();
  const activeTenantId = getActiveTenantId();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(customHeaders as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  if (!skipTenantHeader && activeTenantId) {
    headers["X-Tenant-ID"] = activeTenantId;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...restOptions,
      headers,
    });
  } catch {
    throw new ApiError(
      "Gagal terhubung ke server. Periksa koneksi internet Anda.",
      0,
      "NETWORK_ERROR",
      true
    );
  }

  if (!response.ok) {
    let errorData: { detail?: string | { code?: string; message?: string }; code?: string; message?: string } = {};
    try {
      errorData = await response.json();
    } catch {
      // Non-JSON response
    }

    let errorMessage = "Terjadi kesalahan pada server.";
    let errorCode: string | undefined = undefined;

    if (typeof errorData.detail === "string") {
      errorMessage = errorData.detail;
    } else if (typeof errorData.detail === "object" && errorData.detail !== null) {
      errorMessage = errorData.detail.message || errorMessage;
      errorCode = errorData.detail.code;
    } else if (errorData.message) {
      errorMessage = errorData.message;
      errorCode = errorData.code;
    }

    if (response.status === 401) {
      if (unauthorizedHandler) {
        unauthorizedHandler();
      }
      throw new ApiError(
        errorMessage || "Sesi Anda telah berakhir. Silakan login kembali.",
        401,
        errorCode || "UNAUTHORIZED"
      );
    }

    if (response.status === 403) {
      throw new ApiError(
        errorMessage || "Anda tidak memiliki akses ke sumber daya ini.",
        403,
        errorCode || "FORBIDDEN"
      );
    }

    if (response.status === 404) {
      throw new ApiError(
        errorMessage || "Data tidak ditemukan.",
        404,
        errorCode || "NOT_FOUND"
      );
    }

    if (response.status === 429) {
      throw new ApiError(
        errorMessage || "Terlalu banyak permintaan. Silakan tunggu beberapa saat.",
        429,
        errorCode || "RATE_LIMITED"
      );
    }

    if (response.status >= 500) {
      throw new ApiError(
        errorMessage || "Terjadi kesalahan internal server.",
        response.status,
        errorCode || "SERVER_ERROR"
      );
    }

    throw new ApiError(errorMessage, response.status, errorCode);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  return response.json() as Promise<T>;
}

export function apiGet<T>(endpoint: string, options?: RequestOptions): Promise<T> {
  return apiFetch<T>(endpoint, { ...options, method: "GET" });
}

export function apiPost<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
  return apiFetch<T>(endpoint, {
    ...options,
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export function apiPut<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
  return apiFetch<T>(endpoint, {
    ...options,
    method: "PUT",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export function apiPatch<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
  return apiFetch<T>(endpoint, {
    ...options,
    method: "PATCH",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export function apiDelete<T>(endpoint: string, options?: RequestOptions): Promise<T> {
  return apiFetch<T>(endpoint, { ...options, method: "DELETE" });
}

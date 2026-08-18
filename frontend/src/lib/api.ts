/**
 * The single HTTP client.
 *
 * Two jobs beyond wrapping axios: attach the bearer token, and turn the
 * backend's error envelope into one `ApiError` type so no screen ever has to
 * dig through `err.response.data.error.message` itself.
 */

import axios, { AxiosError, type AxiosInstance } from "axios";

import type { ApiErrorBody } from "@/types/api";

/** A failure from the API, already unwrapped. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Field-level messages from a 422, if the failure was validation. */
  get fieldErrors(): { field: string; message: string }[] {
    if (Array.isArray(this.details)) {
      return this.details as { field: string; message: string }[];
    }
    return [];
  }

  get isAuthError(): boolean {
    return this.status === 401;
  }

  get isPermissionError(): boolean {
    return this.status === 403;
  }
}

const TOKEN_KEY = "designops.token";

export function getStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    // Private-mode browsers can throw on storage access. An unreadable token
    // is the same as no token, so sign-in simply happens again.
    return null;
  }
}

export function setStoredToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable; the session stays in memory only */
  }
}

/** Called when the API rejects our token, so the app can sign the user out. */
let onUnauthenticated: (() => void) | null = null;
export function setUnauthenticatedHandler(handler: () => void): void {
  onUnauthenticated = handler;
}

export const http: AxiosInstance = axios.create({
  // Empty base means same-origin "/api", which the Vite proxy handles in dev
  // and a platform rewrite handles in production.
  baseURL: import.meta.env.VITE_API_BASE_URL || "",
  timeout: 30_000,
  headers: { "Content-Type": "application/json" },
});

http.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorBody>) => {
    if (error.response) {
      const body = error.response.data;
      const envelope = body?.error;

      // A rejected token means the session is over, whatever the caller was
      // doing. Clearing it here keeps every screen from having to check.
      if (error.response.status === 401) {
        setStoredToken(null);
        onUnauthenticated?.();
      }

      throw new ApiError(
        error.response.status,
        envelope?.code ?? `http_${error.response.status}`,
        envelope?.message ?? error.message ?? "Request failed.",
        envelope?.details,
      );
    }

    if (error.code === "ECONNABORTED") {
      throw new ApiError(0, "timeout", "The request timed out. Please try again.");
    }

    throw new ApiError(
      0,
      "network_error",
      "Could not reach the server. Check that the API is running.",
    );
  },
);

/** Strip empty filter values so they never reach the query string. */
export function cleanParams(
  params: Record<string, unknown> | undefined,
): Record<string, unknown> {
  if (!params) return {};
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value) && value.length === 0) continue;
    out[key] = value;
  }
  return out;
}

export async function get<T>(
  url: string,
  params?: Record<string, unknown>,
): Promise<T> {
  const { data } = await http.get<T>(url, { params: cleanParams(params) });
  return data;
}

export async function post<T>(
  url: string,
  body?: unknown,
  params?: Record<string, unknown>,
): Promise<T> {
  const { data } = await http.post<T>(url, body, { params: cleanParams(params) });
  return data;
}

export async function patch<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await http.patch<T>(url, body);
  return data;
}

export async function put<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await http.put<T>(url, body);
  return data;
}

export async function del<T>(url: string): Promise<T> {
  const { data } = await http.delete<T>(url);
  return data;
}

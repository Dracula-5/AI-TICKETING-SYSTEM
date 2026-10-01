import axios, { AxiosError, type AxiosRequestConfig } from "axios";

import type { TokenOut } from "./types";

/**
 * HTTP client.
 *
 * The access token lives only in memory (never localStorage), so an XSS bug
 * cannot read a long-lived credential out of storage. Sessions survive reloads
 * through the httpOnly refresh cookie: on 401 the client calls /auth/refresh
 * once — concurrent 401s share the same refresh — and retries the request.
 */
export const API_BASE = "/api/v1";

/**
 * Public origin of the API when the SPA is hosted on a static host that proxies
 * /api over HTTP but cannot proxy WebSockets (Netlify), e.g.
 * "https://nexadesk-api.onrender.com". Empty when nginx serves SPA and API together.
 */
export const API_ORIGIN = (import.meta.env.VITE_API_ORIGIN ?? "").trim().replace(/\/+$/, "");

/** Notification WebSocket URL: the API origin when set, otherwise this page's host. */
export function notificationSocketUrl(apiOrigin: string = API_ORIGIN, page: Location = window.location): string {
  if (apiOrigin) return `${apiOrigin.replace(/^http/, "ws")}${API_BASE}/notifications/ws`;
  const scheme = page.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${page.host}${API_BASE}/notifications/ws`;
}

export const api = axios.create({ baseURL: API_BASE, withCredentials: true });

let accessToken: string | null = null;
let refreshInFlight: Promise<string | null> | null = null;
let onSessionExpired: () => void = () => {};

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

export function setSessionExpiredHandler(handler: () => void) {
  onSessionExpired = handler;
}

export function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = axios
      .post<TokenOut>(`${API_BASE}/auth/refresh`, null, { withCredentials: true })
      .then((res) => {
        setAccessToken(res.data.access_token);
        return res.data.access_token;
      })
      .catch(() => {
        setAccessToken(null);
        return null;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

api.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

type RetriableConfig = AxiosRequestConfig & { _retried?: boolean };

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const config = error.config as RetriableConfig | undefined;
    const isAuthCall = config?.url?.startsWith("/auth/");
    if (error.response?.status === 401 && config && !config._retried && !isAuthCall) {
      config._retried = true;
      const token = await refreshAccessToken();
      if (token) {
        return api.request(config);
      }
      onSessionExpired();
    }
    return Promise.reject(error);
  },
);

/** Human-readable message from any API error (FastAPI `detail` or validation list). */
export function errorMessage(error: unknown, fallback = "Something went wrong. Please try again."): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) return "Can't reach the server. Check your connection and try again.";
    const detail = (error.response.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string; loc?: (string | number)[] };
      const field = first.loc?.filter((p) => p !== "body").join(".");
      const msg = (first.msg ?? "").replace(/^Value error, /, "");
      return field ? `${field}: ${msg}` : msg;
    }
    if (error.response.status === 429) return "Too many attempts. Wait a minute and try again.";
  }
  return fallback;
}

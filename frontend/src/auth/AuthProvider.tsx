import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { refreshAccessToken, setAccessToken, setSessionExpiredHandler } from "../api/client";
import { authApi } from "../api/endpoints";
import type { Me, TokenOut } from "../api/types";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: Status;
  me: Me | null;
  can: (permission: string) => boolean;
  /** Where the public-page guard sends a user who just signed in (null = their home page). */
  nextPath: string | null;
  /** Store a freshly issued token (login/register/accept-invite) and load the profile. */
  startSession: (tokens: TokenOut, next?: string) => Promise<Me>;
  login: (email: string, password: string, next?: string) => Promise<Me>;
  logout: () => Promise<void>;
  reloadMe: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [me, setMe] = useState<Me | null>(null);
  const [nextPath, setNextPath] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const clear = useCallback(() => {
    setAccessToken(null);
    setMe(null);
    setNextPath(null);
    setStatus("anonymous");
    queryClient.clear();
  }, [queryClient]);

  // Restore the session from the refresh cookie on first load.
  useEffect(() => {
    let cancelled = false;
    setSessionExpiredHandler(clear);
    refreshAccessToken()
      .then((token) => (token ? authApi.me() : null))
      .then((profile) => {
        if (cancelled) return;
        setMe(profile);
        setStatus(profile ? "authenticated" : "anonymous");
      })
      .catch(() => !cancelled && clear());
    return () => {
      cancelled = true;
    };
  }, [clear]);

  const startSession = useCallback(async (tokens: TokenOut, next?: string) => {
    setAccessToken(tokens.access_token);
    const profile = await authApi.me();
    setNextPath(next ?? null);
    setMe(profile);
    setStatus("authenticated");
    return profile;
  }, []);

  const login = useCallback(
    async (email: string, password: string, next?: string) => startSession(await authApi.login(email, password), next),
    [startSession],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      clear();
    }
  }, [clear]);

  const reloadMe = useCallback(async () => {
    setMe(await authApi.me());
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      me,
      can: (permission) => !!me?.permissions.includes(permission),
      nextPath,
      startSession,
      login,
      logout,
      reloadMe,
    }),
    [status, me, nextPath, startSession, login, logout, reloadMe],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

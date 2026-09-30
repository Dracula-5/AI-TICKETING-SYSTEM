import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { API_BASE, getAccessToken, refreshAccessToken } from "../api/client";
import type { NotificationItem } from "../api/types";

const MAX_BACKOFF_MS = 30_000;

/**
 * Live notification feed. Authenticates with its first message (the token is
 * never put in the URL), reconnects with exponential backoff, and on each
 * push refreshes the queries that the event could have changed.
 */
export function useNotificationSocket(enabled: boolean, onNotification?: (n: NotificationItem) => void) {
  const queryClient = useQueryClient();
  const callback = useRef(onNotification);
  useEffect(() => {
    callback.current = onNotification;
  }, [onNotification]);

  useEffect(() => {
    if (!enabled || typeof WebSocket === "undefined") return;
    let socket: WebSocket | null = null;
    let stopped = false;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let keepalive: ReturnType<typeof setInterval> | undefined;

    const connect = async () => {
      const token = getAccessToken() ?? (await refreshAccessToken());
      if (stopped || !token) return;
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${window.location.host}${API_BASE}/notifications/ws`);
      socket.onopen = () => socket?.send(JSON.stringify({ type: "auth", token }));
      socket.onmessage = (event) => {
        const msg = JSON.parse(event.data as string) as { type: string; data?: NotificationItem };
        if (msg.type === "ready") {
          attempt = 0;
          keepalive = setInterval(() => socket?.readyState === WebSocket.OPEN && socket.send("ping"), 25_000);
          return;
        }
        if (msg.type === "notification" && msg.data) {
          queryClient.invalidateQueries({ queryKey: ["notifications"] });
          queryClient.invalidateQueries({ queryKey: ["tickets"] });
          queryClient.invalidateQueries({ queryKey: ["ticket"] });
          callback.current?.(msg.data);
        }
      };
      socket.onclose = () => {
        clearInterval(keepalive);
        if (stopped) return;
        const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** attempt++);
        timer = setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      clearInterval(keepalive);
      socket?.close();
    };
  }, [enabled, queryClient]);
}

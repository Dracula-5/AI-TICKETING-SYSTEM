import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { getAuthItem } from "../utils/authSession";
import {
  listNotifications,
  getUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
} from "../api/notifications";

// Default value doubles as the fallback for anything rendered outside the
// provider (e.g. component tests that mount a page directly) -- the bell
// just shows zero/empty instead of crashing.
const NotificationContext = createContext({
  notifications: [],
  unreadCount: 0,
  markRead: () => {},
  markAllRead: () => {},
});

export function NotificationProvider({ children }) {
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const wsRef = useRef(null);

  useEffect(() => {
    const token = getAuthItem("token");
    if (!token) return undefined;

    listNotifications().then((res) => setNotifications(res.data || [])).catch(() => {});
    getUnreadCount().then((res) => setUnreadCount(res.data?.count || 0)).catch(() => {});

    const base = (process.env.REACT_APP_API_BASE_URL || "http://127.0.0.1:8000").replace(/^http/, "ws");
    const ws = new WebSocket(`${base}/notifications/ws?token=${encodeURIComponent(token)}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const entry = JSON.parse(event.data);
        setNotifications((prev) => [entry, ...prev]);
        setUnreadCount((prev) => prev + 1);
      } catch {
        // ignore malformed frames
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, []);

  const markRead = useCallback((notificationId) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === notificationId ? { ...n, is_read: true } : n))
    );
    setUnreadCount((prev) => Math.max(0, prev - 1));
    markNotificationRead(notificationId).catch(() => {});
  }, []);

  const markAllRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
    markAllNotificationsRead().catch(() => {});
  }, []);

  const value = useMemo(
    () => ({ notifications, unreadCount, markRead, markAllRead }),
    [notifications, unreadCount, markRead, markAllRead]
  );

  return <NotificationContext.Provider value={value}>{children}</NotificationContext.Provider>;
}

export function useNotifications() {
  return useContext(NotificationContext);
}

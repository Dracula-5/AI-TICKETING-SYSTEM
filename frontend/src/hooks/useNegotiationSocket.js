import { useCallback, useEffect, useRef, useState } from "react";
import { getAuthItem } from "../utils/authSession";

export default function useNegotiationSocket(sessionId) {
  const [liveMessages, setLiveMessages] = useState([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);

  useEffect(() => {
    if (!sessionId) return undefined;

    const base = (process.env.REACT_APP_API_BASE_URL || "http://127.0.0.1:8000").replace(/^http/, "ws");
    const token = getAuthItem("token");
    const ws = new WebSocket(`${base}/negotiations/${sessionId}/ws?token=${encodeURIComponent(token || "")}`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setLiveMessages((prev) => [...prev, data]);
      } catch {
        // ignore malformed frames
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [sessionId]);

  const send = useCallback((payload) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
    }
  }, []);

  return { liveMessages, connected, send };
}

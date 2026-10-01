import { Alert } from "@mui/material";
import { useEffect, useState } from "react";

import { API_ORIGIN } from "../api/client";

/**
 * Free-tier hosting puts the API to sleep when idle; waking it takes a few
 * minutes, longer than a static host's /api proxy waits (Netlify: 26 s). When the
 * API has its own origin, ping its /health directly — that also wakes it — and
 * explain the wait instead of letting the first requests fail silently.
 */
export function ServerWakeBanner({
  apiOrigin = API_ORIGIN,
  showAfterMs = 4000,
  retryMs = 10_000,
}: {
  apiOrigin?: string;
  showAfterMs?: number;
  retryMs?: number;
}) {
  const [waking, setWaking] = useState(false);

  useEffect(() => {
    if (!apiOrigin) return;
    let stopped = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const slow = setTimeout(() => !stopped && setWaking(true), showAfterMs);
    const ping = () => {
      // no-cors: the response is opaque, but it resolving at all means the server answers.
      fetch(`${apiOrigin}/health`, { mode: "no-cors", cache: "no-store" })
        .then(() => {
          if (stopped) return;
          clearTimeout(slow);
          setWaking(false);
        })
        .catch(() => {
          if (!stopped) retry = setTimeout(ping, retryMs);
        });
    };
    ping();
    return () => {
      stopped = true;
      clearTimeout(slow);
      clearTimeout(retry);
    };
  }, [apiOrigin, showAfterMs, retryMs]);

  if (!waking) return null;
  return (
    <Alert severity="info" role="status" sx={{ borderRadius: 0, justifyContent: "center" }}>
      The free demo server is starting up — this can take 2–3 minutes after a quiet period. The page
      works as soon as it is ready.
    </Alert>
  );
}

import { useEffect } from "react";
import { Button } from "@mui/material";
import "../styles/successAnimation.css";

const CONFETTI_COUNT = 10;
const CONFETTI_COLORS = ["#6366f1", "#f43f5e", "#10b981", "#f59e0b", "#d946ef", "#0ea5e9"];

/**
 * Celebration overlay for a completed action (ticket raised, order placed,
 * deal accepted, ...). A checkmark draws itself in, a ring pulses out from
 * it, and a handful of confetti dots burst outward -- then it either
 * auto-dismisses or waits for the primary action.
 */
export default function SuccessAnimation({
  open,
  title = "Success!",
  message,
  primaryLabel = "Done",
  onPrimary,
  autoCloseMs = 0,
}) {
  useEffect(() => {
    if (!open || !autoCloseMs) return undefined;
    const timer = setTimeout(() => onPrimary?.(), autoCloseMs);
    return () => clearTimeout(timer);
  }, [open, autoCloseMs, onPrimary]);

  if (!open) return null;

  return (
    <div className="success-overlay">
      <div className="success-card">
        <div className="success-mark-wrap">
          <div className="success-confetti">
            {Array.from({ length: CONFETTI_COUNT }).map((_, i) => (
              <span
                key={i}
                className="success-confetti-dot"
                style={{
                  "--angle": `${(360 / CONFETTI_COUNT) * i}deg`,
                  background: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
                }}
              />
            ))}
          </div>
          <div className="success-ring"></div>
          <svg className="success-check" viewBox="0 0 52 52">
            <circle className="success-check-circle" cx="26" cy="26" r="24" fill="none" />
            <path className="success-check-mark" fill="none" d="M14 27l7 7 17-17" />
          </svg>
        </div>

        <h2 className="success-title">{title}</h2>
        {message && <p className="success-message">{message}</p>}

        <Button variant="contained" size="large" onClick={onPrimary} className="success-primary-btn">
          {primaryLabel}
        </Button>
      </div>
    </div>
  );
}

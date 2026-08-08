import { useEffect, useState } from "react";
import "../styles/splashIntro.css";

const HOLD_MS = 1800;
const EXIT_MS = 550;

/**
 * One-time boot animation shown while the app first mounts (not on every
 * SPA route change -- App only mounts once per hard page load). Sits as an
 * overlay above the already-rendering app so there's no blank flash once
 * it clears. Skippable via the "Skip" button, and skipped entirely for
 * prefers-reduced-motion.
 */
export default function SplashIntro({ onDone }) {
  const [exiting, setExiting] = useState(false);
  const [hidden, setHidden] = useState(false);

  const prefersReducedMotion =
    typeof window !== "undefined" &&
    Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches);

  useEffect(() => {
    if (prefersReducedMotion) {
      setHidden(true);
      onDone?.();
      return undefined;
    }

    const holdTimer = setTimeout(() => setExiting(true), HOLD_MS);
    return () => clearTimeout(holdTimer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!exiting) return undefined;
    const exitTimer = setTimeout(() => {
      setHidden(true);
      onDone?.();
    }, EXIT_MS);
    return () => clearTimeout(exitTimer);
  }, [exiting, onDone]);

  function skip() {
    if (!exiting) setExiting(true);
  }

  if (hidden || prefersReducedMotion) return null;

  return (
    <div className={`splash-intro${exiting ? " splash-exiting" : ""}`}>
      <div className="splash-orb splash-orb-1"></div>
      <div className="splash-orb splash-orb-2"></div>
      <div className="splash-orb splash-orb-3"></div>
      <div className="splash-grid"></div>

      <div className="splash-content">
        <div className="splash-mark-wrap">
          <div className="splash-mark">
            <span>T</span>
          </div>
          <div className="splash-mark-ring"></div>
          <div className="splash-splash-ring"></div>
          <span className="splash-droplet splash-droplet-1"></span>
          <span className="splash-droplet splash-droplet-2"></span>
          <span className="splash-droplet splash-droplet-3"></span>
          <span className="splash-droplet splash-droplet-4"></span>
          <span className="splash-droplet splash-droplet-5"></span>
          <span className="splash-droplet splash-droplet-6"></span>
        </div>
        <h1 className="splash-wordmark">TicketMind</h1>
        <p className="splash-tagline">AI ticketing &amp; a marketplace, in one workspace</p>
        <div className="splash-loader">
          <span></span>
          <span></span>
          <span></span>
        </div>
      </div>

      <button type="button" className="splash-skip" onClick={skip} aria-label="Skip intro">
        Skip
      </button>
    </div>
  );
}

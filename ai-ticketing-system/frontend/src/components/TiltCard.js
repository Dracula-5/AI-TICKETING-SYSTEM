import { useRef } from "react";

const MAX_TILT_DEG = 8;

/**
 * Wraps children in a perspective container and tilts them toward the
 * pointer on hover, like a physical card catching light. Pure CSS
 * transforms (GPU-friendly), resets smoothly on pointer leave. Disabled
 * for touch/coarse pointers where there's no hover to track.
 */
export default function TiltCard({ children, className = "", maxTilt = MAX_TILT_DEG, glare = true, style }) {
  const cardRef = useRef(null);
  const frameRef = useRef(null);

  function handlePointerMove(e) {
    if (e.pointerType === "touch") return;
    const card = cardRef.current;
    if (!card) return;

    if (frameRef.current) cancelAnimationFrame(frameRef.current);
    frameRef.current = requestAnimationFrame(() => {
      const rect = card.getBoundingClientRect();
      const px = (e.clientX - rect.left) / rect.width;
      const py = (e.clientY - rect.top) / rect.height;
      const rotateY = (px - 0.5) * 2 * maxTilt;
      const rotateX = (0.5 - py) * 2 * maxTilt;
      card.style.transform = `rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateZ(0)`;
      if (glare) {
        card.style.setProperty("--glare-x", `${px * 100}%`);
        card.style.setProperty("--glare-y", `${py * 100}%`);
        card.style.setProperty("--glare-opacity", "1");
      }
    });
  }

  function handlePointerLeave() {
    const card = cardRef.current;
    if (!card) return;
    card.style.transform = "rotateX(0deg) rotateY(0deg) translateZ(0)";
    card.style.setProperty("--glare-opacity", "0");
  }

  return (
    <div className="perspective-wrap">
      <div
        ref={cardRef}
        className={`tilt-card ${className}`}
        style={style}
        onPointerMove={handlePointerMove}
        onPointerLeave={handlePointerLeave}
      >
        {children}
      </div>
    </div>
  );
}

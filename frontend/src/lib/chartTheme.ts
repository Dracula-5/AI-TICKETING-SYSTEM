// Chart tokens (dataviz reference palette). Categorical slots are assigned in
// this fixed order and never cycled; validated on the #ffffff card surface
// with validate_palette.js (slots 1-2: all checks pass, worst CVD ΔE 24.7).
export const SERIES = ["#2a78d6", "#eb6834"] as const;

export const CHART = {
  surface: "#ffffff",
  grid: "#e5e7eb", // hairline, solid
  axis: "#d1d5db",
  inkPrimary: "#111827",
  inkSecondary: "#4b5563",
  inkMuted: "#6b7280",
  barSize: 18, // <= 24px thick
} as const;

// Status palette: reserved for meaning (never a series), always shipped with icon + label.
export const STATUS_COLOR = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
} as const;

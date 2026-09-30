import { differenceInMinutes, format, formatDistanceToNowStrict, isValid, parseISO } from "date-fns";

export function toDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const d = parseISO(value);
  return isValid(d) ? d : null;
}

export function formatDateTime(value: string | null | undefined): string {
  const d = toDate(value);
  return d ? format(d, "d MMM yyyy, HH:mm") : "—";
}

export function formatRelative(value: string | null | undefined): string {
  const d = toDate(value);
  return d ? `${formatDistanceToNowStrict(d)} ago` : "—";
}

/** "in 3h 20m" / "2h 5m overdue" relative to now. */
export function formatDue(value: string | null | undefined, now: Date = new Date()): string {
  const d = toDate(value);
  if (!d) return "—";
  const minutes = differenceInMinutes(d, now);
  const text = formatMinutes(Math.abs(minutes));
  return minutes >= 0 ? `in ${text}` : `${text} overdue`;
}

export function formatMinutes(total: number): string {
  if (total > 0 && total < 1) return "<1m";
  if (total < 60) return `${Math.max(0, Math.round(total))}m`;
  const days = Math.floor(total / 1440);
  const hours = Math.floor((total % 1440) / 60);
  const minutes = Math.round(total % 60);
  if (days > 0) return hours ? `${days}d ${hours}h` : `${days}d`;
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ticketRef(n: number): string {
  return `#${n}`;
}

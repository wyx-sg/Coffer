import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** A Date -> "YYYY-MM-DD HH:mm:ss" in local time. */
export function formatLocalDateTime(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(
    d.getHours(),
  )}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/**
 * An ISO timestamp -> "YYYY-MM-DD HH:mm:ss" in local time. Locale-
 * independent on purpose — no English "PM" / "ago" leaking into the UI.
 */
export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  // Invalid input (malformed ISO, empty string, NaN) — return the raw
  // value so the UI doesn't paint "NaN-NaN-NaN NaN:NaN:NaN".
  if (Number.isNaN(d.getTime())) return iso;
  return formatLocalDateTime(d);
}

/**
 * Humanize a byte count as "B / KB / MB / GB" (binary, base-1024). Bytes stay
 * exact; larger units show one decimal (e.g. 1536 -> "1.5 KB"). Locale-
 * independent on purpose. Negative / non-finite input falls back to "0 B".
 */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  // Bytes are whole; larger units show one decimal, trimming a trailing ".0".
  const text = unit === 0 ? String(Math.round(value)) : value.toFixed(1).replace(/\.0$/, "");
  return `${text} ${units[unit]}`;
}

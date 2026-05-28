import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
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
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(
    d.getHours(),
  )}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

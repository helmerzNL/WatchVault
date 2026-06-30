// Small presentation helpers.
//
// Dates/times are always rendered in the device's local timezone and locale
// (`toLocale*` with `undefined` locale). The one trap is a date-only string like
// "2025-03-14": `new Date("2025-03-14")` parses as UTC midnight, which renders as
// the *previous* day in negative-offset timezones. `parseLocalDate` builds such
// dates in local time to avoid that off-by-one.

export function parseLocalDate(iso: string): Date {
  const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(iso);
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3] || "1"));
  return new Date(iso);
}

// Locale tag (e.g. "nl", "de") that drives the *language* of written-out dates.
// Set from the app's selected language so month/date names follow the in-app
// language rather than the browser locale. The timezone is never overridden, so
// dates still render in the device's local timezone.
let formatLocale: string | undefined = undefined;

export function setFormatLocale(lang?: string): void {
  formatLocale = lang || undefined;
}

export function localeTag(): string | undefined {
  return formatLocale;
}

// Local calendar date as YYYY-MM-DD (not UTC), for "today/yesterday" pickers.
export function localDateKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function todayLocalKey(): string {
  return localDateKey(new Date());
}

export function fmtHours(h: number): string {
  const n = Number(h);
  if (!n || Number.isNaN(n)) return "0h";
  if (n < 1) return `${Math.round(n * 60)}m`;
  if (n < 10) return `${n.toFixed(1)}h`;
  return `${Math.round(n)}h`;
}

export function fmtNum(n: number): string {
  return new Intl.NumberFormat().format(Number(n) || 0);
}

export function fmtDate(iso: string): string {
  try {
    return parseLocalDate(iso).toLocaleDateString(formatLocale, { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return iso;
  }
}

export function fmtMonth(iso: string): string {
  // iso like 2025-03-01 or 2025-03
  return parseLocalDate(iso).toLocaleDateString(formatLocale, { month: "short", year: "numeric" });
}

export function monthKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function monthLabel(key: string): string {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString(formatLocale, { month: "long", year: "numeric" });
}

export function initials(name: string): string {
  return (name || "?")
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() || "")
    .join("");
}

export const ACCENTS: { name: string; value: string }[] = [
  { name: "Blue", value: "#0a84ff" },
  { name: "Indigo", value: "#5e5ce6" },
  { name: "Purple", value: "#bf5af2" },
  { name: "Pink", value: "#ff2d55" },
  { name: "Red", value: "#ff3b30" },
  { name: "Orange", value: "#ff9f0a" },
  { name: "Yellow", value: "#ffd60a" },
  { name: "Green", value: "#30d158" },
  { name: "Teal", value: "#40c8e0" },
];

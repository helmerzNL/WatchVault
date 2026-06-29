// Small presentation helpers.

export function fmtHours(h: number): string {
  if (!h) return "0h";
  if (h < 1) return `${Math.round(h * 60)}m`;
  if (h < 10) return `${h.toFixed(1)}h`;
  return `${Math.round(h)}h`;
}

export function fmtNum(n: number): string {
  return new Intl.NumberFormat().format(n ?? 0);
}

export function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return iso;
  }
}

export function fmtMonth(iso: string): string {
  // iso like 2025-03-01 or 2025-03
  const d = new Date(iso.length === 7 ? iso + "-01" : iso);
  return d.toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

export function monthKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function monthLabel(key: string): string {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });
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

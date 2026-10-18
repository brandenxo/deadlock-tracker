// Display formatting. null always renders as an em dash: "not computable" is not 0%.
export const MISSING = "—";
const integer = new Intl.NumberFormat("en-US");

export function pct(value: number | null, digits = 1): string {
  return value === null ? MISSING : `${(value * 100).toFixed(digits)}%`;
}

export function count(value: number): string {
  return integer.format(value);
}

export function duration(seconds: number | null): string {
  if (seconds === null) return MISSING;
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function age(hours: number): string {
  if (hours < 1.5) return `${Math.max(1, Math.round(hours * 60))} min ago`;
  if (hours < 48) return `${Math.round(hours)} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

// "± 1.2" : half the width of the 95% range, in percentage points.
export function margin(low: number | null, high: number | null): string {
  return low === null || high === null ? MISSING : `± ${(((high - low) / 2) * 100).toFixed(1)}`;
}

export const ROLE_LABELS = {
  brawler: "Brawler",
  marksman: "Marksman",
  mystic: "Mystic",
  assassin: "Assassin",
} as const;

// Fetches data/summary.json (same origin, static) and derives the per-hero numbers.
import { tierOf, wilson } from "./stats";
import type { HeroDaily, HeroInfo, HeroRow, SeriesPoint, Summary, UtcDate } from "./types";

export const SUMMARY_URL = "/data/summary.json";

export class LoadError extends Error {}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// Runtime shape check: the static types can't validate fetched JSON.
export function parseSummary(body: unknown): Summary {
  if (!isObject(body) || body.schema_version !== 1) throw new LoadError("Unsupported data format.");
  const coverage = body.coverage;
  if (!isObject(coverage) || !Array.isArray(coverage.covered_dates)) {
    throw new LoadError("Data file is missing coverage.");
  }
  if (!Array.isArray(body.hero_daily) || !Array.isArray(body.daily_matches) || !isObject(body.heroes)) {
    throw new LoadError("Data file is missing counters.");
  }
  for (const row of body.hero_daily) {
    if (!isObject(row) || typeof row.date !== "string" || typeof row.appearances !== "number") {
      throw new LoadError("Data file has a malformed hero row.");
    }
  }
  return body as unknown as Summary;
}

export async function fetchSummary(signal?: AbortSignal): Promise<Summary | null> {
  let response: Response;
  try {
    response = await fetch(SUMMARY_URL, { signal: signal ?? null });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new LoadError("Could not reach the server. Check your connection and retry.");
  }
  // A missing object comes back as 403 through OAC; treat it as "not published yet".
  if (response.status === 403 || response.status === 404) return null;
  if (!response.ok) throw new LoadError(`The server answered ${response.status}.`);
  return parseSummary(await response.json());
}

const ratio = (numerator: number, denominator: number) =>
  denominator === 0 ? null : numerator / denominator;

export function heroInfo(summary: Summary, heroId: number): HeroInfo {
  return summary.heroes[String(heroId)] ?? { name: `Hero ${heroId}`, type: null, image: null };
}

function toRow(info: HeroInfo, heroId: number, rows: HeroDaily[], eligibleMatches: number): HeroRow {
  const sum = (key: keyof Omit<HeroDaily, "date" | "hero_id">) =>
    rows.reduce((total, r) => total + r[key], 0);
  const appearances = sum("appearances");
  const wins = sum("wins");
  const durationCount = sum("duration_count");
  const matchesWithHero = sum("matches_with_hero");
  const range = wilson(wins, appearances);
  return {
    ...info,
    hero_id: heroId,
    appearances,
    wins,
    win_rate: ratio(wins, appearances),
    win_low: range?.low ?? null,
    win_high: range?.high ?? null,
    tier: tierOf(wins, appearances),
    matches_with_hero: matchesWithHero,
    pick_rate: ratio(matchesWithHero, eligibleMatches),
    duration_count: durationCount,
    avg_duration_s: ratio(sum("duration_sum_s"), durationCount),
  };
}

export function datesBetween(summary: Summary, from: UtcDate, to: UtcDate): UtcDate[] {
  return summary.coverage.covered_dates.filter((d) => d >= from && d <= to);
}

export function eligibleMatches(summary: Summary, dates: UtcDate[]): number {
  const wanted = new Set(dates);
  return summary.daily_matches
    .filter((d) => wanted.has(d.date))
    .reduce((total, d) => total + d.eligible_matches, 0);
}

// Per-hero totals across `dates`.
export function heroTotals(summary: Summary, dates: UtcDate[]): HeroRow[] {
  const wanted = new Set(dates);
  const byHero = new Map<number, HeroDaily[]>();
  for (const row of summary.hero_daily) {
    if (!wanted.has(row.date)) continue;
    byHero.set(row.hero_id, [...(byHero.get(row.hero_id) ?? []), row]);
  }
  const matches = eligibleMatches(summary, dates);
  return [...byHero].map(([heroId, rows]) => toRow(heroInfo(summary, heroId), heroId, rows, matches));
}

// Daily series for one hero over all covered dates; unplayed days have null rates.
export function heroSeries(summary: Summary, heroId: number): SeriesPoint[] {
  return summary.coverage.covered_dates.map((date) => {
    const rows = summary.hero_daily.filter((r) => r.date === date && r.hero_id === heroId);
    return { date, ...toRow(heroInfo(summary, heroId), heroId, rows, eligibleMatches(summary, [date])) };
  });
}

export const STALE_AFTER_HOURS = 3;

export function ageHours(builtAt: string, now: Date = new Date()): number {
  return (now.getTime() - Date.parse(builtAt)) / 3_600_000;
}

import type { HeroDaily, Mode, Summary } from "../types";

const day = (date: string, hero_id: number, appearances: number, wins: number,
  duration_sum_s: number, duration_count: number): HeroDaily =>
  ({ date, hero_id, appearances, wins, duration_sum_s, duration_count, matches_with_hero: appearances });

// Two covered days: Abrams (6) heavily played, Bebop (15) moderately, Haze (13) barely
// and only in matches without a valid duration.
export function summaryFixture(overrides: Partial<Summary> = {}): Summary {
  return {
    schema_version: 1,
    built_at: new Date(Date.now() - 20 * 60_000).toISOString(),
    source: { manifest_version: 629, manifest_generated_at: "2026-10-07T06:00:00Z" },
    coverage: {
      settle_lag_hours: 6,
      status_by_date: { "2026-10-05": "covered", "2026-10-06": "covered", "2026-10-07": "partial" },
      covered_dates: ["2026-10-05", "2026-10-06"],
    },
    players_per_team: 6,
    daily_matches: [
      { date: "2026-10-05", eligible_matches: 300 },
      { date: "2026-10-06", eligible_matches: 200 },
    ],
    hero_daily: [
      day("2026-10-05", 6, 120, 80, 216000, 120),
      day("2026-10-06", 6, 30, 10, 54000, 30),
      day("2026-10-05", 15, 40, 18, 72000, 40),
      day("2026-10-06", 13, 5, 4, 0, 0),
    ],
    heroes: {
      "6": { name: "Abrams", type: "brawler", image: null },
      "13": { name: "Haze", type: "assassin", image: null },
      "15": { name: "Bebop", type: "brawler", image: null },
    },
    excluded_matches: { incomplete_roster: 3 },
    ...overrides,
  };
}

const modeDay = (mode: Mode, ...args: Parameters<typeof day>): HeroDaily => ({ ...day(...args), match_mode: mode });

// Schema 2: the same totals as summaryFixture, split by match mode. Abrams is the only
// hero with unranked games (40 of them, 20 wins, across 100 unranked matches).
export function modeSummaryFixture(overrides: Partial<Summary> = {}): Summary {
  return summaryFixture({
    schema_version: 2,
    daily_matches: [
      { date: "2026-10-05", match_mode: "Ranked", eligible_matches: 200 },
      { date: "2026-10-05", match_mode: "Unranked", eligible_matches: 100 },
      { date: "2026-10-06", match_mode: "Ranked", eligible_matches: 200 },
    ],
    hero_daily: [
      modeDay("Ranked", "2026-10-05", 6, 80, 60, 144000, 80),
      modeDay("Unranked", "2026-10-05", 6, 40, 20, 72000, 40),
      modeDay("Ranked", "2026-10-06", 6, 30, 10, 54000, 30),
      modeDay("Ranked", "2026-10-05", 15, 40, 18, 72000, 40),
      modeDay("Ranked", "2026-10-06", 13, 5, 4, 0, 0),
    ],
    ...overrides,
  });
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

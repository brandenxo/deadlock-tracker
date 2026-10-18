// Shape of data/summary.json, written by pipeline/summary.py.
// Rules:
//   * Only additive counters are stored. Rates are computed here, over the selected
//     dates, as sum(numerator) / sum(denominator), never as an average of daily rates.
//   * A zero denominator gives null ("not computable"), never 0%.
//   * Dates are UTC "YYYY-MM-DD" strings, never Date objects, so a viewer's time zone
//     can't shift a day.

export type UtcDate = string;
export type Role = "brawler" | "marksman" | "mystic" | "assassin";

export interface HeroDaily {
  date: UtcDate;
  hero_id: number;
  appearances: number;
  wins: number;
  duration_sum_s: number;
  duration_count: number;
  matches_with_hero: number;
}

export interface HeroInfo {
  name: string;
  type: Role | null;
  image: string | null;
}

export interface Summary {
  schema_version: 1;
  built_at: string;
  source: { manifest_version: number; manifest_generated_at: string };
  coverage: {
    settle_lag_hours: number;
    status_by_date: Record<UtcDate, "covered" | "partial" | "absent">;
    covered_dates: UtcDate[];
  };
  players_per_team: number;
  daily_matches: { date: UtcDate; eligible_matches: number }[];
  hero_daily: HeroDaily[];
  heroes: Record<string, HeroInfo>; // keyed by hero_id as a string
  excluded_matches: Record<string, number>;
}

export type Tier = "S" | "A" | "B" | "C" | "D";

// What the UI shows for one hero over a set of dates.
export interface HeroRow extends HeroInfo {
  hero_id: number;
  appearances: number;
  wins: number;
  win_rate: number | null;
  win_low: number | null; // 95% confidence range for the win rate
  win_high: number | null;
  tier: Tier | null; // null = not enough games to say
  matches_with_hero: number;
  pick_rate: number | null;
  duration_count: number;
  avg_duration_s: number | null;
}

export interface SeriesPoint extends HeroRow {
  date: UtcDate;
}

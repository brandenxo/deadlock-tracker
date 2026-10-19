// Types for data/summary.json (produced by pipeline/summary.py).
//   * The file holds sums only; rates are computed client-side as sum/sum over the
//     selected days, never as a mean of daily rates.
//   * Division by zero yields null, displayed as unknown rather than 0%.
//   * Dates stay as UTC "YYYY-MM-DD" strings so local time zones can't shift them.

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
    // Minutes of upstream data missing on otherwise-complete days. Absent in older
    // summaries, hence optional.
    gap_minutes_by_date?: Record<UtcDate, number>;
  };
  players_per_team: number;
  daily_matches: { date: UtcDate; eligible_matches: number }[];
  hero_daily: HeroDaily[];
  heroes: Record<string, HeroInfo>; // JSON keys: stringified hero_id
  excluded_matches: Record<string, number>;
}

export type Tier = "S" | "A" | "B" | "C" | "D";

// Per-hero aggregate for the selected date range.
export interface HeroRow extends HeroInfo {
  hero_id: number;
  appearances: number;
  wins: number;
  win_rate: number | null;
  win_low: number | null; // 95% interval bounds
  win_high: number | null;
  tier: Tier | null; // null when below the game threshold
  matches_with_hero: number;
  pick_rate: number | null;
  duration_count: number;
  avg_duration_s: number | null;
}

export interface SeriesPoint extends HeroRow {
  date: UtcDate;
}

import { lazy, Suspense } from "react";
import { count, duration, pct, ROLE_LABELS } from "../format";
import type { HeroRow, SeriesPoint } from "../types";
import { HeroAvatar } from "./HeroAvatar";

// Recharts dominates bundle size, so the chart is code-split.
const TrendChart = lazy(() =>
  import("./TrendChart").then((module) => ({ default: module.TrendChart })),
);

// Detail view for the selected hero: headline rate, interval, stats, daily trend.
export function HeroPanel({ hero, series }: { hero: HeroRow; series: SeriesPoint[] }) {
  return (
    <aside className="panel" aria-labelledby="panel-title">
      <div className="panel-head">
        <HeroAvatar hero={hero} size="large" />
        <div>
          <h2 id="panel-title">{hero.name}</h2>
          <p className="panel-role">
            {hero.type ? ROLE_LABELS[hero.type] : "Role unknown"}
            {hero.tier ? `, tier ${hero.tier}` : ", not rated yet"}
          </p>
        </div>
      </div>
      <p className="panel-rate">
        <span className="panel-rate-value">{pct(hero.win_rate)}</span>
        <span className="panel-rate-label">win rate</span>
      </p>
      {hero.win_low !== null && hero.win_high !== null && (
        <p className="panel-range">
          Probably between {pct(hero.win_low)} and {pct(hero.win_high)}, based on{" "}
          {count(hero.appearances)} games.
        </p>
      )}
      <dl className="panel-stats">
        <div>
          <dt>Games</dt>
          <dd>{count(hero.appearances)}</dd>
        </div>
        <div>
          <dt>Pick rate</dt>
          <dd>{pct(hero.pick_rate)}</dd>
        </div>
        <div>
          <dt>Avg length</dt>
          <dd>{duration(hero.avg_duration_s)}</dd>
        </div>
      </dl>
      <Suspense fallback={<p className="loading">Loading chart…</p>}>
        <TrendChart name={hero.name} series={series} />
      </Suspense>
    </aside>
  );
}

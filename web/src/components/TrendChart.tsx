import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SeriesPoint } from "../types";
import { count, duration, pct } from "../format";

// One hero, one measure, one axis: win rate per covered UTC date.
//  * The axis spans at least 40-60%: win rates sit near 50%, so 0-100% draws a flat line.
//  * Sample size isn't drawn on a second axis (two axes invite false correlations); it's
//    in the tooltip and in the table below, which is also the screen-reader view.

interface TooltipProps {
  active?: boolean;
  payload?: { payload: SeriesPoint }[];
}

function PointTooltip({ active, payload }: TooltipProps) {
  const point = active ? payload?.[0]?.payload : undefined;
  if (!point) return null;
  return (
    <div className="chart-tooltip">
      <div className="tt-date">{point.date} (UTC)</div>
      <div>
        Win rate <strong>{pct(point.win_rate)}</strong>
      </div>
      <div className="muted">
        {count(point.wins)} wins / {count(point.appearances)} appearances
      </div>
    </div>
  );
}

export function TrendChart({ name, series }: { name: string; series: SeriesPoint[] }) {
  // Recharts skips null values, leaving a visible gap for days with no appearances
  // instead of drawing a fake 0% point.
  const data = series.map((p) => ({ ...p, win_rate_pct: p.win_rate === null ? null : p.win_rate * 100 }));
  return (
    <figure className="trend">
      <figcaption>
        <span className="trend-title">Win rate by day</span>
        <span className="muted">The dashed line marks 50%.</span>
      </figcaption>
      <div className="chart-box" aria-hidden="true">
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data} margin={{ top: 12, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="date" tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
              tickLine={false} axisLine={{ stroke: "var(--axis)" }} />
            <YAxis domain={[(low: number) => Math.min(40, Math.floor(low / 5) * 5),
              (high: number) => Math.max(60, Math.ceil(high / 5) * 5)]} unit="%" width={44}
              tick={{ fill: "var(--text-secondary)", fontSize: 12 }} tickLine={false} axisLine={false} />
            <ReferenceLine y={50} stroke="var(--axis)" strokeDasharray="4 4" />
            <Tooltip content={<PointTooltip />} cursor={{ stroke: "var(--axis)", strokeWidth: 1 }} />
            <Line type="linear" dataKey="win_rate_pct" stroke="var(--line-series)" strokeWidth={2}
              dot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)", fill: "var(--line-series)" }}
              activeDot={{ r: 6, strokeWidth: 2, stroke: "var(--surface)" }}
              connectNulls={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <details className="chart-table">
        <summary>Show the numbers</summary>
        <table>
          <caption className="visually-hidden">{name} by UTC date</caption>
          <thead>
            <tr>
              <th scope="col">Date (UTC)</th>
              <th scope="col" className="num">Win rate</th>
              <th scope="col" className="num">Wins</th>
              <th scope="col" className="num">Games</th>
              <th scope="col" className="num">Pick rate</th>
              <th scope="col" className="num">Avg length</th>
            </tr>
          </thead>
          <tbody>
            {series.map((p) => (
              <tr key={p.date}>
                <th scope="row">{p.date}</th>
                <td className="num">{pct(p.win_rate)}</td>
                <td className="num">{count(p.wins)}</td>
                <td className="num">{count(p.appearances)}</td>
                <td className="num">{pct(p.pick_rate)}</td>
                <td className="num">{duration(p.avg_duration_s)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

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

// Daily win rate for one hero.
//  * Y axis covers at least 40-60%; a full 0-100% scale would flatten the line.
//  * Game counts live in the tooltip and the table, not a second axis. The table also
//    serves as the accessible version of the chart.

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
  // null leaves a gap in the line for days without games, rather than plotting 0%.
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

import { useMemo, useState } from "react";
import { count, duration, margin, pct, ROLE_LABELS } from "../format";
import type { HeroRow } from "../types";
import { HeroAvatar } from "./HeroAvatar";

type SortKey = "name" | "win_rate" | "appearances" | "pick_rate" | "avg_duration_s";
type Direction = "ascending" | "descending";

interface Column {
  key: SortKey;
  label: string;
  numeric: boolean;
  firstDirection: Direction; // direction on first click
}

const COLUMNS: Column[] = [
  { key: "name", label: "Hero", numeric: false, firstDirection: "ascending" },
  { key: "win_rate", label: "Win rate", numeric: true, firstDirection: "descending" },
  { key: "appearances", label: "Games", numeric: true, firstDirection: "descending" },
  { key: "pick_rate", label: "Pick rate", numeric: true, firstDirection: "descending" },
  { key: "avg_duration_s", label: "Avg length", numeric: true, firstDirection: "descending" },
];

// Nulls sort last regardless of direction; hero_id breaks ties so ordering is stable.
export function sortHeroes(rows: HeroRow[], key: SortKey, direction: Direction): HeroRow[] {
  const sign = direction === "ascending" ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (key === "name") return a.name.localeCompare(b.name) * sign || a.hero_id - b.hero_id;
    const x = a[key];
    const y = b[key];
    if (x === null && y === null) return a.hero_id - b.hero_id;
    if (x === null) return 1;
    if (y === null) return -1;
    return (x - y) * sign || a.hero_id - b.hero_id;
  });
}

// Diverging bar centered on 50%: right/sapphire above, left/amber below. The track only
// covers 40-60%, since that's where hero win rates actually fall.
function WinRateCell({ row }: { row: HeroRow }) {
  if (row.win_rate === null) return <span className="muted">{pct(null)}</span>;
  const delta = Math.max(-0.1, Math.min(0.1, row.win_rate - 0.5));
  return (
    <span className="winrate">
      <span className="winrate-value">{pct(row.win_rate)}</span>
      <span className="winrate-margin">{margin(row.win_low, row.win_high)}</span>
      <span className="winrate-track" aria-hidden="true">
        <span
          className={`winrate-bar ${delta >= 0 ? "above" : "below"}`}
          style={{ width: `${(Math.abs(delta) / 0.1) * 50}%` }}
        />
      </span>
    </span>
  );
}

export function HeroTable({
  rows,
  selected,
  onSelect,
}: {
  rows: HeroRow[];
  selected: number | null;
  onSelect: (heroId: number) => void;
}) {
  const [sort, setSort] = useState<{ key: SortKey; direction: Direction }>({
    key: "appearances",
    direction: "descending",
  });
  const sorted = useMemo(() => sortHeroes(rows, sort.key, sort.direction), [rows, sort]);

  function toggle(column: Column) {
    setSort((current) =>
      current.key === column.key
        ? { key: column.key, direction: current.direction === "ascending" ? "descending" : "ascending" }
        : { key: column.key, direction: column.firstDirection },
    );
  }

  return (
    <div className="table-scroll" role="region" aria-label="Hero statistics" tabIndex={0}>
      <table className="heroes">
        <caption className="visually-hidden">
          Hero statistics for the selected dates. Column headers sort the table.
        </caption>
        <thead>
          <tr>
            {COLUMNS.map((column) => (
              <th
                key={column.key}
                scope="col"
                aria-sort={sort.key === column.key ? sort.direction : "none"}
                className={column.numeric ? "num" : undefined}
              >
                <button type="button" className="sort" onClick={() => toggle(column)}>
                  {column.label}
                  <span className="sort-mark" aria-hidden="true">
                    {sort.key === column.key ? (sort.direction === "ascending" ? "▲" : "▼") : ""}
                  </span>
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={row.hero_id} className={row.hero_id === selected ? "selected" : undefined}>
              <th scope="row">
                <button
                  type="button"
                  className="hero-pick"
                  aria-pressed={row.hero_id === selected}
                  onClick={() => onSelect(row.hero_id)}
                >
                  <HeroAvatar hero={row} />
                  <span className="hero-pick-text">
                    <span className="hero-name">
                      {row.name}
                      {row.tier && (
                        <span className={`tier-badge tier-${row.tier}`} aria-label={`tier ${row.tier}`}>
                          {row.tier}
                        </span>
                      )}
                    </span>
                    <span className="hero-role">{row.type ? ROLE_LABELS[row.type] : "Role unknown"}</span>
                  </span>
                </button>
              </th>
              <td className="num">
                <WinRateCell row={row} />
              </td>
              <td className="num">{count(row.appearances)}</td>
              <td className="num">{pct(row.pick_rate)}</td>
              <td className="num">{duration(row.avg_duration_s)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

import { useCallback, useEffect, useMemo, useState } from "react";
import { HeroPanel } from "./components/HeroPanel";
import { HeroTable } from "./components/HeroTable";
import { RangePicker } from "./components/RangePicker";
import { RoleFilter } from "./components/RoleFilter";
import { TierBoard } from "./components/TierBoard";
import { age, count } from "./format";
import {
  ageHours,
  datesBetween,
  eligibleMatches,
  fetchSummary,
  heroSeries,
  heroTotals,
  STALE_AFTER_HOURS,
} from "./summary";
import type { Role, Summary, UtcDate } from "./types";

type Load =
  | { state: "loading" }
  | { state: "empty" }
  | { state: "error"; message: string }
  | { state: "ready"; summary: Summary };

// Loads the summary on mount and on each retry. Aborts in-flight requests on unmount
// so a late response can't update a gone component.
function useSummary(): [Load, () => void] {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoad({ state: "loading" });
    fetchSummary(controller.signal).then(
      (summary) =>
        setLoad(
          summary && summary.coverage.covered_dates.length > 0
            ? { state: "ready", summary }
            : { state: "empty" },
        ),
      (error: unknown) => {
        if (!controller.signal.aborted) setLoad({ state: "error", message: String((error as Error).message) });
      },
    );
    return () => controller.abort();
  }, [attempt]);
  return [load, useCallback(() => setAttempt((n) => n + 1), [])];
}

function Freshness({ summary }: { summary: Summary }) {
  const hours = ageHours(summary.built_at);
  const stale = hours > STALE_AFTER_HOURS;
  return (
    <p className={`status ${stale ? "status-stale" : ""}`} role={stale ? "status" : undefined}>
      <span className="status-icon" aria-hidden="true">{stale ? "▲" : "●"}</span>
      <strong>{stale ? "Data is stale." : "Up to date."}</strong> Updated {age(hours)}.
      {stale && " The hourly update hasn't succeeded recently."}
    </p>
  );
}

function Dashboard({ summary }: { summary: Summary }) {
  const covered = summary.coverage.covered_dates;
  const [range, setRange] = useState({ from: covered[0]!, to: covered[covered.length - 1]! });
  const [role, setRole] = useState<Role | null>(null);
  const [selected, setSelected] = useState<number | null>(null);

  const dates = useMemo(() => datesBetween(summary, range.from, range.to), [summary, range]);
  const all = useMemo(() => heroTotals(summary, dates), [summary, dates]);
  const rows = useMemo(() => (role ? all.filter((r) => r.type === role) : all), [all, role]);
  // Default selection: most-played hero in view.
  const mostPlayed = [...rows].sort((a, b) => b.appearances - a.appearances || a.hero_id - b.hero_id)[0];
  const hero = rows.find((r) => r.hero_id === selected) ?? mostPlayed;
  const matches = eligibleMatches(summary, dates);
  const gaps = dates.flatMap((d) => {
    const minutes = summary.coverage.gap_minutes_by_date?.[d];
    return minutes ? [`${minutes} min on ${d}`] : [];
  });

  return (
    <>
      <section className="controls" aria-label="Filters">
        <RangePicker
          covered={covered}
          from={range.from}
          to={range.to}
          onChange={(from: UtcDate, to: UtcDate) => setRange({ from, to })}
        />
        <RoleFilter role={role} onChange={setRole} />
        <p className="sample">
          <strong>{count(matches)}</strong> matches over {dates.length} {dates.length === 1 ? "day" : "days"}
        </p>
      </section>
      {gaps.length > 0 && (
        <p className="gap-note">
          The data source is missing {gaps.join(", ")} (UTC), so match counts there read slightly
          low. Win rates barely change.
        </p>
      )}
      <TierBoard rows={rows} selected={hero?.hero_id ?? null} onSelect={setSelected} />
      <div className="layout">
        <HeroTable rows={rows} selected={hero?.hero_id ?? null} onSelect={setSelected} />
        {hero && <HeroPanel hero={hero} series={heroSeries(summary, hero.hero_id)} />}
      </div>
    </>
  );
}

export function App() {
  const [load, retry] = useSummary();
  return (
    <div className="page">
      <header className="masthead">
        <div className="masthead-inner">
          <div>
            <h1>Hero Ledger</h1>
            <p className="lede">
              Deadlock win rates from public matches, rebuilt every hour. Every rate shows the games
              behind it.
            </p>
          </div>
          {load.state === "ready" && <Freshness summary={load.summary} />}
        </div>
      </header>
      <main>
        {load.state === "loading" && <p className="loading" aria-live="polite">Loading hero statistics…</p>}
        {load.state === "empty" && (
          <div className="notice">
            <p>
              <strong>No complete day of data yet.</strong> A UTC day is published once the pipeline
              holds all of it plus a few hours for late matches. Check back after the next hourly run.
            </p>
          </div>
        )}
        {load.state === "error" && (
          <div className="notice error" role="alert">
            <p>
              <strong>Could not load the hero table.</strong> {load.message}
            </p>
            <button type="button" onClick={retry}>Retry</button>
          </div>
        )}
        {load.state === "ready" && <Dashboard summary={load.summary} />}
      </main>
      <footer className="colophon">
        <p>
          Match data and hero portraits from the community Deadlock API. Deadlock and its art belong
          to Valve; this site isn't affiliated with Valve or the Deadlock API project. Win rates
          describe this sample of matches, not what causes wins.
        </p>
      </footer>
    </div>
  );
}

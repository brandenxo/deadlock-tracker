import { describe, expect, it } from "vitest";
import { ageHours, datesBetween, eligibleMatches, hasModes, heroSeries, heroTotals, parseSummary } from "../summary";
import { modeSummaryFixture, summaryFixture } from "./fixtures";

const summary = summaryFixture();
const both = ["2026-10-05", "2026-10-06"];

describe("heroTotals", () => {
  it("weights a multi-day win rate by games, not by averaging daily rates", () => {
    const abrams = heroTotals(summary, both).find((r) => r.hero_id === 6)!;
    expect(abrams.win_rate).toBe(90 / 150); // 60%
    const daily = (80 / 120 + 10 / 30) / 2; // unweighted mean, 50%: incorrect
    expect(abrams.win_rate).not.toBeCloseTo(daily);
  });

  it("uses eligible matches across the whole range for pick rate", () => {
    const bebop = heroTotals(summary, both).find((r) => r.hero_id === 15)!;
    expect(bebop.pick_rate).toBe(40 / 500);
  });

  it("returns null, not 0, when there is nothing to divide by", () => {
    const haze = heroTotals(summary, both).find((r) => r.hero_id === 13)!;
    expect(haze.avg_duration_s).toBeNull();
    expect(haze.win_rate).toBe(0.8);
  });

  it("attaches names and roles, with a placeholder for unknown heroes", () => {
    const rows = heroTotals({ ...summary, heroes: {} }, both);
    expect(rows.find((r) => r.hero_id === 6)!.name).toBe("Hero 6");
    expect(heroTotals(summary, both).find((r) => r.hero_id === 6)!.type).toBe("brawler");
  });

  it("only counts the selected dates", () => {
    const rows = heroTotals(summary, ["2026-10-06"]);
    expect(rows.map((r) => r.name).sort()).toEqual(["Abrams", "Haze"]);
  });
});

describe("heroSeries", () => {
  it("has a point per covered date, with null on days the hero wasn't played", () => {
    const series = heroSeries(summary, 15);
    expect(series.map((p) => p.date)).toEqual(both);
    expect(series[1]!.win_rate).toBeNull();
    expect(series[1]!.appearances).toBe(0);
  });
});

describe("datesBetween", () => {
  it("never includes a partial day", () => {
    expect(datesBetween(summary, "2026-10-05", "2026-10-07")).toEqual(both);
  });
});

describe("match modes", () => {
  const split = modeSummaryFixture();

  it("gives the same totals as an unsplit summary when no mode is chosen", () => {
    expect(heroTotals(split, both)).toEqual(heroTotals(summary, both));
    expect(eligibleMatches(split, both)).toBe(500);
  });

  it("counts only the chosen mode's games and matches", () => {
    const abrams = heroTotals(split, both, "Unranked").find((r) => r.hero_id === 6)!;
    expect([abrams.appearances, abrams.win_rate, abrams.pick_rate]).toEqual([40, 0.5, 40 / 100]);
    expect(heroTotals(split, both, "Unranked").map((r) => r.hero_id)).toEqual([6]);
    expect(eligibleMatches(split, both, "Ranked")).toBe(400);
  });

  it("filters the daily series by mode", () => {
    const series = heroSeries(split, 6, "Unranked");
    expect(series.map((p) => p.appearances)).toEqual([40, 0]);
    expect(series[1]!.win_rate).toBeNull();
  });

  it("only offers modes when the summary is split", () => {
    expect(hasModes(split)).toBe(true);
    expect(hasModes(summary)).toBe(false);
  });
});

describe("parseSummary", () => {
  it("accepts both schema versions", () => {
    expect(parseSummary(summary)).toBe(summary);
    expect(parseSummary(modeSummaryFixture()).schema_version).toBe(2);
  });

  it("rejects an unknown format instead of rendering garbage", () => {
    expect(() => parseSummary({ ...summary, schema_version: 3 })).toThrow("Unsupported");
    expect(() => parseSummary({ ...summary, hero_daily: [{ date: 1 }] })).toThrow("malformed");
  });
});

it("measures age from built_at", () => {
  expect(ageHours("2026-10-07T06:00:00Z", new Date("2026-10-07T09:30:00Z"))).toBe(3.5);
});

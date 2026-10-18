import { describe, expect, it } from "vitest";
import { ageHours, datesBetween, heroSeries, heroTotals, parseSummary } from "../summary";
import { summaryFixture } from "./fixtures";

const summary = summaryFixture();
const both = ["2026-10-05", "2026-10-06"];

describe("heroTotals", () => {
  it("weights a multi-day win rate by games, not by averaging daily rates", () => {
    const abrams = heroTotals(summary, both).find((r) => r.hero_id === 6)!;
    expect(abrams.win_rate).toBe(90 / 150); // 60%
    const daily = (80 / 120 + 10 / 30) / 2; // 50%: the wrong answer
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

describe("parseSummary", () => {
  it("rejects an unknown format instead of rendering garbage", () => {
    expect(() => parseSummary({ ...summary, schema_version: 2 })).toThrow("Unsupported");
    expect(() => parseSummary({ ...summary, hero_daily: [{ date: 1 }] })).toThrow("malformed");
  });
});

it("measures age from built_at", () => {
  expect(ageHours("2026-10-07T06:00:00Z", new Date("2026-10-07T09:30:00Z"))).toBe(3.5);
});

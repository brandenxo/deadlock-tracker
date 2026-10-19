import { describe, expect, it } from "vitest";
import { tierOf, wilson } from "../stats";

describe("wilson", () => {
  it("matches the textbook value for 50 wins in 100 games", () => {
    const range = wilson(50, 100)!;
    expect(range.low).toBeCloseTo(0.4038, 4);
    expect(range.high).toBeCloseTo(0.5962, 4);
  });

  it("narrows as games grow, and stays inside 0..1", () => {
    const small = wilson(6, 10)!;
    const large = wilson(6000, 10000)!;
    expect(large.high - large.low).toBeLessThan(small.high - small.low);
    expect(wilson(10, 10)!.high).toBeLessThanOrEqual(1);
    expect(wilson(0, 10)!.low).toBeGreaterThanOrEqual(0);
  });

  it("has no range with no games", () => {
    expect(wilson(0, 0)).toBeNull();
  });
});

describe("tierOf", () => {
  it("rates by how sure we are, not just by the win rate", () => {
    expect(tierOf(5400, 10000)).toBe("S");
    expect(tierOf(5150, 10000)).toBe("A");
    expect(tierOf(515, 1000)).toBe("B"); // same rate, interval still includes 50%
    expect(tierOf(4850, 10000)).toBe("C");
    expect(tierOf(4600, 10000)).toBe("D");
  });

  it("doesn't rate heroes with too few games", () => {
    expect(tierOf(40, 50)).toBeNull();
  });
});

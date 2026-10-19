// Win-rate uncertainty. The same percentage means much less over 50 games than over
// 50,000, so tiers are assigned from a 95% Wilson interval rather than the point value.

export const Z95 = 1.96;
export const MIN_GAMES_FOR_TIER = 100;

// 95% Wilson score interval for wins/games. Unlike the normal approximation it stays
// within [0, 1] and holds up at small n and extreme rates.
export function wilson(wins: number, games: number, z = Z95): { low: number; high: number } | null {
  if (games === 0) return null;
  const p = wins / games;
  const z2 = z * z;
  const center = (p + z2 / (2 * games)) / (1 + z2 / games);
  const margin = (z / (1 + z2 / games)) * Math.sqrt((p * (1 - p)) / games + z2 / (4 * games * games));
  return { low: Math.max(0, center - margin), high: Math.min(1, center + margin) };
}

// S: lower bound >= 52%     A: lower bound > 50%     B: interval contains 50%
// C: upper bound < 50%      D: upper bound < 48%
export function tierOf(wins: number, games: number): "S" | "A" | "B" | "C" | "D" | null {
  if (games < MIN_GAMES_FOR_TIER) return null;
  const range = wilson(wins, games)!;
  if (range.low >= 0.52) return "S";
  if (range.low > 0.5) return "A";
  if (range.high < 0.48) return "D";
  if (range.high < 0.5) return "C";
  return "B";
}

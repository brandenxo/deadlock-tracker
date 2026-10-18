// How sure are we about a win rate? 52% over 50 games and 52% over 50,000 games are
// very different claims. The Wilson score interval gives the range the true win rate
// probably lies in (95% of the time), and the tier is read from that range.

export const Z95 = 1.96;
export const MIN_GAMES_FOR_TIER = 100;

// Wilson score interval for `wins` successes out of `games` trials.
// Better than the textbook p +- 1.96*sqrt(p(1-p)/n): it never leaves [0, 1] and
// behaves well for small samples and for rates near 0% or 100%.
export function wilson(wins: number, games: number, z = Z95): { low: number; high: number } | null {
  if (games === 0) return null;
  const p = wins / games;
  const z2 = z * z;
  const center = (p + z2 / (2 * games)) / (1 + z2 / games);
  const margin = (z / (1 + z2 / games)) * Math.sqrt((p * (1 - p)) / games + z2 / (4 * games * games));
  return { low: Math.max(0, center - margin), high: Math.min(1, center + margin) };
}

// S: even the pessimistic end is 52%+     A: clearly above 50%
// B: can't tell it apart from 50%         C: clearly below 50%    D: even the optimistic end is under 48%
export function tierOf(wins: number, games: number): "S" | "A" | "B" | "C" | "D" | null {
  if (games < MIN_GAMES_FOR_TIER) return null;
  const range = wilson(wins, games)!;
  if (range.low >= 0.52) return "S";
  if (range.low > 0.5) return "A";
  if (range.high < 0.48) return "D";
  if (range.high < 0.5) return "C";
  return "B";
}

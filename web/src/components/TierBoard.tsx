import { pct } from "../format";
import { MIN_GAMES_FOR_TIER } from "../stats";
import type { HeroRow, Tier } from "../types";
import { HeroAvatar } from "./HeroAvatar";

const TIERS: { tier: Tier; meaning: string }[] = [
  { tier: "S", meaning: "Wins at least 52% even at the low end of its range" },
  { tier: "A", meaning: "Clearly above 50%" },
  { tier: "B", meaning: "Can't be told apart from 50%" },
  { tier: "C", meaning: "Clearly below 50%" },
  { tier: "D", meaning: "Under 48% even at the high end of its range" },
];

export function TierBoard({
  rows,
  selected,
  onSelect,
}: {
  rows: HeroRow[];
  selected: number | null;
  onSelect: (heroId: number) => void;
}) {
  const unrated = rows.filter((r) => r.tier === null);
  return (
    <section className="tiers" aria-labelledby="tiers-title">
      <h2 id="tiers-title">Tiers</h2>
      <p className="tiers-note">
        A tier says how sure we are a hero wins more or less than half its games, not just how high
        its win rate is. Heroes with fewer than {MIN_GAMES_FOR_TIER} games aren't rated.
      </p>
      <ol className="tier-rows">
        {TIERS.map(({ tier, meaning }) => {
          const heroes = rows
            .filter((r) => r.tier === tier)
            .sort((a, b) => (b.win_rate ?? 0) - (a.win_rate ?? 0) || a.hero_id - b.hero_id);
          return (
            <li key={tier} className={`tier tier-${tier}`}>
              <div className="tier-label">
                <span className="tier-letter">{tier}</span>
                <span className="tier-meaning">{meaning}</span>
              </div>
              <ul className="tier-heroes">
                {heroes.length === 0 && <li className="tier-empty">No heroes</li>}
                {heroes.map((hero) => (
                  <li key={hero.hero_id}>
                    <button
                      type="button"
                      className="tile"
                      aria-pressed={hero.hero_id === selected}
                      onClick={() => onSelect(hero.hero_id)}
                    >
                      <HeroAvatar hero={hero} />
                      <span className="tile-name">{hero.name}</span>
                      <span className="tile-rate">{pct(hero.win_rate)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ol>
      {unrated.length > 0 && (
        <p className="tiers-unrated">
          Not enough games yet: {unrated.map((r) => r.name).join(", ")}.
        </p>
      )}
    </section>
  );
}

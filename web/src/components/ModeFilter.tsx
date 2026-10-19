import type { Mode } from "../types";

const MODES: Mode[] = ["Ranked", "Unranked"];

// Match-mode toggles ("All" + Ranked/Unranked), styled and announced like RoleFilter.
export function ModeFilter({ mode, onChange }: { mode: Mode | null; onChange: (mode: Mode | null) => void }) {
  return (
    <div className="roles" role="group" aria-label="Match mode">
      <button type="button" aria-pressed={mode === null} onClick={() => onChange(null)}>
        All matches
      </button>
      {MODES.map((m) => (
        <button key={m} type="button" aria-pressed={mode === m} onClick={() => onChange(m)}>
          {m}
        </button>
      ))}
    </div>
  );
}

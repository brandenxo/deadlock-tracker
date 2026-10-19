import { ROLE_LABELS } from "../format";
import type { Role } from "../types";

const ROLES = Object.keys(ROLE_LABELS) as Role[];

// Role toggles ("All" + one per role). aria-pressed drives both styling and a11y state.
export function RoleFilter({ role, onChange }: { role: Role | null; onChange: (role: Role | null) => void }) {
  return (
    <div className="roles" role="group" aria-label="Hero role">
      <button type="button" aria-pressed={role === null} onClick={() => onChange(null)}>
        All roles
      </button>
      {ROLES.map((r) => (
        <button key={r} type="button" aria-pressed={role === r} onClick={() => onChange(r)}>
          {ROLE_LABELS[r]}
        </button>
      ))}
    </div>
  );
}

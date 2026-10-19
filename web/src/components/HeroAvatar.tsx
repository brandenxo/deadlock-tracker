import { useState } from "react";
import type { HeroRow } from "../types";

// Portrait with an initials fallback for missing or broken images. Decorative only
// (alt="", aria-hidden): the name is always rendered beside it.
export function HeroAvatar({ hero, size = "small" }: { hero: Pick<HeroRow, "name" | "image" | "type">; size?: "small" | "large" }) {
  const [broken, setBroken] = useState(false);
  const initials = hero.name
    .split(/\s+/)
    .filter((word) => word !== "The" && word !== "&")
    .map((word) => word[0])
    .join("")
    .slice(0, 2);
  return (
    <span className={`avatar avatar-${size} role-${hero.type ?? "unknown"}`} aria-hidden="true">
      {hero.image && !broken ? (
        <img src={hero.image} alt="" loading="lazy" onError={() => setBroken(true)} />
      ) : (
        <span className="avatar-initials">{initials}</span>
      )}
    </span>
  );
}

import { useState } from "react";
import type { HeroRow } from "../types";

// The hero's portrait, or their initials if there's no image (or it fails to load).
// alt="" because the name is always printed right next to it: a screen reader would
// otherwise read every name twice.
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

"""Hero names, roles and portraits, so the dashboard can say "Abrams", not "hero 6".

The match data only has a numeric hero_id. The Deadlock API publishes the game's hero
list at /v1/assets/heroes: one JSON object per hero with `id`, `name`, `hero_type`
(brawler / marksman / mystic / assassin) and `images` (portrait URLs).

Names are cosmetic: if the list can't be fetched, the run still publishes, and the
dashboard falls back to "Hero 6". Bad names must never block good numbers.
"""

from __future__ import annotations

import json

HEROES_MAX_BYTES = 10_000_000
IMAGE_KEYS = ("icon_image_small_webp", "icon_image_small")  # first one present wins


def parse_heroes(raw: bytes) -> dict[int, dict]:
    """Return hero metadata keyed by ID, skipping entries that don't look like heroes."""
    heroes = {}
    for hero in json.loads(raw):
        if not isinstance(hero, dict):
            continue

        hero_id, name = hero.get("id"), hero.get("name")
        if not isinstance(hero_id, int) or not isinstance(name, str) or not name:
            continue

        images = hero.get("images") if isinstance(hero.get("images"), dict) else {}
        image = next(
            (images[key] for key in IMAGE_KEYS if isinstance(images.get(key), str)),
            None,
        )
        hero_type = hero.get("hero_type")
        heroes[hero_id] = {
            "name": name,
            "type": hero_type if isinstance(hero_type, str) else None,
            "image": image if image and image.startswith("https://") else None,
        }
    return heroes


def heroes_for(ids: set[int], known: dict[int, dict]) -> dict[str, dict]:
    """Return the requested entries with string IDs and placeholders for unknown heroes."""
    return {
        str(hero_id): known.get(
            hero_id,
            {"name": f"Hero {hero_id}", "type": None, "image": None},
        )
        for hero_id in sorted(ids)
    }

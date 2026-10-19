"""Map hero_id to display name, role and portrait.

match_player only carries numeric ids. Names come from the Deadlock API's
/v1/assets/heroes list (`id`, `name`, `hero_type`, `images`).

This lookup is optional: if it fails, the run still publishes and the UI shows
"Hero <id>" instead.
"""

from __future__ import annotations

import json

HEROES_MAX_BYTES = 10_000_000
IMAGE_KEYS = ("icon_image_small_webp", "icon_image_small")  # preference order


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

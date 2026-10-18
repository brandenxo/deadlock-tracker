"""Hero metadata: parse the API's shape defensively, fall back to "Hero <id>"."""

import json
from pathlib import Path

from pipeline.heroes import heroes_for, parse_heroes

HEROES_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "heroes.json"


def test_fixture_parses_with_names_and_roles():
    heroes = parse_heroes(HEROES_FIXTURE.read_bytes())
    assert heroes[6] == {"name": "Abrams", "type": "brawler", "image": None}
    assert heroes[69]["name"] == "The Doorman"
    assert len(heroes) == 16


def test_junk_entries_are_skipped_and_only_https_images_kept():
    raw = json.dumps(
        [
            {"id": 1, "name": "Ok", "images": {"icon_image_small": "https://x/1.png"}},
            {"id": 2, "name": "Plain http", "images": {"icon_image_small": "http://x/2.png"}},
            {"id": "3", "name": "string id"},
            {"name": "no id"},
            "not an object",
        ]
    ).encode()
    heroes = parse_heroes(raw)
    assert set(heroes) == {1, 2}
    assert heroes[1]["image"] == "https://x/1.png"
    assert heroes[2]["image"] is None  # a page served over https can't load http images


def test_unknown_ids_get_a_placeholder_name():
    out = heroes_for({6, 99}, {6: {"name": "Abrams", "type": "brawler", "image": None}})
    assert out == {
        "6": {"name": "Abrams", "type": "brawler", "image": None},
        "99": {"name": "Hero 99", "type": None, "image": None},
    }

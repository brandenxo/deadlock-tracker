"""Full runs over a fake source, with a local store and with mocked S3."""

import dataclasses
import json

import boto3
import pytest
from moto import mock_aws

from pipeline import summary
from pipeline.config import Settings
from pipeline.run import run_once
from pipeline.source import SourceClient
from pipeline.storage import LocalStore, S3Store
from tests.helpers import HEROES_FIXTURE, NOW, make_source

# The synthetic source ends 6 h after its last day, so the lag is pinned to match it.
SETTINGS = Settings(window_days=3, settle_lag_s=6 * 3600, heroes_url=HEROES_FIXTURE.as_uri())


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    make_source(root)
    base = root.as_uri()
    return SourceClient(base, f"{base}/v1/manifest.json", sleep=lambda s: None)


def read_summary(store):
    return json.loads(store.get_bytes(summary.SUMMARY_KEY))


def test_run_publishes_only_covered_dates(tmp_path, source):
    store = LocalStore(tmp_path / "data")
    outcome = run_once(SETTINGS, store, source, now=NOW)
    doc = read_summary(store)
    assert doc["coverage"]["covered_dates"] == ["2026-10-05", "2026-10-06"]
    assert doc["coverage"]["status_by_date"]["2026-10-07"] == "partial"
    assert {r["date"] for r in doc["hero_daily"]} == {"2026-10-05", "2026-10-06"}
    assert outcome["new_objects"] > 0
    assert "account_id" not in json.dumps(doc)  # no player ids anywhere
    assert doc["heroes"]["6"]["name"] == "Abrams"
    assert set(doc["heroes"]) == {str(r["hero_id"]) for r in doc["hero_daily"]}


def test_missing_hero_names_do_not_block_publishing(tmp_path, source):
    store = LocalStore(tmp_path / "data")
    broken = dataclasses.replace(SETTINGS, heroes_url=(tmp_path / "nope.json").as_uri())
    run_once(broken, store, source, now=NOW)
    assert read_summary(store)["heroes"]["6"] == {"name": "Hero 6", "type": None, "image": None}
    assert store.list_keys("curated/matches/match_date_utc=2026-10-05/")


def test_second_run_downloads_nothing_and_gives_the_same_numbers(tmp_path, source):
    store = LocalStore(tmp_path / "data")
    run_once(SETTINGS, store, source, now=NOW)
    first = read_summary(store)
    outcome = run_once(SETTINGS, store, source, now=NOW)
    assert outcome["new_objects"] == 0 and outcome["bytes_downloaded"] == 0
    assert read_summary(store)["hero_daily"] == first["hero_daily"]


def test_a_small_cap_reaches_the_same_result_over_several_runs(tmp_path, source):
    full = LocalStore(tmp_path / "full")
    run_once(SETTINGS, full, source, now=NOW)
    capped = LocalStore(tmp_path / "capped")
    settings = dataclasses.replace(SETTINGS, download_cap_bytes=60_000)
    for _ in range(30):
        if run_once(settings, capped, source, now=NOW)["new_objects"] == 0:
            break
    assert read_summary(capped)["hero_daily"] == read_summary(full)["hero_daily"]


def test_failed_validation_keeps_the_previous_summary(tmp_path, source, monkeypatch):
    store = LocalStore(tmp_path / "data")
    run_once(SETTINGS, store, source, now=NOW)
    before = store.get_bytes(summary.SUMMARY_KEY)

    def broken(doc, curation, players_per_team):
        raise summary.ValidationFailed(["simulated"])

    monkeypatch.setattr(summary, "validate", broken)
    with pytest.raises(summary.ValidationFailed):
        run_once(SETTINGS, store, source, now=NOW)
    assert store.get_bytes(summary.SUMMARY_KEY) == before


def test_validation_catches_counters_that_do_not_add_up(tmp_path, source):
    store = LocalStore(tmp_path / "data")
    run_once(SETTINGS, store, source, now=NOW)
    doc = read_summary(store)
    doc["hero_daily"][0]["wins"] += 1  # wins no longer match one winner per match
    with pytest.raises(summary.ValidationFailed, match="wins"):
        summary.validate(doc, _curation_stub(doc), players_per_team=6)


def test_validation_checks_each_match_mode_separately(tmp_path, source):
    store = LocalStore(tmp_path / "data")
    run_once(SETTINGS, store, source, now=NOW)
    doc = read_summary(store)
    assert doc["schema_version"] == 2
    assert {r["match_mode"] for r in doc["daily_matches"]} == {"Ranked", "Unranked"}
    # Day totals still add up, but one ranked row is now filed as unranked.
    row = next(r for r in doc["hero_daily"] if r["match_mode"] == "Ranked")
    row["match_mode"] = "Unranked"
    with pytest.raises(summary.ValidationFailed, match="Ranked"):
        summary.validate(doc, _curation_stub(doc), players_per_team=6)


def _curation_stub(doc):
    from pipeline.curate import Curation

    return Curation(0, doc["hero_daily"], {}, {}, 0)


@mock_aws
def test_same_run_works_against_s3(tmp_path, source):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")
    store = S3Store("test-bucket", s3)
    run_once(SETTINGS, store, source, now=NOW)
    head = s3.head_object(Bucket="test-bucket", Key=summary.SUMMARY_KEY)
    assert head["CacheControl"] == "public, max-age=60"
    assert read_summary(store)["coverage"]["covered_dates"] == ["2026-10-05", "2026-10-06"]

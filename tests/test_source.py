"""Manifest parsing, schema checks, download planning, HTTP client limits."""

import json
from pathlib import Path

import pytest

from pipeline import contract
from pipeline.source import (
    SourceClient,
    SourceError,
    SourceFile,
    UnsupportedSchema,
    check_schema,
    parse_manifest,
    plan_ingest,
)

EXCERPT = Path(__file__).resolve().parent.parent / "fixtures" / "manifest_v629_excerpt.json"


@pytest.fixture
def manifest():
    return parse_manifest(EXCERPT.read_bytes())


def test_real_manifest_excerpt_parses(manifest):
    assert manifest.version == 629
    kinds = {f.kind for f in manifest.files("match_player")}
    assert kinds == {"base", "residual", "delta"}
    delta = next(f for f in manifest.files("match_player") if f.kind == "delta")
    assert delta.lo < delta.hi  # created_at bounds, epoch seconds


def test_contract_types_match_the_real_manifest(manifest):
    check_schema(manifest, "match_player", contract.EXPECTED_MANIFEST_TYPES)  # passes


def test_schema_change_stops_the_run(manifest):
    expected = dict(contract.EXPECTED_MANIFEST_TYPES, hero_id="UInt16")
    with pytest.raises(UnsupportedSchema, match="hero_id"):
        check_schema(manifest, "match_player", expected)


def test_unknown_manifest_format_is_refused():
    with pytest.raises(UnsupportedSchema):
        parse_manifest(json.dumps({"format_version": 2}).encode())


def _manifest_with(files):
    doc = {"format_version": 1, "version": 1, "generated_at": "x",
           "tables": {"t": {"files": files}}}  # fmt: skip
    return parse_manifest(json.dumps(doc).encode())


def _delta(hour, size=100):
    return {"key": f"d{hour}", "kind": "delta", "rows": 1, "bytes": size,
            "lo": hour * 3600, "hi": (hour + 1) * 3600}  # fmt: skip


def test_plan_takes_newest_unheld_deltas_until_the_cap():
    m = _manifest_with([_delta(h) for h in range(10)] + [{"key": "b", "kind": "base",
                        "rows": 9, "bytes": 1}])  # fmt: skip
    plan = plan_ingest(m, "t", held_keys={"d9"}, cap_bytes=250, window_start=3 * 3600)
    assert [f.key for f in plan.to_download] == ["d8", "d7"]  # d9 already held; base files skipped
    assert [f.key for f in plan.skipped_for_cap] == ["d6", "d5", "d4", "d3"]  # deferred
    assert plan.planned_bytes == 200


def test_plan_ignores_deltas_before_the_window():
    m = _manifest_with([_delta(h) for h in range(5)])
    plan = plan_ingest(m, "t", set(), cap_bytes=10_000, window_start=3 * 3600)
    assert {f.key for f in plan.to_download} == {"d3", "d4"}  # d2's hi equals window start


def _client(tmp_path):
    return SourceClient(tmp_path.as_uri(), (tmp_path / "m.json").as_uri(), sleep=lambda s: None)


def test_download_enforces_the_cap_and_leaves_no_partial_file(tmp_path):
    (tmp_path / "obj").write_bytes(b"x" * 5000)
    dest = tmp_path / "out" / "obj"
    with pytest.raises(SourceError, match="cap"):
        _client(tmp_path).download(SourceFile("obj", "delta", 1, 5000, 0, 1), dest, max_bytes=4000)
    assert not dest.exists()


def test_download_rejects_a_size_that_disagrees_with_the_manifest(tmp_path):
    (tmp_path / "obj").write_bytes(b"x" * 10)
    with pytest.raises(SourceError, match="manifest says"):
        _client(tmp_path).download(SourceFile("obj", "delta", 1, 11, 0, 1), tmp_path / "o", 100)

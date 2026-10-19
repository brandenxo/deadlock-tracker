"""Decide which UTC dates have enough source data to publish.

Raw objects carry the [lo, hi) range of source ingest times they contain. Rows for a
match on day D keep arriving after D ends, so each D is judged over D + settle lag:

* covered  - held data reaches the end of that span, with at most max_gap_s missing
* partial  - some data in the span, but not enough
* absent   - none

Only covered dates are published; an undercounted day looks plausible and misleads.
The gap allowance exists because upstream occasionally folds a few minutes of hourly
files into its multi-GB base files, which leaves a hole we can't fill. Missing minutes
are reported in the summary.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

DAY_S = 86_400


def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge half-open intervals; adjacent ones like [a,b) and [b,c) join."""
    merged: list[tuple[int, int]] = []
    for lo, hi in sorted(i for i in intervals if i[1] > i[0]):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def day_start(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())


def window_dates(now: int, window_days: int) -> list[date]:
    """The last window_days UTC dates ending today, oldest first."""
    today = datetime.fromtimestamp(now, UTC).date()
    return [today - timedelta(days=n) for n in range(window_days - 1, -1, -1)]


def _missing(merged: list[tuple[int, int]], need_lo: int, need_hi: int) -> int:
    """Seconds of [need_lo, need_hi) not covered by merged."""
    held = sum(max(0, min(hi, need_hi) - max(lo, need_lo)) for lo, hi in merged)
    return (need_hi - need_lo) - held


def missing_seconds(
    intervals: list[tuple[int, int]], dates: list[date], settle_lag_s: int
) -> dict[str, int]:
    """Missing seconds per date over the day plus settle lag."""
    merged = merge_intervals(intervals)
    return {
        d.isoformat(): _missing(merged, day_start(d), day_start(d) + DAY_S + settle_lag_s)
        for d in dates
    }


def classify(
    intervals: list[tuple[int, int]], dates: list[date], settle_lag_s: int, max_gap_s: int = 0
) -> dict:
    merged = merge_intervals(intervals)
    status = {}
    for d in dates:
        need_lo = day_start(d)
        need_hi = need_lo + DAY_S + settle_lag_s
        # Require data through the end of the settle lag; only interior holes count
        # against max_gap_s.
        reaches_end = any(lo < need_hi <= hi for lo, hi in merged)
        if reaches_end and _missing(merged, need_lo, need_hi) <= max_gap_s:
            status[d.isoformat()] = "covered"
        elif any(lo < need_hi and hi > need_lo for lo, hi in merged):
            status[d.isoformat()] = "partial"
        else:
            status[d.isoformat()] = "absent"
    return status

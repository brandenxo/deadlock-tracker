"""Which UTC dates can we honestly show?

Each raw object holds rows the source ingested in [lo, hi). A match starting on date D
is ingested some time after it starts, so D is:

* covered  - held intervals span all of D plus the settle lag, without gaps;
* partial  - held intervals touch that span but don't cover it;
* absent   - nothing held touches it.

Only covered dates are published. A partial day would show real-looking but
undercounted numbers, which is worse than showing nothing.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

DAY_S = 86_400


def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Union of half-open intervals; touching ones ([a,b) and [b,c)) merge."""
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
    """Today (UTC) and the window_days - 1 days before it, oldest first."""
    today = datetime.fromtimestamp(now, UTC).date()
    return [today - timedelta(days=n) for n in range(window_days - 1, -1, -1)]


def classify(intervals: list[tuple[int, int]], dates: list[date], settle_lag_s: int) -> dict:
    merged = merge_intervals(intervals)
    status = {}
    for d in dates:
        need_lo = day_start(d)
        need_hi = need_lo + DAY_S + settle_lag_s
        if any(lo <= need_lo and hi >= need_hi for lo, hi in merged):
            status[d.isoformat()] = "covered"
        elif any(lo < need_hi and hi > need_lo for lo, hi in merged):
            status[d.isoformat()] = "partial"
        else:
            status[d.isoformat()] = "absent"
    return status

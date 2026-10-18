"""Which dates are safe to publish."""

from datetime import date

from pipeline.coverage import DAY_S, classify, day_start, merge_intervals, window_dates

D = date(2026, 10, 10)
START = day_start(D)
LAG = 6 * 3600


def test_touching_intervals_merge_and_gaps_do_not():
    assert merge_intervals([(0, 10), (10, 20), (25, 30)]) == [(0, 20), (25, 30)]


def test_a_day_is_covered_only_with_the_settle_lag_held():
    full = [(START + h * 3600, START + (h + 1) * 3600) for h in range(30)]  # day + 6 h
    assert classify(full, [D], LAG) == {"2026-10-10": "covered"}
    assert classify(full[:-1], [D], LAG) == {"2026-10-10": "partial"}  # lag not yet held


def test_a_one_hour_gap_makes_the_day_partial():
    held = [(START, START + 5 * 3600), (START + 6 * 3600, START + DAY_S + LAG)]
    assert classify(held, [D], LAG) == {"2026-10-10": "partial"}


def test_untouched_days_are_absent():
    assert classify([(0, 3600)], [D], LAG) == {"2026-10-10": "absent"}


def test_window_is_today_and_the_previous_days_in_utc():
    now = START + 23 * 3600 + 59 * 60  # 23:59 UTC
    assert [d.isoformat() for d in window_dates(now, 3)] == [
        "2026-10-08",
        "2026-10-09",
        "2026-10-10",
    ]

import csv

from src.calibration.events import load_events

FIELDS = ["event_ticker", "open_time", "close_time", "ticker", "floor_strike", "result"]


def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_load_events_keeps_only_hourly_ladders(tmp_path):
    csv_path = tmp_path / "settled.csv"
    _write_csv(csv_path, [
        # valid hourly event, one strike
        {"event_ticker": "HOURLY-1", "open_time": "2026-08-01T00:00:00",
         "close_time": "2026-08-01T01:00:00", "ticker": "HOURLY-1-T1",
         "floor_strike": "100.0", "result": "yes"},
        # 2-hour event, should be filtered out entirely
        {"event_ticker": "DAILY-1", "open_time": "2026-08-01T00:00:00",
         "close_time": "2026-08-01T02:00:00", "ticker": "DAILY-1-T1",
         "floor_strike": "100.0", "result": "yes"},
    ])

    events = load_events(csv_path)

    assert len(events) == 1
    assert events[0].event_ticker == "HOURLY-1"
    assert events[0].open_ts < events[0].close_ts


def test_load_events_drops_strikes_missing_floor_or_result(tmp_path):
    csv_path = tmp_path / "settled.csv"
    _write_csv(csv_path, [
        {"event_ticker": "HOURLY-1", "open_time": "2026-08-01T00:00:00",
         "close_time": "2026-08-01T01:00:00", "ticker": "HOURLY-1-T1",
         "floor_strike": "100.0", "result": "yes"},
        {"event_ticker": "HOURLY-1", "open_time": "2026-08-01T00:00:00",
         "close_time": "2026-08-01T01:00:00", "ticker": "HOURLY-1-T2",
         "floor_strike": "", "result": ""},
    ])

    events = load_events(csv_path)

    assert len(events) == 1
    assert len(events[0].strikes) == 1
    assert events[0].strikes[0].ticker == "HOURLY-1-T1"


def test_load_events_drops_event_with_no_valid_strikes(tmp_path):
    csv_path = tmp_path / "settled.csv"
    _write_csv(csv_path, [
        {"event_ticker": "HOURLY-1", "open_time": "2026-08-01T00:00:00",
         "close_time": "2026-08-01T01:00:00", "ticker": "HOURLY-1-T1",
         "floor_strike": "", "result": ""},
    ])

    events = load_events(csv_path)

    assert events == []

"""Strike selection within a single hourly ladder"""

from __future__ import annotations

from ajax_pmm.calibration.events import Strike


def select_near_money(strikes: list[Strike], spot: float, n: int) -> list[Strike]:
    """The n strikes closest to spot, returned in ascending strike order."""
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    nearest = sorted(strikes, key=lambda s: (abs(s.floor_strike - spot), s.floor_strike))[:n]
    return sorted(nearest, key=lambda s: s.floor_strike)
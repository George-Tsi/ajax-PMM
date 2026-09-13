"""Aggregate per-fill markouts into event-clustered stats"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from ajax_pmm.analysis.ladder_bars import StrikeSeries
from ajax_pmm.analysis.markout import infer_fills, markout_curve


@dataclass(frozen=True)
class HorizonStat:
    """Cross-event statistics for one markout horizon. Prices are dollars, not cents."""

    horizon: int
    mean: float
    se: float
    t_stat: float
    n_events: int
    n_fills: int


def collect_event_markouts(
    series: Sequence[StrikeSeries], horizons: Sequence[int]
) -> dict[int, dict[str, list[float]]]:
    """Markouts grouped by horizon, then by event. Horizons without a full window are dropped."""
    acc: dict[int, dict[str, list[float]]] = {k: defaultdict(list) for k in horizons}
    for s in series:
        for fill in infer_fills(s.bars):
            for k, value in markout_curve(s.bars, fill, horizons).items():
                if value is not None:
                    acc[k][s.event_ticker].append(value)
    return acc


def horizon_stats(acc: dict[int, dict[str, list[float]]]) -> list[HorizonStat]:
    stats = []
    for k in sorted(acc):
        per_event = [sum(v) / len(v) for v in acc[k].values() if v]
        n = len(per_event)
        if n < 2:
            continue
        mean = sum(per_event) / n
        var = sum((x - mean) ** 2 for x in per_event) / (n-1)
        se = math.sqrt(var / n)
        stats.append(HorizonStat(
            horizon=k,
            mean=mean,
            se=se,
            t_stat=mean / se if se > 0 else float("nan"),
            n_events=n,
            n_fills=sum(len(v) for v in acc[k].values()),
        ))
    return stats
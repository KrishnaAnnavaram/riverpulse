"""CCME Water Quality Index (Canadian Council of Ministers of the Environment, 2001).

Scale: 0 to 100. A HIGHER value is BETTER water. The index is calculated for a group
of visits (for example one site in one year) from three factors:

* F1 scope: percentage of variables that fail at least one objective
* F2 frequency: percentage of individual tests that fail
* F3 amplitude: how far the failed tests are from the objectives

Objectives are explicit: pH is two-sided, dissolved oxygen has a minimum, nutrients
have a maximum, and nitrate is "as N" (11.3 mg/l N = 50 mg/l NO3). The objectives are
screening values for this project, not a legal classification.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Objective:
    low: float | None = None
    high: float | None = None
    note: str = ""


OBJECTIVES = {
    "ph": Objective(6.0, 9.0, "two-sided range"),
    "do_mg": Objective(low=6.0, note="minimum, mg/l"),
    "ammonia_n": Objective(high=0.6, note="maximum, mg/l as N"),
    "orthophosphate_p": Objective(high=0.1, note="maximum, mg/l as P"),
    "nitrate_n": Objective(high=11.3, note="maximum, mg/l as N (50 mg/l as NO3)"),
    "temp_c": Objective(high=25.0, note="maximum, degrees C"),
}
CATEGORIES = [(95, "excellent"), (80, "good"), (65, "fair"), (45, "marginal"), (0, "poor")]
MIN_VARIABLES, MIN_TESTS = 4, 4


def excursion(value: float, obj: Objective) -> float:
    """0 for a pass. For a fail: value/objective - 1 (maximum) or objective/value - 1 (minimum)."""
    if obj.high is not None and value > obj.high:
        return value / obj.high - 1.0
    if obj.low is not None and value < obj.low:
        return obj.low / max(value, 1e-9) - 1.0
    return 0.0


def ccme(values: pd.DataFrame, objectives: dict[str, Objective] = OBJECTIVES) -> dict:
    """CCME WQI for one group of visits. ``values`` has one column for each determinand."""
    cols = [c for c in objectives if c in values.columns and values[c].notna().any()]
    tests = [(c, v) for c in cols for v in values[c].dropna().to_numpy(float)]
    if len(cols) < MIN_VARIABLES or len(tests) < MIN_TESTS:
        return {"wqi": np.nan, "category": "insufficient data", "variables": len(cols), "tests": len(tests)}
    exc = np.array([excursion(v, objectives[c]) for c, v in tests])
    failed_vars = {c for (c, _), e in zip(tests, exc) if e > 0}
    f1 = 100.0 * len(failed_vars) / len(cols)
    f2 = 100.0 * np.count_nonzero(exc > 0) / len(tests)
    nse = exc.sum() / len(tests)
    f3 = nse / (0.01 * nse + 0.01)
    wqi = 100.0 - np.sqrt(f1**2 + f2**2 + f3**2) / 1.732
    wqi = float(np.clip(wqi, 0.0, 100.0))
    return {"wqi": wqi, "category": category(wqi), "f1": f1, "f2": f2, "f3": f3, "variables": len(cols), "tests": len(tests)}


def category(wqi: float) -> str:
    if not np.isfinite(wqi):
        return "insufficient data"
    for floor, name in CATEGORIES:
        if wqi >= floor:
            return name
    return "poor"


def ccme_by(visits_df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    rows = []
    for key, group in visits_df.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        rows.append({**dict(zip(by, key)), **ccme(group)})
    return pd.DataFrame(rows)


def exceedances(visits_df: pd.DataFrame, objectives: dict[str, Objective] = OBJECTIVES) -> pd.DataFrame:
    """For each visit: number of measured objectives and number of failed objectives. Spikes stay."""
    out = pd.DataFrame(index=visits_df.index)
    measured = np.zeros(len(visits_df), int)
    failed = np.zeros(len(visits_df), int)
    for col, obj in objectives.items():
        if col not in visits_df:
            continue
        v = visits_df[col].to_numpy(float)
        ok = np.isfinite(v)
        measured += ok
        fail = np.zeros_like(ok)
        if obj.high is not None:
            fail |= ok & (v > obj.high)
        if obj.low is not None:
            fail |= ok & (v < obj.low)
        failed += fail
    out["measured"] = measured
    out["failed"] = failed
    return out

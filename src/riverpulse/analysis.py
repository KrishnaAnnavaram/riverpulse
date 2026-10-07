"""The two study questions. Both model DETERMINANDS, never the index, so no result is
circular.

1. Weather effects: ``log(determinand) ~ site + season + temperature + antecedent rain``.
2. COVID effect: an interrupted time series on a BALANCED panel of sites that were
   sampled in each period: ``log(determinand) ~ site + season + trend + during + after``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .stats import ols_cluster, seasonal_terms

LOG_DETERMINANDS = {"ammonia_n", "orthophosphate_p", "nitrate_n", "bod"}
WEATHER_TERMS = ["tmean", "rain_3d", "rain_7d", "rain_14d"]


def response(df: pd.DataFrame, determinand: str) -> np.ndarray:
    """Log for nutrients (multiplicative effects), raw scale for pH, oxygen and temperature."""
    v = df[determinand].to_numpy(float)
    return np.log(np.clip(v, 1e-4, None)) if determinand in LOG_DETERMINANDS else v


def weather_effects(df: pd.DataFrame, determinand: str, terms: list[str] = WEATHER_TERMS) -> pd.DataFrame:
    data = df.dropna(subset=[determinand] + terms)
    if data["site"].nunique() < 3 or len(data) < 50:
        raise ValueError(f"{determinand}: too few rows with weather ({len(data)}) for the model")
    X = pd.concat([data[terms].reset_index(drop=True), seasonal_terms(data["date"]).reset_index(drop=True)], axis=1)
    fit = ols_cluster(response(data, determinand), X, data["site"].to_numpy(), fixed_effects=data["site"].to_numpy())
    out = fit.table(terms)
    out.insert(0, "determinand", determinand)
    out["scale"] = "log" if determinand in LOG_DETERMINANDS else "raw"
    out["n"], out["sites"] = fit.n, fit.clusters
    return out


def assign_period(dates: pd.Series, start, end) -> pd.Series:
    d = pd.to_datetime(dates)
    return pd.Series(np.where(d < pd.Timestamp(start), "before", np.where(d <= pd.Timestamp(end), "during", "after")), index=dates.index)


def balanced_panel(df: pd.DataFrame, determinand: str, start, end, min_samples: int = 3) -> pd.DataFrame:
    """Keep only sites with at least ``min_samples`` measurements of the determinand in EACH period."""
    data = df.dropna(subset=[determinand]).copy()
    data["period"] = assign_period(data["date"], start, end)
    counts = data.groupby(["site", "period"]).size().unstack(fill_value=0)
    for p in ("before", "during", "after"):
        if p not in counts:
            counts[p] = 0
    keep = counts[(counts[["before", "during", "after"]] >= min_samples).all(axis=1)].index
    return data[data["site"].isin(keep)]


def naive_phase_means(df: pd.DataFrame, determinand: str, start, end) -> pd.DataFrame:
    """The comparison that the prototype made: means of all visits for each period, no matching."""
    data = df.dropna(subset=[determinand]).copy()
    data["period"] = assign_period(data["date"], start, end)
    return data.groupby("period").agg(mean=(determinand, "mean"), visits=(determinand, "size"), sites=("site", "nunique")).reindex(["before", "during", "after"])


def covid_its(df: pd.DataFrame, determinand: str, start, end, min_samples: int = 3) -> dict:
    """Interrupted time series on the balanced panel, with cluster-robust 95 % intervals.

    For a log response, ``effect_pct`` is the change in percent: 100 * (exp(b) - 1).
    """
    panel = balanced_panel(df, determinand, start, end, min_samples)
    if panel["site"].nunique() < 3:
        raise ValueError(f"{determinand}: fewer than 3 sites have {min_samples} samples in each period")
    t0 = pd.Timestamp(start)
    X = pd.DataFrame({
        "trend_years": (pd.to_datetime(panel["date"]) - t0).dt.days.to_numpy() / 365.25,
        "during": (panel["period"] == "during").to_numpy(float),
        "after": (panel["period"] == "after").to_numpy(float),
    })
    X = pd.concat([X, seasonal_terms(panel["date"]).reset_index(drop=True)], axis=1)
    fit = ols_cluster(response(panel, determinand), X, panel["site"].to_numpy(), fixed_effects=panel["site"].to_numpy())
    table = fit.table(["trend_years", "during", "after"])
    log = determinand in LOG_DETERMINANDS
    for col in ("coef", "ci_low", "ci_high"):
        table[f"{col}_pct" if log else f"{col}_units"] = 100 * (np.exp(table[col]) - 1) if log else table[col]
    return {
        "determinand": determinand,
        "scale": "log" if log else "raw",
        "sites_in_panel": int(panel["site"].nunique()),
        "sites_total": int(df.dropna(subset=[determinand])["site"].nunique()),
        "visits_in_panel": int(len(panel)),
        "terms": table.to_dict(orient="records"),
    }

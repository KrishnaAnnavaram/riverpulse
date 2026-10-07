"""Optional machine learning: forecast ONE determinand (default dissolved oxygen) from
season, site history and weather. The target is a measurement, not the index.

* Temporal split: train on visits up to ``cutoff``, test on later visits.
* Grouped cross-validation by site on the training part, to measure the transfer to
  sites that the model did not see.
* Baseline: the training mean of the same site and calendar month.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold

from .stats import seasonal_terms

FEATURES = ["tmean", "rain_1d", "rain_3d", "rain_7d", "rain_14d", "sin1", "cos1", "sin2", "cos2", "site_mean"]


def _features(df: pd.DataFrame, site_means: pd.Series, global_mean: float) -> pd.DataFrame:
    X = pd.concat([df[["tmean", "rain_1d", "rain_3d", "rain_7d", "rain_14d"]].reset_index(drop=True),
                   seasonal_terms(df["date"]).reset_index(drop=True)], axis=1)
    X["site_mean"] = df["site"].map(site_means).fillna(global_mean).to_numpy()
    return X[FEATURES]


def _climatology(train: pd.DataFrame, test: pd.DataFrame, target: str) -> np.ndarray:
    month = lambda d: pd.to_datetime(d).dt.month  # noqa: E731
    table = train.assign(month=month(train["date"])).groupby(["site", "month"])[target].mean()
    site = train.groupby("site")[target].mean()
    keys = list(zip(test["site"], month(test["date"])))
    pred = np.array([table.get(k, np.nan) for k in keys])
    fallback = test["site"].map(site).fillna(train[target].mean()).to_numpy()
    return np.where(np.isfinite(pred), pred, fallback)


def _mae(y, p) -> float:
    return float(np.mean(np.abs(np.asarray(y) - np.asarray(p))))


def forecast(df: pd.DataFrame, target: str = "do_mg", cutoff: str = "2021-12-31", seed: int = 42, folds: int = 5) -> dict:
    from .units import VALID_RANGES

    if target not in VALID_RANGES:
        raise ValueError(f"target must be a measured determinand {sorted(VALID_RANGES)}, not {target!r}")
    data = df.dropna(subset=[target, "tmean", "rain_14d"]).reset_index(drop=True)
    train = data[data["date"] <= pd.Timestamp(cutoff)].reset_index(drop=True)
    test = data[data["date"] > pd.Timestamp(cutoff)].reset_index(drop=True)
    if len(train) < 100 or len(test) < 20:
        raise ValueError(f"too few rows for a temporal split at {cutoff}: train {len(train)}, test {len(test)}")
    site_means = train.groupby("site")[target].mean()
    gmean = float(train[target].mean())

    def model():
        return HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, random_state=seed)

    fitted = model().fit(_features(train, site_means, gmean), train[target])
    pred = fitted.predict(_features(test, site_means, gmean))
    base = _climatology(train, test, target)

    cv = []
    for tr, va in GroupKFold(n_splits=folds).split(train, groups=train["site"]):
        a, b = train.iloc[tr], train.iloc[va]
        means = a.groupby("site")[target].mean()  # sites of the fold are unseen: they get the global mean
        m = model().fit(_features(a, means, float(a[target].mean())), a[target])
        cv.append(_mae(b[target], m.predict(_features(b, means, float(a[target].mean())))))
    return {
        "target": target,
        "cutoff": cutoff,
        "rows": {"train": len(train), "test": len(test)},
        "test_mae": {"model": _mae(test[target], pred), "site_month_climatology": _mae(test[target], base)},
        "grouped_cv_mae_unseen_sites": {"mean": float(np.mean(cv)), "folds": [round(v, 4) for v in cv]},
    }

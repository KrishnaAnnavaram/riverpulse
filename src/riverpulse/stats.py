"""Ordinary least squares with site fixed effects and cluster-robust (CR1) standard errors.

Visits of one site are not independent, so the standard errors are clustered by site.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class OLSResult:
    names: list[str]
    coef: np.ndarray
    se: np.ndarray
    n: int
    clusters: int

    def table(self, terms: list[str] | None = None) -> pd.DataFrame:
        rows = []
        for i, name in enumerate(self.names):
            if terms is not None and name not in terms:
                continue
            b, s = float(self.coef[i]), float(self.se[i])
            z = b / s if s > 0 else float("nan")
            rows.append({
                "term": name, "coef": b, "se": s, "ci_low": b - 1.96 * s, "ci_high": b + 1.96 * s,
                "p_value": math.erfc(abs(z) / math.sqrt(2)) if np.isfinite(z) else float("nan"),
            })
        return pd.DataFrame(rows)


def seasonal_terms(dates: pd.Series, harmonics: int = 2) -> pd.DataFrame:
    doy = pd.to_datetime(dates).dt.dayofyear.to_numpy(float)
    out = {}
    for k in range(1, harmonics + 1):
        out[f"sin{k}"] = np.sin(2 * np.pi * k * doy / 365.25)
        out[f"cos{k}"] = np.cos(2 * np.pi * k * doy / 365.25)
    return pd.DataFrame(out, index=dates.index)


def ols_cluster(y: np.ndarray, X: pd.DataFrame, clusters: np.ndarray, fixed_effects: np.ndarray | None = None) -> OLSResult:
    """Fit ``y ~ X (+ one dummy for each fixed-effect level)``. Return the coefficients of ``X`` only."""
    names = list(X.columns)
    mats = [X.to_numpy(float)]
    if fixed_effects is not None:
        dummies = pd.get_dummies(pd.Series(fixed_effects).astype(str)).to_numpy(float)
        mats.append(dummies)  # no intercept: the dummies take its place
    else:
        mats.append(np.ones((len(y), 1)))
        names = names + ["intercept"]
    Z = np.hstack(mats)
    y = np.asarray(y, float)
    keep = np.isfinite(y) & np.isfinite(Z).all(axis=1)
    Z, y, g = Z[keep], y[keep], np.asarray(clusters)[keep]
    bread = np.linalg.pinv(Z.T @ Z)
    beta = bread @ Z.T @ y
    resid = y - Z @ beta
    meat = np.zeros((Z.shape[1], Z.shape[1]))
    groups = pd.Series(np.arange(len(g))).groupby(pd.Series(g).to_numpy()).indices
    for idx in groups.values():
        s = Z[idx].T @ resid[idx]
        meat += np.outer(s, s)
    G, n, k = len(groups), len(y), np.linalg.matrix_rank(Z)
    scale = G / max(G - 1, 1) * (n - 1) / max(n - k, 1)
    cov = scale * bread @ meat @ bread
    m = len(X.columns) + (0 if fixed_effects is not None else 1)
    return OLSResult(names[:m], beta[:m], np.sqrt(np.clip(np.diag(cov)[:m], 0, None)), int(n), int(G))

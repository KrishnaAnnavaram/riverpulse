"""Read Environment Agency water-quality archive CSV files into one tidy table.

Tidy table: one row for each measurement, with the columns in ``TIDY_COLUMNS``.
No value is copied from one visit to another. A determinand that a visit did not
measure stays missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .units import VALID_RANGES, canonical_name, to_mg_per_l

EA_COLUMNS = {
    "sample.samplingPoint.notation": "site",
    "sample.sampleDateTime": "datetime",
    "determinand.notation": "notation",
    "determinand.definition": "definition",
    "resultQualifier.notation": "qualifier",
    "result": "result",
    "determinand.unit.label": "unit",
    "sample.samplingPoint.easting": "easting",
    "sample.samplingPoint.northing": "northing",
}
TIDY_COLUMNS = ["site", "datetime", "date", "determinand", "value", "below_lod", "easting", "northing"]


class IngestError(ValueError):
    pass


@dataclass
class IngestReport:
    rows_in: int = 0
    rows_out: int = 0
    dropped: dict[str, int] = field(default_factory=dict)

    def drop(self, reason: str, count) -> None:
        if int(count):
            self.dropped[reason] = self.dropped.get(reason, 0) + int(count)

    def summary(self) -> str:
        lines = [f"measurements: {self.rows_in} rows in, {self.rows_out} rows out"]
        lines += [f"  dropped {n:>7}  {r}" for r, n in sorted(self.dropped.items())]
        return "\n".join(lines)


def tidy(raw: pd.DataFrame, lod_policy: str = "half") -> tuple[pd.DataFrame, IngestReport]:
    """Change EA archive rows into the tidy table.

    ``lod_policy`` handles a result below the limit of detection (qualifier ``<``):
    ``half`` uses LOD / 2, ``lod`` uses the LOD, ``drop`` removes the row. The
    ``below_lod`` column keeps the flag in all cases.
    """
    report = IngestReport(rows_in=len(raw))
    absent = [c for c in EA_COLUMNS if c not in raw.columns]
    if absent:
        raise IngestError(f"EA archive columns are absent: {absent}")
    df = raw[list(EA_COLUMNS)].rename(columns=EA_COLUMNS).copy()
    df["determinand"] = [canonical_name(n, d) for n, d in zip(df["notation"], df["definition"])]
    unknown = df["determinand"].isna()
    report.drop("determinand not used", unknown.sum())
    df = df[~unknown]

    df["below_lod"] = df["qualifier"].astype(str).str.strip().eq("<")
    above = df["qualifier"].astype(str).str.strip().eq(">")
    report.drop("result above the upper limit of the method", above.sum())
    df = df[~above]
    value, known = to_mg_per_l(pd.to_numeric(df["result"], errors="coerce"), df["unit"])
    df["value"] = value
    report.drop("unknown unit", (~known).sum())
    df = df[known]
    if lod_policy == "half":
        df.loc[df["below_lod"], "value"] = df.loc[df["below_lod"], "value"] / 2
    elif lod_policy == "drop":
        report.drop("below the limit of detection", df["below_lod"].sum())
        df = df[~df["below_lod"]]

    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    bad_time = df["datetime"].isna() | df["value"].isna()
    report.drop("no date or no numeric result", bad_time.sum())
    df = df[~bad_time]
    low = df["determinand"].map(lambda d: VALID_RANGES[d][0])
    high = df["determinand"].map(lambda d: VALID_RANGES[d][1])
    impossible = (df["value"] < low) | (df["value"] > high)
    report.drop("physically impossible value", impossible.sum())
    df = df[~impossible]

    df["site"] = df["site"].astype(str).str.strip()
    df["date"] = df["datetime"].dt.normalize()
    for col in ("easting", "northing"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # repeated measurements of one determinand in one visit: keep the median
    keys = ["site", "datetime", "determinand"]
    n_before = len(df)
    df = (
        df.groupby(keys, as_index=False)
        .agg(value=("value", "median"), below_lod=("below_lod", "all"), date=("date", "first"),
             easting=("easting", "first"), northing=("northing", "first"))
    )
    report.drop("repeated measurement in one visit (median kept)", n_before - len(df))
    report.rows_out = len(df)
    return df[TIDY_COLUMNS].sort_values(["site", "datetime", "determinand"]).reset_index(drop=True), report


def read_archive(paths: list[str | Path], lod_policy: str = "half") -> tuple[pd.DataFrame, IngestReport]:
    if not paths:
        raise IngestError("no archive CSV files given")
    raw = pd.concat([pd.read_csv(p, low_memory=False) for p in paths], ignore_index=True)
    return tidy(raw, lod_policy)


def visits(tidy_df: pd.DataFrame) -> pd.DataFrame:
    """One row for each visit (site and time), one column for each determinand. Missing stays NaN."""
    wide = tidy_df.pivot_table(index=["site", "datetime"], columns="determinand", values="value", aggfunc="median")
    wide.columns.name = None
    meta = tidy_df.groupby(["site", "datetime"])[["date", "easting", "northing"]].first()
    return wide.join(meta).reset_index()


def sampling_summary(visits_df: pd.DataFrame) -> pd.DataFrame:
    """Visits and sites for each year. A large change shows a change of the sampling design."""
    year = visits_df["datetime"].dt.year
    return visits_df.groupby(year).agg(visits=("site", "size"), sites=("site", "nunique")).rename_axis("year")


def missing_share(visits_df: pd.DataFrame, determinands: list[str]) -> dict[str, float]:
    return {d: float(visits_df[d].isna().mean()) if d in visits_df else 1.0 for d in determinands}


def finite(values) -> np.ndarray:
    v = np.asarray(values, float)
    return v[np.isfinite(v)]

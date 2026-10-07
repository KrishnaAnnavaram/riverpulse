"""Seeded synthetic archive in the Environment Agency CSV format, with KNOWN effects.

The generator writes the defects that the real archive has and that a naive analysis
gets wrong:

* the sampling changes during COVID: fewer sites, and the cleaner sites are sampled more
* a slow downward trend in ammonia that starts before COVID
* results below the limit of detection (qualifier ``<``) and a mix of mg/l and ug/l
* determinands that a visit did not measure, and rare pollution spikes

``TRUTH`` holds the true effects, so a test can check that the analysis recovers them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .geo import bng_to_wgs84, grid_cell
from .weather import SyntheticWeather, add_rain_windows

TRUTH = {
    "ammonia_n": {"during": -0.15, "after": 0.0, "trend_years": -0.03, "rain_3d": 0.03},
    "orthophosphate_p": {"rain_7d": 0.012, "trend_years": -0.02},
    "do_mg": {"tmean": -0.22},
}
DEFINITIONS = {
    "ph": ("0061", "pH", "phunits"),
    "temp_c": ("0076", "Temperature of Water", "cel"),
    "ammonia_n": ("0111", "Ammoniacal Nitrogen as N", "mg/l"),
    "nitrate_n": ("0117", "Nitrate as N", "mg/l"),
    "orthophosphate_p": ("0180", "Orthophosphate, reactive as P", "mg/l"),
    "do_mg": ("9924", "Oxygen, Dissolved as O2", "mg/l"),
}
AMMONIA_LOD = 0.03


def make_archive(n_sites: int = 60, seed: int = 42, start: str = "2015-01-01", end: str = "2024-12-31",
                 covid=("2020-03-23", "2021-07-19")) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    sites = pd.DataFrame({
        "site": [f"AN-RV{i:03d}" for i in range(n_sites)],
        "easting": rng.uniform(480_000, 560_000, n_sites).round(0),
        "northing": rng.uniform(220_000, 300_000, n_sites).round(0),
        "mu_nh4": rng.normal(np.log(0.15), 0.6, n_sites),
        "mu_po4": rng.normal(np.log(0.12), 0.5, n_sites),
        "no3": rng.lognormal(np.log(6.0), 0.4, n_sites),
        "do": rng.normal(10.5, 0.8, n_sites),
        "ph": rng.normal(7.9, 0.25, n_sites),
    })
    lat, lon = bng_to_wgs84(sites["easting"], sites["northing"], use_pyproj=False)
    sites["cell_lat"], sites["cell_lon"] = grid_cell(lat, lon)
    clean_rank = sites["mu_nh4"].rank(pct=True).to_numpy()  # 0 = cleanest

    weather = SyntheticWeather(seed)
    cache: dict[tuple, pd.DataFrame] = {}
    c0, c1 = pd.Timestamp(covid[0]), pd.Timestamp(covid[1])
    rows = []
    months = pd.date_range(start, end, freq="MS")
    for s in sites.itertuples():
        key = (s.cell_lat, s.cell_lon)
        if key not in cache:
            w = add_rain_windows(weather.daily(s.cell_lat, s.cell_lon, (pd.Timestamp(start) - pd.Timedelta(days=20)).strftime("%Y-%m-%d"), end))
            cache[key] = w.set_index("date")
        w = cache[key]
        for m in months:
            during = c0 <= m <= c1
            # during COVID, few sites are visited and the cleaner sites are favoured
            p_visit = (0.55 * (1.0 - clean_rank[s.Index]) ** 3 + 0.05) if during else 0.8
            if rng.random() > p_visit:
                continue
            day = m + pd.Timedelta(days=int(rng.integers(0, 27)))
            t = day + pd.Timedelta(hours=int(rng.integers(8, 16)), minutes=int(rng.integers(0, 60)))
            wx = w.loc[day.normalize()]
            doy = day.dayofyear
            years = (day - pd.Timestamp("2015-01-01")).days / 365.25
            after = day > c1
            season = np.cos(2 * np.pi * (doy - 15) / 365.25)
            log_nh4 = (s.mu_nh4 + 0.3 * season + TRUTH["ammonia_n"]["trend_years"] * years
                       + TRUTH["ammonia_n"]["rain_3d"] * wx["rain_3d"] + TRUTH["ammonia_n"]["during"] * during
                       + TRUTH["ammonia_n"]["after"] * after + rng.normal(0, 0.35))
            nh4 = float(np.exp(log_nh4)) * (5.0 if rng.random() < 0.01 else 1.0)  # rare pollution spike
            po4 = float(np.exp(s.mu_po4 + TRUTH["orthophosphate_p"]["rain_7d"] * wx["rain_7d"]
                               + TRUTH["orthophosphate_p"]["trend_years"] * years + rng.normal(0, 0.3)))
            values = {
                "ph": s.ph + rng.normal(0, 0.2),
                "temp_c": 2.0 + 0.8 * wx["tmean"] + rng.normal(0, 1.0),
                "ammonia_n": nh4,
                "nitrate_n": s.no3 * float(np.exp(0.2 * season + rng.normal(0, 0.2))),
                "orthophosphate_p": po4,
                "do_mg": s.do + TRUTH["do_mg"]["tmean"] * (wx["tmean"] - 10.0) + rng.normal(0, 0.6),
            }
            for name, value in values.items():
                if rng.random() > 0.88:
                    continue  # not measured at this visit
                notation, definition, unit = DEFINITIONS[name]
                qualifier = ""
                if name == "ammonia_n" and value < AMMONIA_LOD:
                    qualifier, value = "<", AMMONIA_LOD
                if name == "orthophosphate_p" and rng.random() < 0.2:
                    unit, value = "ug/l", value * 1000.0
                rows.append({
                    "sample.samplingPoint.notation": s.site,
                    "sample.sampleDateTime": t.strftime("%Y-%m-%dT%H:%M:%S"),
                    "determinand.notation": notation,
                    "determinand.definition": definition,
                    "resultQualifier.notation": qualifier,
                    "result": round(float(value), 4),
                    "determinand.unit.label": unit,
                    "sample.samplingPoint.easting": s.easting,
                    "sample.samplingPoint.northing": s.northing,
                })
    return pd.DataFrame(rows)

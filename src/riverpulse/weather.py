"""Daily weather for each site, and antecedent rain features.

Each site gets the weather of its own 0.1-degree grid cell (about 7 x 11 km). The
Open-Meteo provider calls the public archive API once for each cell and caches the reply.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from .geo import bng_to_wgs84, grid_cell

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY = ["temperature_2m_mean", "precipitation_sum", "relative_humidity_2m_mean"]
RAIN_WINDOWS = (1, 3, 7, 14)


class WeatherProvider(Protocol):
    name: str

    def daily(self, lat: float, lon: float, start: str, end: str) -> pd.DataFrame: ...


class OpenMeteoProvider:
    name = "open-meteo"

    def __init__(self, cache_dir: str | Path, timeout_s: float = 60.0, fetch=None) -> None:
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.timeout_s = timeout_s
        self.fetch = fetch or self._fetch

    def _fetch(self, url: str) -> dict:
        with urllib.request.urlopen(url, timeout=self.timeout_s) as resp:  # noqa: S310 - fixed https host
            return json.loads(resp.read().decode("utf-8"))

    def daily(self, lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
        file = self.cache / f"om_{lat:.4f}_{lon:.4f}_{start}_{end}.json"
        if file.exists():
            data = json.loads(file.read_text(encoding="utf-8"))
        else:
            query = {"latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
                     "daily": ",".join(DAILY), "timezone": "Europe/London"}
            data = self.fetch(f"{OPEN_METEO_URL}?{urllib.parse.urlencode(query)}")
            file.write_text(json.dumps(data), encoding="utf-8")
        d = data["daily"]
        return pd.DataFrame({
            "date": pd.to_datetime(d["time"]),
            "tmean": d["temperature_2m_mean"],
            "precip": d["precipitation_sum"],
            "rh": d["relative_humidity_2m_mean"],
        })


class StationWeather:
    """Fixed weather stations (for example two downloaded CSV files). A cell gets the nearest
    station only if it is within ``max_km``. Otherwise its weather stays missing."""

    name = "stations"

    def __init__(self, stations: dict[str, tuple[float, float, pd.DataFrame]], max_km: float = 25.0) -> None:
        if not stations:
            raise ValueError("no weather station given")
        self.stations = stations
        self.max_km = max_km

    def daily(self, lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
        from .geo import haversine_km

        names = list(self.stations)
        dist = [float(haversine_km(lat, lon, self.stations[n][0], self.stations[n][1])) for n in names]
        best = int(np.argmin(dist))
        frame = self.stations[names[best]][2]
        if dist[best] > self.max_km:
            return frame.iloc[0:0].copy()
        mask = (frame["date"] >= pd.Timestamp(start)) & (frame["date"] <= pd.Timestamp(end))
        return frame.loc[mask].copy()


def read_station_csv(path: str | Path) -> pd.DataFrame:
    """Read an Open-Meteo daily CSV download: metadata lines, then ``time, temperature_2m_mean (°C), ...``."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("time,"))
    df = pd.read_csv(path, skiprows=start)
    cols = {c: c.split(" ")[0] for c in df.columns}
    df = df.rename(columns=cols)
    return pd.DataFrame({
        "date": pd.to_datetime(df["time"]),
        "tmean": df["temperature_2m_mean"],
        "precip": df["precipitation_sum"],
        "rh": df.get("relative_humidity_2m_mean", np.nan),
    })


class SyntheticWeather:
    """Seeded daily weather for the demo and the tests: seasonal temperature and gamma rain."""

    name = "synthetic"

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed

    SPAN = ("2000-01-01", "2035-12-31")  # one fixed series for each cell, sliced on request

    def daily(self, lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
        dates = pd.date_range(*self.SPAN, freq="D")
        cell = int(round(abs(lat) * 1000) + round(abs(lon) * 1000)) % 10_000
        rng = np.random.default_rng(self.seed * 10_000 + cell)
        doy = dates.dayofyear.to_numpy()
        shocks = rng.normal(0, 1.2, len(dates))
        noise = np.zeros(len(dates))
        for i in range(1, len(dates)):
            noise[i] = 0.8 * noise[i - 1] + shocks[i]
        tmean = 10.5 - 6.5 * np.cos(2 * np.pi * (doy - 15) / 365.25) + noise
        wet = rng.random(len(dates)) < 0.45
        precip = np.where(wet, rng.gamma(0.8, 4.0, len(dates)), 0.0)
        rh = np.clip(78 + 8 * np.cos(2 * np.pi * (doy - 15) / 365.25) + 3 * wet + rng.normal(0, 4, len(dates)), 30, 100)
        full = pd.DataFrame({"date": dates, "tmean": tmean.round(2), "precip": precip.round(2), "rh": rh.round(1)})
        mask = (full["date"] >= pd.Timestamp(start)) & (full["date"] <= pd.Timestamp(end))
        return full.loc[mask].reset_index(drop=True)


def add_rain_windows(weather: pd.DataFrame) -> pd.DataFrame:
    """Rain sums over the 1, 3, 7 and 14 days that END on each date (the date is included)."""
    out = weather.sort_values("date").copy()
    for w in RAIN_WINDOWS:
        out[f"rain_{w}d"] = out["precip"].rolling(w, min_periods=w).sum()
    return out


def site_weather(visits_df: pd.DataFrame, provider: WeatherProvider, use_pyproj: bool = True) -> pd.DataFrame:
    """Join the weather of each site grid cell to each visit on the visit date."""
    sites = visits_df.groupby("site")[["easting", "northing"]].first().dropna()
    lat, lon = bng_to_wgs84(sites["easting"].to_numpy(), sites["northing"].to_numpy(), use_pyproj=use_pyproj)
    clat, clon = grid_cell(lat, lon)
    sites = sites.assign(lat=lat, lon=lon, cell_lat=clat, cell_lon=clon)
    start = (visits_df["date"].min() - pd.Timedelta(days=20)).strftime("%Y-%m-%d")
    end = visits_df["date"].max().strftime("%Y-%m-%d")
    frames = []
    for (cl, cn), group in sites.groupby(["cell_lat", "cell_lon"]):
        w = add_rain_windows(provider.daily(float(cl), float(cn), start, end))
        for site in group.index:
            frames.append(w.assign(site=site))
    weather = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["site", "date"])
    merged = visits_df.merge(weather, on=["site", "date"], how="left")
    return merged.merge(sites[["lat", "lon"]], left_on="site", right_index=True, how="left")

"""Coordinates: British National Grid (EPSG:27700) to WGS84, distances and station links.

The conversion is vectorised numpy. It uses the Ordnance Survey formulas for the
inverse transverse Mercator projection (Airy 1830) and a 7-parameter Helmert
transformation to WGS84. The accuracy is about 5 m, which is enough to link a
sampling point to a weather grid cell. With the extra ``geo``, ``pyproj`` is used.
"""
from __future__ import annotations

import importlib

import numpy as np

AIRY_A, AIRY_B = 6377563.396, 6356256.909
WGS_A, WGS_B = 6378137.000, 6356752.3142
F0 = 0.9996012717
LAT0, LON0 = np.radians(49.0), np.radians(-2.0)
N0, E0 = -100000.0, 400000.0
# OSGB36 -> WGS84 Helmert parameters (metres, ppm, arc seconds)
HELMERT = {"tx": 446.448, "ty": -125.157, "tz": 542.060, "s": -20.4894, "rx": 0.1502, "ry": 0.2470, "rz": 0.8421}


def _meridional_arc(lat, a=AIRY_A, b=AIRY_B):
    n = (a - b) / (a + b)
    d, s = lat - LAT0, lat + LAT0
    return b * F0 * (
        (1 + n + 1.25 * n**2 + 1.25 * n**3) * d
        - (3 * n + 3 * n**2 + 21 / 8 * n**3) * np.sin(d) * np.cos(s)
        + (15 / 8 * n**2 + 15 / 8 * n**3) * np.sin(2 * d) * np.cos(2 * s)
        - 35 / 24 * n**3 * np.sin(3 * d) * np.cos(3 * s)
    )


def bng_to_osgb36(easting, northing) -> tuple[np.ndarray, np.ndarray]:
    """Easting and northing (m) to OSGB36 latitude and longitude in degrees."""
    E = np.asarray(easting, dtype=float)
    N = np.asarray(northing, dtype=float)
    a, b = AIRY_A, AIRY_B
    e2 = 1 - b**2 / a**2
    lat = (N - N0) / (a * F0) + LAT0
    for _ in range(20):
        M = _meridional_arc(lat)
        lat = lat + (N - N0 - M) / (a * F0)
        if np.all(np.abs(N - N0 - _meridional_arc(lat)) < 1e-5):
            break
    sin, cos, tan = np.sin(lat), np.cos(lat), np.tan(lat)
    nu = a * F0 / np.sqrt(1 - e2 * sin**2)
    rho = a * F0 * (1 - e2) / (1 - e2 * sin**2) ** 1.5
    eta2 = nu / rho - 1
    sec = 1 / cos
    VII = tan / (2 * rho * nu)
    VIII = tan / (24 * rho * nu**3) * (5 + 3 * tan**2 + eta2 - 9 * tan**2 * eta2)
    IX = tan / (720 * rho * nu**5) * (61 + 90 * tan**2 + 45 * tan**4)
    X = sec / nu
    XI = sec / (6 * nu**3) * (nu / rho + 2 * tan**2)
    XII = sec / (120 * nu**5) * (5 + 28 * tan**2 + 24 * tan**4)
    XIIA = sec / (5040 * nu**7) * (61 + 662 * tan**2 + 1320 * tan**4 + 720 * tan**6)
    dE = E - E0
    phi = lat - VII * dE**2 + VIII * dE**4 - IX * dE**6
    lam = LON0 + X * dE - XI * dE**3 + XII * dE**5 - XIIA * dE**7
    return np.degrees(phi), np.degrees(lam)


def _to_cartesian(lat, lon, a, b):
    lat, lon = np.radians(lat), np.radians(lon)
    e2 = 1 - b**2 / a**2
    nu = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    return nu * np.cos(lat) * np.cos(lon), nu * np.cos(lat) * np.sin(lon), (1 - e2) * nu * np.sin(lat)


def _from_cartesian(x, y, z, a, b):
    e2 = 1 - b**2 / a**2
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1 - e2))
    for _ in range(10):
        nu = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
        lat = np.arctan2(z + e2 * nu * np.sin(lat), p)
    return np.degrees(lat), np.degrees(np.arctan2(y, x))


def osgb36_to_wgs84(lat, lon) -> tuple[np.ndarray, np.ndarray]:
    x, y, z = _to_cartesian(lat, lon, AIRY_A, AIRY_B)
    h = HELMERT
    s = h["s"] * 1e-6
    rx, ry, rz = (np.radians(h[k] / 3600.0) for k in ("rx", "ry", "rz"))
    x2 = h["tx"] + (1 + s) * x - rz * y + ry * z
    y2 = h["ty"] + rz * x + (1 + s) * y - rx * z
    z2 = h["tz"] - ry * x + rx * y + (1 + s) * z
    return _from_cartesian(x2, y2, z2, WGS_A, WGS_B)


def bng_to_wgs84(easting, northing, use_pyproj: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Easting and northing to WGS84 latitude and longitude. ``pyproj`` is used if it is installed."""
    if use_pyproj:
        try:
            pyproj = importlib.import_module("pyproj")
            t = pyproj.Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
            lon, lat = t.transform(np.asarray(easting, float), np.asarray(northing, float))
            return np.asarray(lat), np.asarray(lon)
        except ImportError:
            pass
    return osgb36_to_wgs84(*bng_to_osgb36(easting, northing))


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(v, float)) for v in (lat1, lon1, lat2, lon2))
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def grid_cell(lat, lon, step: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    """Centre of the ``step``-degree weather grid cell of each point."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    return np.round(np.floor(lat / step) * step + step / 2, 4), np.round(np.floor(lon / step) * step + step / 2, 4)

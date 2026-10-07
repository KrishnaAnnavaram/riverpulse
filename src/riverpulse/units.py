"""Determinands: Environment Agency codes, canonical names and unit conversion to mg/l."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

# EA determinand notation -> canonical name. "as N" and "as P" stay in the name.
DETERMINANDS = {
    61: "ph",
    76: "temp_c",
    111: "ammonia_n",
    117: "nitrate_n",
    180: "orthophosphate_p",
    9924: "do_mg",
    9901: "do_sat",
    85: "bod",
}
# fallback: match on the determinand definition text (lower case)
DEFINITION_PATTERNS = [
    (r"^ph\b", "ph"),
    (r"temperature of water", "temp_c"),
    (r"ammoniacal nitrogen as n|ammonia\(n\)", "ammonia_n"),
    (r"nitrate as n|nitrate-n", "nitrate_n"),
    (r"orthophosphate, reactive as p|orthophospht", "orthophosphate_p"),
    (r"oxygen, dissolved as o2", "do_mg"),
    (r"oxygen, dissolved, % saturation", "do_sat"),
    (r"bod", "bod"),
]
UNIT_FACTORS = {"mg/l": 1.0, "ug/l": 1e-3, "µg/l": 1e-3, "ng/l": 1e-6, "g/l": 1e3}
PASS_THROUGH_UNITS = {"phunits": "ph", "unitless": "", "cel": "C", "degc": "C", "%": "%"}
VALID_RANGES = {
    "ph": (0.0, 14.0),
    "temp_c": (-1.0, 40.0),
    "ammonia_n": (0.0, 500.0),
    "nitrate_n": (0.0, 200.0),
    "orthophosphate_p": (0.0, 100.0),
    "do_mg": (0.0, 25.0),
    "do_sat": (0.0, 250.0),
    "bod": (0.0, 500.0),
}


def canonical_name(notation, definition: str | None) -> str | None:
    try:
        code = int(float(notation))
        if code in DETERMINANDS:
            return DETERMINANDS[code]
    except (TypeError, ValueError):
        pass
    text = (definition or "").strip().lower()
    for pattern, name in DEFINITION_PATTERNS:
        if re.search(pattern, text):
            return name
    return None


def to_mg_per_l(values: pd.Series, units: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Convert concentrations to mg/l. Return the values and a mask of rows with a known unit."""
    key = units.astype(str).str.strip().str.lower().str.replace(" ", "", regex=False)
    factor = key.map(UNIT_FACTORS)
    passthrough = key.isin(PASS_THROUGH_UNITS)
    factor = factor.where(~passthrough, 1.0)
    known = factor.notna()
    return values.astype(float) * factor.fillna(np.nan), known

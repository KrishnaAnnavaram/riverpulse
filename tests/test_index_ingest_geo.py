"""The index (reference problems 3 and 7), ingest without imputation or smoothing (4 and 5), units and geo."""
import numpy as np
import pandas as pd
import pytest

from riverpulse.geo import bng_to_osgb36, bng_to_wgs84, grid_cell, haversine_km
from riverpulse.ingest import IngestError, tidy, visits
from riverpulse.units import canonical_name, to_mg_per_l
from riverpulse.wqi import OBJECTIVES, category, ccme, excursion, exceedances


def test_ph_objective_is_two_sided():
    obj = OBJECTIVES["ph"]
    assert excursion(7.5, obj) == 0.0
    assert excursion(5.0, obj) > 0 and excursion(10.0, obj) > 0


def test_nitrate_limit_is_as_n_and_temperature_is_not_a_pollutant():
    assert OBJECTIVES["nitrate_n"].high == pytest.approx(11.3)
    assert excursion(0.0, OBJECTIVES["temp_c"]) == 0.0 and excursion(26.0, OBJECTIVES["temp_c"]) > 0
    assert excursion(3.0, OBJECTIVES["do_mg"]) == pytest.approx(1.0)  # 6 / 3 - 1


def test_ccme_scale_direction_and_values():
    clean = pd.DataFrame({"ph": [7.5] * 4, "do_mg": [9.0] * 4, "ammonia_n": [0.1] * 4, "nitrate_n": [5.0] * 4})
    assert ccme(clean)["wqi"] == 100.0 and category(100.0) == "excellent"
    dirty = clean.assign(ammonia_n=[0.1, 1.2, 0.1, 0.1])  # one test of one variable fails
    r = ccme(dirty)
    assert r["f1"] == 25.0 and r["f2"] == 6.25
    nse = (1.2 / 0.6 - 1) / 16
    f3 = nse / (0.01 * nse + 0.01)
    assert r["wqi"] == pytest.approx(100 - np.sqrt(25**2 + 6.25**2 + f3**2) / 1.732)
    assert r["wqi"] < 100  # lower is worse: the direction is fixed


def test_ccme_needs_enough_data():
    assert ccme(pd.DataFrame({"ph": [7.0], "do_mg": [9.0]}))["category"] == "insufficient data"


def test_categories_increase_with_the_index():
    names = [category(v) for v in (10, 50, 70, 85, 97)]
    assert names == ["poor", "marginal", "fair", "good", "excellent"]


def _raw(rows):
    cols = ["sample.samplingPoint.notation", "sample.sampleDateTime", "determinand.notation", "determinand.definition",
            "resultQualifier.notation", "result", "determinand.unit.label", "sample.samplingPoint.easting",
            "sample.samplingPoint.northing"]
    return pd.DataFrame(rows, columns=cols)


def test_no_value_is_copied_between_visits():
    """Problem 4: a determinand measured at one visit stays missing at the other visit."""
    raw = _raw([
        ["S1", "2019-01-10T10:00:00", "0111", "Ammoniacal Nitrogen as N", "", 0.2, "mg/l", 500000, 250000],
        ["S1", "2019-01-10T10:00:00", "0061", "pH", "", 7.8, "phunits", 500000, 250000],
        ["S1", "2019-02-10T10:00:00", "0061", "pH", "", 7.6, "phunits", 500000, 250000],
    ])
    v = visits(tidy(raw)[0])
    assert np.isnan(v.loc[1, "ammonia_n"]) and v.loc[0, "ammonia_n"] == 0.2


def test_spikes_are_kept_and_counted():
    """Problem 5: a pollution spike is not smoothed away."""
    raw = _raw([["S1", f"2019-0{m}-10T10:00:00", "0111", "Ammoniacal Nitrogen as N", "", v, "mg/l", 500000, 250000]
                for m, v in zip(range(1, 7), [0.1, 0.1, 0.1, 9.5, 0.1, 0.1])])
    v = visits(tidy(raw)[0])
    assert v["ammonia_n"].max() == 9.5
    assert exceedances(v)["failed"].sum() == 1


def test_units_lod_and_impossible_values():
    raw = _raw([
        ["S1", "2019-01-10T10:00:00", "0180", "Orthophosphate, reactive as P", "", 120.0, "ug/l", 1, 1],
        ["S1", "2019-01-10T10:00:00", "0111", "Ammoniacal Nitrogen as N", "<", 0.03, "mg/l", 1, 1],
        ["S1", "2019-01-10T10:00:00", "0061", "pH", "", 19.0, "phunits", 1, 1],
        ["S1", "2019-01-10T10:00:00", "9999", "Something else", "", 1.0, "mg/l", 1, 1],
    ])
    t, report = tidy(raw, lod_policy="half")
    values = t.set_index("determinand")["value"]
    assert values["orthophosphate_p"] == pytest.approx(0.12)
    assert values["ammonia_n"] == pytest.approx(0.015) and t.set_index("determinand")["below_lod"]["ammonia_n"]
    assert "ph" not in values.index and report.dropped["physically impossible value"] == 1
    assert len(tidy(raw, lod_policy="drop")[0]) == 1


def test_missing_archive_columns_raise():
    with pytest.raises(IngestError):
        tidy(pd.DataFrame({"result": [1]}))


def test_determinand_names_by_code_or_text():
    assert canonical_name("0111", "") == "ammonia_n"
    assert canonical_name(None, "Nitrate as N") == "nitrate_n"
    assert canonical_name("abc", "unknown") is None
    v, known = to_mg_per_l(pd.Series([5.0, 5.0]), pd.Series(["ug/l", "furlongs"]))
    assert v[0] == pytest.approx(0.005) and not known[1]


def test_bng_conversion_matches_the_ordnance_survey_example():
    lat, lon = bng_to_osgb36(651409.903, 313177.270)
    assert float(lat) == pytest.approx(52 + 39 / 60 + 27.2531 / 3600, abs=1e-6)
    assert float(lon) == pytest.approx(1 + 43 / 60 + 4.5177 / 3600, abs=1e-6)
    wlat, wlon = bng_to_wgs84(651409.903, 313177.270, use_pyproj=False)
    assert float(wlat) == pytest.approx(52 + 39 / 60 + 28.8282 / 3600, abs=5e-5)
    assert float(wlon) == pytest.approx(1 + 42 / 60 + 57.8663 / 3600, abs=5e-5)


def test_pyproj_agrees_with_numpy_conversion():
    pytest.importorskip("pyproj")
    a = bng_to_wgs84([530000, 500000], [260000, 240000], use_pyproj=True)
    b = bng_to_wgs84([530000, 500000], [260000, 240000], use_pyproj=False)
    assert np.allclose(a[0], b[0], atol=1e-4) and np.allclose(a[1], b[1], atol=1e-4)


def test_distance_and_grid_cell():
    assert float(haversine_km(52.0, 0.0, 53.0, 0.0)) == pytest.approx(111.2, abs=0.1)
    lat, lon = grid_cell([52.21, 52.29], [0.11, 0.19])
    assert list(lat) == [52.25, 52.25] and list(lon) == [0.15, 0.15]

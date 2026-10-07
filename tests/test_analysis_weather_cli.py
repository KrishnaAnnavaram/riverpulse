"""Analysis on synthetic data with known effects (problems 1, 2, 6, 8) and the CLI (problem 9)."""
import json

import numpy as np
import pandas as pd
import pytest

from riverpulse.analysis import balanced_panel, covid_its, naive_phase_means, weather_effects
from riverpulse.cli import main
from riverpulse.config import ConfigError, Settings
from riverpulse.forecast import forecast
from riverpulse.synthetic import TRUTH
from riverpulse.weather import OpenMeteoProvider, StationWeather, SyntheticWeather, add_rain_windows, read_station_csv


def _term(table, term):
    return table.set_index("term").loc[term]


def test_weather_effects_recover_the_true_coefficients(prepared):
    """Problem 1: the models explain determinands from weather, and recover the known effects."""
    v = prepared.visits
    nh4 = _term(weather_effects(v, "ammonia_n"), "rain_3d")
    assert nh4["ci_low"] <= TRUTH["ammonia_n"]["rain_3d"] <= nh4["ci_high"]
    po4 = _term(weather_effects(v, "orthophosphate_p"), "rain_7d")
    assert po4["ci_low"] <= TRUTH["orthophosphate_p"]["rain_7d"] <= po4["ci_high"]
    do = _term(weather_effects(v, "do_mg"), "tmean")
    assert do["ci_low"] <= TRUTH["do_mg"]["tmean"] <= do["ci_high"]
    no_effect = _term(weather_effects(v, "do_mg"), "rain_7d")
    assert no_effect["ci_low"] < 0 < no_effect["ci_high"]


def test_covid_its_recovers_the_effect_and_the_naive_comparison_does_not(prepared, settings):
    """Problem 2: site matching and a trend give the true effect. Raw phase means do not."""
    v = prepared.visits
    res = covid_its(v, "ammonia_n", settings.covid_start, settings.covid_end, settings.min_samples_per_period)
    during = next(t for t in res["terms"] if t["term"] == "during")
    assert during["ci_low"] <= TRUTH["ammonia_n"]["during"] <= during["ci_high"]
    naive = naive_phase_means(v, "ammonia_n", settings.covid_start, settings.covid_end)
    naive_change = np.log(naive.loc["during", "mean"] / naive.loc["before", "mean"])
    assert naive_change < TRUTH["ammonia_n"]["during"] - 0.2  # the naive change is far too large


def test_balanced_panel_keeps_only_sites_in_each_period(prepared, settings):
    panel = balanced_panel(prepared.visits, "ammonia_n", settings.covid_start, settings.covid_end, 3)
    counts = panel.groupby(["site", "period"]).size().unstack()
    assert (counts[["before", "during", "after"]] >= 3).all().all()
    assert panel["site"].nunique() < prepared.visits["site"].nunique()


def test_sampling_change_is_reported(prepared):
    from riverpulse.ingest import sampling_summary

    s = sampling_summary(prepared.visits)
    assert s.loc[2020, "visits"] < 0.6 * s.loc[2019, "visits"]


def test_forecast_uses_a_temporal_split_and_beats_climatology(prepared):
    """Problem 6: no random split over time. Grouped CV measures unseen sites."""
    res = forecast(prepared.visits, "do_mg", cutoff="2021-12-31")
    assert res["test_mae"]["model"] < res["test_mae"]["site_month_climatology"]
    assert res["grouped_cv_mae_unseen_sites"]["mean"] > res["test_mae"]["model"]
    with pytest.raises(ValueError):
        forecast(prepared.visits, "wqi")


def test_rain_windows_include_the_day():
    w = pd.DataFrame({"date": pd.date_range("2020-01-01", periods=5), "precip": [1.0, 2.0, 3.0, 4.0, 5.0]})
    out = add_rain_windows(w)
    assert out["rain_3d"].tolist()[2:] == [6.0, 9.0, 12.0]
    assert np.isnan(out["rain_7d"]).all()


def test_synthetic_weather_does_not_depend_on_the_requested_range():
    g = SyntheticWeather(3)
    a = g.daily(52.25, 0.15, "2020-01-01", "2020-12-31")
    b = g.daily(52.25, 0.15, "2019-06-01", "2021-06-30")
    merged = a.merge(b, on="date")
    assert np.allclose(merged["tmean_x"], merged["tmean_y"])


def test_station_far_away_gives_no_weather():
    """Problem 8: a site far from each station gets missing weather, not the nearest station."""
    frame = pd.DataFrame({"date": pd.date_range("2020-01-01", periods=3), "tmean": 5.0, "precip": 1.0, "rh": 80.0})
    stations = StationWeather({"cambridge": (52.1968, 0.1661, frame)}, max_km=25)
    assert len(stations.daily(52.20, 0.17, "2020-01-01", "2020-01-03")) == 3
    assert stations.daily(53.50, -1.50, "2020-01-01", "2020-01-03").empty


def test_open_meteo_provider_uses_cache(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return {"daily": {"time": ["2020-01-01"], "temperature_2m_mean": [4.0], "precipitation_sum": [0.5],
                          "relative_humidity_2m_mean": [90]}}

    p = OpenMeteoProvider(tmp_path, fetch=fetch)
    assert p.daily(52.25, 0.15, "2020-01-01", "2020-01-01")["tmean"].iloc[0] == 4.0
    p.daily(52.25, 0.15, "2020-01-01", "2020-01-01")
    assert len(calls) == 1 and "archive-api.open-meteo.com" in calls[0]


def test_station_csv_reader(tmp_path):
    f = tmp_path / "bedford.csv"
    f.write_text("latitude,longitude\n52.1,-0.5\n\ntime,temperature_2m_mean (°C),precipitation_sum (mm),"
                 "relative_humidity_2m_mean (%)\n2020-01-01,4.1,0.2,88\n", encoding="utf-8")
    df = read_station_csv(f)
    assert df.loc[0, "tmean"] == 4.1 and df.loc[0, "precip"] == 0.2


def test_settings(monkeypatch):
    monkeypatch.setenv("RIVERPULSE_LOD_POLICY", "zero")
    with pytest.raises(ConfigError):
        Settings.from_env()
    monkeypatch.setenv("RIVERPULSE_LOD_POLICY", "drop")
    monkeypatch.setenv("RIVERPULSE_COVID_START", "2022-01-01")
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_cli_generate_ingest_index_study(tmp_path, capsys):
    csv = tmp_path / "archive.csv"
    assert main(["generate", "--out", str(csv), "--sites", "25"]) == 0
    assert main(["ingest", "--csv", str(csv), "--out", str(tmp_path / "tidy.csv")]) == 0
    assert (tmp_path / "tidy.csv").exists()
    assert main(["index", "--sites", "25", "--out", str(tmp_path / "index.csv")]) == 0
    assert set(pd.read_csv(tmp_path / "index.csv")["category"]) <= {"excellent", "good", "fair", "marginal", "poor", "insufficient data"}
    assert main(["study", "--sites", "40", "--out", str(tmp_path / "rep")]) == 0
    data = json.loads((tmp_path / "rep" / "study.json").read_text(encoding="utf-8"))
    assert {"weather_effects", "covid", "naive_phase_means", "forecast", "sampling_by_year"} <= set(data)
    assert "SYNTHETIC" in (tmp_path / "rep" / "study.md").read_text(encoding="utf-8")


def test_cli_error(capsys):
    assert main(["ingest", "--csv", "missing.csv"]) == 1
    assert "error:" in capsys.readouterr().err

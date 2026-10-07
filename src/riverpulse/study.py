"""The full study: tidy -> visits -> weather -> index, weather effects, COVID, forecast."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .analysis import covid_its, naive_phase_means, weather_effects
from .config import Settings
from .forecast import forecast
from .ingest import IngestReport, sampling_summary, tidy, visits
from .weather import WeatherProvider, site_weather
from .wqi import ccme_by, exceedances

STUDY_DETERMINANDS = ["ammonia_n", "orthophosphate_p", "do_mg"]


@dataclass
class Prepared:
    tidy: pd.DataFrame
    visits: pd.DataFrame
    report: IngestReport


def prepare(raw: pd.DataFrame, settings: Settings, provider: WeatherProvider, use_pyproj: bool = True) -> Prepared:
    t, report = tidy(raw, settings.lod_policy)
    v = site_weather(visits(t), provider, use_pyproj=use_pyproj)
    v = pd.concat([v, exceedances(v)], axis=1)
    return Prepared(t, v, report)


def run_study(prep: Prepared, settings: Settings) -> dict:
    v = prep.visits
    s, e = settings.covid_start, settings.covid_end
    index = ccme_by(v.assign(year=v["datetime"].dt.year), ["site", "year"])
    by_year = index.groupby("year")["wqi"].agg(["mean", "count"]).round(2)
    result = {
        "sampling_by_year": sampling_summary(v).to_dict(orient="index"),
        "ccme_by_year": by_year.to_dict(orient="index"),
        "ccme_categories": index["category"].value_counts().to_dict(),
        "weather_effects": [],
        "covid": {},
        "naive_phase_means": {},
    }
    for det in STUDY_DETERMINANDS:
        try:
            result["weather_effects"] += weather_effects(v, det).to_dict(orient="records")
        except ValueError as exc:
            result["weather_effects"].append({"determinand": det, "error": str(exc)})
        try:
            result["covid"][det] = covid_its(v, det, s, e, settings.min_samples_per_period)
        except ValueError as exc:
            result["covid"][det] = {"error": str(exc)}
        result["naive_phase_means"][det] = naive_phase_means(v, det, s, e).round(4).to_dict(orient="index")
    try:
        result["forecast"] = forecast(v, "do_mg", seed=settings.seed)
    except ValueError as exc:
        result["forecast"] = {"error": str(exc)}
    return result


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(x) for k, x in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(x) for x in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def format_result(result: dict) -> str:
    lines = ["sampling (visits / sites by year):"]
    lines.append("  " + ", ".join(f"{y}: {r['visits']}/{r['sites']}" for y, r in result["sampling_by_year"].items()))
    lines.append("CCME WQI by year (site-year mean, higher is better):")
    lines.append("  " + ", ".join(f"{y}: {r['mean']}" for y, r in result["ccme_by_year"].items()))
    lines.append("weather effects (coefficient, 95% CI, cluster-robust by site):")
    for r in result["weather_effects"]:
        if "error" in r:
            lines.append(f"  {r['determinand']}: {r['error']}")
        else:
            lines.append(f"  {r['determinand']:<17}{r['term']:<10}{r['coef']:>9.4f} [{r['ci_low']:.4f}, {r['ci_high']:.4f}] ({r['scale']})")
    lines.append("COVID effect (interrupted time series, balanced panel):")
    for det, c in result["covid"].items():
        if "error" in c:
            lines.append(f"  {det}: {c['error']}")
            continue
        during = next(t for t in c["terms"] if t["term"] == "during")
        unit = "%" if c["scale"] == "log" else " units"
        key = "_pct" if c["scale"] == "log" else "_units"
        lines.append(
            f"  {det:<17}during {during['coef' + key]:+.1f}{unit} [{during['ci_low' + key]:+.1f}, {during['ci_high' + key]:+.1f}]"
            f"  ({c['sites_in_panel']} of {c['sites_total']} sites)"
        )
    lines.append("naive phase means (no site matching, for comparison):")
    for det, phases in result["naive_phase_means"].items():
        lines.append("  " + det + ": " + ", ".join(f"{p} {r['mean']:.4f} ({r['sites']} sites)" for p, r in phases.items() if r["mean"] == r["mean"]))
    f = result["forecast"]
    if "error" not in f:
        lines.append(
            f"forecast {f['target']} after {f['cutoff']}: model MAE {f['test_mae']['model']:.3f}, "
            f"site-month climatology {f['test_mae']['site_month_climatology']:.3f}, "
            f"grouped CV (unseen sites) {f['grouped_cv_mae_unseen_sites']['mean']:.3f}"
        )
    return "\n".join(lines)


def write_report(result: dict, out_dir: str | Path, source: str) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data_source": source}
    paths = {"json": out / "study.json", "markdown": out / "study.md"}
    paths["json"].write_text(json.dumps(jsonable({**meta, **result}), indent=2, default=str), encoding="utf-8")
    note = " (SYNTHETIC: not a finding about real rivers)" if "synthetic" in source else ""
    paths["markdown"].write_text(
        f"# riverpulse study\n\n- Created (UTC): {meta['created_utc']}\n- Data source: {source}{note}\n\n```\n"
        + format_result(result) + "\n```\n", encoding="utf-8")
    return paths

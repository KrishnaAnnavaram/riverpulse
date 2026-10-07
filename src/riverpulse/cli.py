"""Command line: ``riverpulse <command>``. Run ``riverpulse --help`` for the list."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from . import study as st
from .analysis import covid_its, naive_phase_means, weather_effects
from .config import ConfigError, Settings, load_dotenv
from .forecast import forecast
from .ingest import IngestError, read_archive
from .synthetic import make_archive
from .weather import OpenMeteoProvider, StationWeather, SyntheticWeather, read_station_csv
from .wqi import ccme_by


def _provider(args, settings):
    if args.weather == "synthetic":
        return SyntheticWeather(settings.seed)
    if args.weather == "open-meteo":
        return OpenMeteoProvider(settings.data_dir / "weather_cache")
    stations = {}
    for spec in args.station or []:
        name, lat, lon, path = spec.split(",", 3)
        stations[name] = (float(lat), float(lon), read_station_csv(path))
    return StationWeather(stations, settings.max_station_km)


def _prepared(args, settings) -> tuple[st.Prepared, str]:
    if args.csv:
        raw = pd.concat([pd.read_csv(p, low_memory=False) for p in args.csv], ignore_index=True)
        source = ", ".join(args.csv)
        use_pyproj = True
    else:
        raw = make_archive(args.sites, seed=settings.seed)
        source = f"synthetic ({args.sites} sites, seed {settings.seed})"
        use_pyproj = False  # the generator links cells with the numpy conversion
    if args.csv and args.weather == "synthetic":
        print("warning: synthetic weather with real water-quality data gives no real weather effect", file=sys.stderr)
    prep = st.prepare(raw, settings, _provider(args, settings), use_pyproj=use_pyproj)
    print(prep.report.summary())
    return prep, source


def cmd_generate(args, settings):
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = make_archive(args.sites, seed=settings.seed)
    raw.to_csv(out, index=False)
    print(f"wrote {out} ({len(raw)} measurements, {args.sites} sites)")
    return 0


def cmd_ingest(args, settings):
    tidy_df, report = read_archive(args.csv, settings.lod_policy)
    print(report.summary())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tidy_df.to_csv(out, index=False)
    print(f"wrote {out}")
    return 0


def cmd_index(args, settings):
    prep, _ = _prepared(args, settings)
    v = prep.visits
    table = ccme_by(v.assign(year=v["datetime"].dt.year), ["site", "year"])
    print(table.groupby("year")["wqi"].describe()[["count", "mean", "min", "max"]].round(2).to_string())
    if args.out:
        table.to_csv(args.out, index=False)
        print(f"wrote {args.out}")
    return 0


def cmd_weather_effects(args, settings):
    prep, _ = _prepared(args, settings)
    for det in args.determinands.split(","):
        print(weather_effects(prep.visits, det).round(4).to_string(index=False))
    return 0


def cmd_covid(args, settings):
    prep, _ = _prepared(args, settings)
    for det in args.determinands.split(","):
        print(json.dumps(st.jsonable(covid_its(prep.visits, det, settings.covid_start, settings.covid_end,
                                               settings.min_samples_per_period)), indent=2))
        print(naive_phase_means(prep.visits, det, settings.covid_start, settings.covid_end).round(4).to_string())
    return 0


def cmd_forecast(args, settings):
    prep, _ = _prepared(args, settings)
    print(json.dumps(forecast(prep.visits, args.target, args.cutoff, seed=settings.seed), indent=2))
    return 0


def cmd_study(args, settings):
    prep, source = _prepared(args, settings)
    result = st.run_study(prep, settings)
    print(st.format_result(result))
    paths = st.write_report(result, args.out or settings.out_dir, source)
    print(f"wrote {paths['markdown']} and {paths['json']}")
    return 0


def cmd_demo(args, settings):
    print("riverpulse offline demo: synthetic archive and synthetic weather, no download, no network\n")
    prep, _ = _prepared(args, settings)
    print(st.format_result(st.run_study(prep, settings)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="riverpulse", description="River water quality, weather effects and the COVID effect.")
    sub = p.add_subparsers(dest="command", required=True)

    def data_args(c):
        c.add_argument("--csv", nargs="+", help="EA archive CSV files (default: synthetic archive)")
        c.add_argument("--sites", type=int, default=60, help="synthetic sites if no --csv")
        c.add_argument("--weather", choices=["synthetic", "open-meteo", "stations"], default="synthetic")
        c.add_argument("--station", action="append", help="NAME,LAT,LON,CSV for --weather stations (repeat)")

    g = sub.add_parser("generate", help="write a synthetic archive CSV in the EA format")
    g.add_argument("--out", default="data/synthetic_archive.csv")
    g.add_argument("--sites", type=int, default=60)
    g.set_defaults(func=cmd_generate)

    i = sub.add_parser("ingest", help="EA archive CSV files to one tidy CSV")
    i.add_argument("--csv", nargs="+", required=True)
    i.add_argument("--out", default="data/tidy.csv")
    i.set_defaults(func=cmd_ingest)

    x = sub.add_parser("index", help="CCME WQI for each site and year")
    data_args(x)
    x.add_argument("--out")
    x.set_defaults(func=cmd_index)

    w = sub.add_parser("weather-effects", help="weather and season models for determinands")
    data_args(w)
    w.add_argument("--determinands", default="ammonia_n,orthophosphate_p,do_mg")
    w.set_defaults(func=cmd_weather_effects)

    c = sub.add_parser("covid", help="interrupted time series on the balanced panel")
    data_args(c)
    c.add_argument("--determinands", default="ammonia_n")
    c.set_defaults(func=cmd_covid)

    f = sub.add_parser("forecast", help="forecast one determinand with a temporal split")
    data_args(f)
    f.add_argument("--target", default="do_mg")
    f.add_argument("--cutoff", default="2021-12-31")
    f.set_defaults(func=cmd_forecast)

    s = sub.add_parser("study", help="full study and report files")
    data_args(s)
    s.add_argument("--out")
    s.set_defaults(func=cmd_study)

    d = sub.add_parser("demo", help="offline demo")
    data_args(d)
    d.set_defaults(func=cmd_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        load_dotenv()
        return args.func(args, Settings.from_env())
    except (ConfigError, IngestError, ValueError, FileNotFoundError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

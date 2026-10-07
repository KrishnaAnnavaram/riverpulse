"""Settings from environment variables. Each value has a default for the offline demo."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

LOD_POLICIES = ("half", "lod", "drop")


class ConfigError(ValueError):
    """An environment variable has a value that the code cannot use."""


def load_dotenv(path: str | Path = ".env") -> None:
    file = Path(path)
    if not file.is_file():
        return
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _get(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


def _num(name: str, default, kind=int):
    raw = _get(name, str(default))
    try:
        return kind(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _date(name: str, default: str) -> date:
    raw = _get(name, default)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a date YYYY-MM-DD, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path("data"))
    out_dir: Path = field(default_factory=lambda: Path("reports"))
    seed: int = 42
    lod_policy: str = "half"
    max_station_km: float = 25.0
    min_samples_per_period: int = 3
    covid_start: date = date(2020, 3, 23)  # first national lockdown in England
    covid_end: date = date(2021, 7, 19)  # last legal restrictions removed in England

    def __post_init__(self) -> None:
        if self.lod_policy not in LOD_POLICIES:
            raise ConfigError(f"RIVERPULSE_LOD_POLICY must be one of {LOD_POLICIES}, got {self.lod_policy!r}")
        if self.covid_start >= self.covid_end:
            raise ConfigError("RIVERPULSE_COVID_START must be before RIVERPULSE_COVID_END")
        if self.max_station_km <= 0 or self.min_samples_per_period < 1:
            raise ConfigError("RIVERPULSE_MAX_STATION_KM must be > 0 and RIVERPULSE_MIN_SAMPLES must be >= 1")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_dir=Path(_get("RIVERPULSE_DATA_DIR", "data")),
            out_dir=Path(_get("RIVERPULSE_OUT", "reports")),
            seed=_num("RIVERPULSE_SEED", 42),
            lod_policy=_get("RIVERPULSE_LOD_POLICY", "half"),
            max_station_km=_num("RIVERPULSE_MAX_STATION_KM", 25.0, float),
            min_samples_per_period=_num("RIVERPULSE_MIN_SAMPLES", 3),
            covid_start=_date("RIVERPULSE_COVID_START", "2020-03-23"),
            covid_end=_date("RIVERPULSE_COVID_END", "2021-07-19"),
        )

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import pytest  # noqa: E402

from riverpulse import study as st  # noqa: E402
from riverpulse.config import Settings  # noqa: E402
from riverpulse.synthetic import make_archive  # noqa: E402
from riverpulse.weather import SyntheticWeather  # noqa: E402


@pytest.fixture(scope="session")
def settings():
    return Settings()


@pytest.fixture(scope="session")
def raw():
    return make_archive(n_sites=60, seed=42)


@pytest.fixture(scope="session")
def prepared(raw, settings):
    return st.prepare(raw, settings, SyntheticWeather(42), use_pyproj=False)

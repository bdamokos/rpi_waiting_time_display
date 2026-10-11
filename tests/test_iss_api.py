import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import requests
from skyfield.api import Loader

import iss
from backoff import ExponentialBackoff


ISS_TLE = b"""ISS (ZARYA)
1 25544U 98067A   24165.53171296  .00016717  00000+0  30112-3 0  9994
2 25544  51.6409 183.2873 0003402  92.7284  30.1764 15.50091203458018
"""


@pytest.fixture
def tle_loader(monkeypatch, tmp_path):
    loader = Loader(str(tmp_path), verbose=False)
    monkeypatch.setattr(iss, "load", loader)
    monkeypatch.setattr(
        iss, "_tle_backoff", ExponentialBackoff(initial_backoff=7200, max_backoff=28800)
    )
    downloads = []

    def download(url, path, *args, **kwargs):
        downloads.append(url)
        Path(path).write_bytes(ISS_TLE)

    monkeypatch.setattr("skyfield.iokit.download", download)
    return loader, downloads


def test_iss_download_uses_supported_query_and_dedicated_cache(tle_loader):
    loader, downloads = tle_loader

    satellite = iss.get_tle_data()

    assert satellite.model.satnum == 25544
    assert downloads == [
        "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE"
    ]
    assert loader.exists("iss.tle")
    assert not loader.exists("gp.php")


def test_fresh_iss_cache_avoids_repeated_downloads(tle_loader):
    _, downloads = tle_loader

    iss.get_tle_data()
    iss.get_tle_data()

    assert len(downloads) == 1


def test_old_iss_cache_refreshes_instead_of_reusing_orbit_forever(tle_loader):
    loader, downloads = tle_loader
    iss.get_tle_data()
    old = (datetime.now() - timedelta(days=2)).timestamp()
    os.utime(loader.path_to("iss.tle"), (old, old))

    satellite = iss.get_tle_data()
    iss.get_tle_data()

    assert satellite.model.satnum == 25544
    assert len(downloads) == 2
    assert loader.days_old("iss.tle") < 1


def test_failed_tle_download_is_not_retried_within_provider_update_window(
    tle_loader, monkeypatch
):
    attempts = []

    def fail(url, path, *args, **kwargs):
        attempts.append(url)
        raise IOError("HTTP 403")

    monkeypatch.setattr("skyfield.iokit.download", fail)
    before = datetime.now()

    with pytest.raises(IOError):
        iss.get_tle_data()
    with pytest.raises(Exception, match="backed off"):
        iss.get_tle_data()

    assert len(attempts) == 1
    assert iss._tle_backoff._next_retry_time >= before + timedelta(hours=2)


def test_position_timeout_returns_control_and_activates_backoff(monkeypatch):
    backoff = ExponentialBackoff(initial_backoff=30, max_backoff=300)
    monkeypatch.setattr(iss, "_api_backoff", backoff)
    attempts = []

    def stalled(url, **kwargs):
        attempts.append((url, kwargs))
        assert kwargs["timeout"] == 10
        raise requests.Timeout("position service stalled")

    monkeypatch.setattr(iss.requests, "get", stalled)

    assert iss.get_iss_position() is None
    assert iss.get_iss_position() is None
    assert len(attempts) == 1
    assert backoff.get_failure_count() == 1

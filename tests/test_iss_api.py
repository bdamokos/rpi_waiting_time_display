import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from skyfield.api import Loader

import iss
from backoff import ExponentialBackoff


ISS_TLE = b"""ISS (ZARYA)
1 25544U 98067A   24165.53171296  .00016717  00000+0  30112-3 0  9994
2 25544  51.6409 183.2873 0003402  92.7284  30.1764 15.50091203458018
"""
ISS_NAN_TLE = b"\n".join([
    *ISS_TLE.splitlines()[:2],
    ISS_TLE.splitlines()[2][:52] + b"        nan" + ISS_TLE.splitlines()[2][63:],
]) + b"\n"
ISS_NAN_EPOCH_TLE = ISS_TLE.replace(b"24165.53171296", b"24         nan")


class TleResponse:
    def __init__(self, payload=ISS_TLE, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        for offset in range(0, len(self.payload), chunk_size):
            yield self.payload[offset:offset + chunk_size]

    def close(self):
        self.closed = True


def age_cache(loader, hours):
    old = (datetime.now() - timedelta(hours=hours)).timestamp()
    os.utime(loader.path_to("iss.tle"), (old, old))


@pytest.fixture
def tle_loader(monkeypatch, tmp_path):
    loader = Loader(str(tmp_path), verbose=False)
    monkeypatch.setattr(iss, "load", loader)
    monkeypatch.setattr(
        iss, "_tle_backoff", ExponentialBackoff(initial_backoff=7200, max_backoff=28800)
    )
    downloads = []

    def download(url, **kwargs):
        downloads.append(url)
        assert kwargs["timeout"] == 10
        assert kwargs["stream"] is True
        return TleResponse()

    monkeypatch.setattr(iss.requests, "get", download)
    monkeypatch.setattr(
        "skyfield.iokit.download",
        Mock(side_effect=AssertionError("Skyfield must only parse local data")),
    )
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
    age_cache(loader, 48)

    satellite = iss.get_tle_data()
    iss.get_tle_data()

    assert satellite.model.satnum == 25544
    assert len(downloads) == 2
    assert loader.days_old("iss.tle") < 1


def test_failed_tle_download_is_not_retried_within_provider_update_window(
    tle_loader, monkeypatch
):
    attempts = []

    def fail(url, **kwargs):
        attempts.append(url)
        raise requests.HTTPError("HTTP 403")

    monkeypatch.setattr(iss.requests, "get", fail)
    before = datetime.now()

    with pytest.raises(requests.HTTPError):
        iss.get_tle_data()
    with pytest.raises(Exception, match="backed off"):
        iss.get_tle_data()

    assert len(attempts) == 1
    assert iss._tle_backoff._next_retry_time >= before + timedelta(hours=2)


def test_failed_refresh_reuses_last_good_cache_during_remote_backoff(
    tle_loader, monkeypatch
):
    loader, _ = tle_loader
    original = iss.get_tle_data()
    age_cache(loader, 25)
    cache_file = Path(loader.path_to("iss.tle"))
    previous_mtime = cache_file.stat().st_mtime
    response = TleResponse(status_code=503)
    request = Mock(return_value=response)
    monkeypatch.setattr(iss.requests, "get", request)

    refreshed = iss.get_tle_data()
    next_retry = iss._tle_backoff._next_retry_time
    reused = iss.get_tle_data()

    assert refreshed.model.satnum == reused.model.satnum == 25544
    assert refreshed.epoch.tt == reused.epoch.tt == original.epoch.tt
    assert request.call_count == 1
    assert request.call_args.kwargs["timeout"] == 10
    assert request.call_args.kwargs["stream"] is True
    assert request.call_args.kwargs["headers"]["Accept"] == "text/plain"
    assert response.closed
    assert cache_file.read_bytes() == ISS_TLE
    assert cache_file.stat().st_mtime == previous_mtime
    assert iss._tle_backoff.get_failure_count() == 1
    assert iss._tle_backoff._next_retry_time == next_retry


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"garbage",
        b"<html>temporarily unavailable</html>",
        ISS_TLE.replace(b"25544", b"12345"),
        b"ISS\n" + b"1 25544".ljust(69) + b"\n" + b"2 25544".ljust(69) + b"\n",
        ISS_NAN_TLE,
        ISS_NAN_EPOCH_TLE,
        b"x" * (iss._ISS_TLE_MAX_BYTES + 1),
    ],
    ids=["empty", "garbage", "html", "wrong-norad", "invalid-orbit", "nan-orbit", "nan-epoch", "oversized"],
)
def test_invalid_refresh_preserves_last_good_cache(tle_loader, monkeypatch, payload):
    loader, _ = tle_loader
    original = iss.get_tle_data()
    age_cache(loader, 25)
    cache_file = Path(loader.path_to("iss.tle"))
    previous_mtime = cache_file.stat().st_mtime
    response = TleResponse(payload)
    request = Mock(return_value=response)
    monkeypatch.setattr(iss.requests, "get", request)

    satellite = iss.get_tle_data()
    iss.get_tle_data()

    assert satellite.model.satnum == 25544
    assert satellite.epoch.tt == original.epoch.tt
    assert cache_file.read_bytes() == ISS_TLE
    assert cache_file.stat().st_mtime == previous_mtime
    assert request.call_count == 1
    assert response.closed
    assert iss._tle_backoff.get_failure_count() == 1
    assert not list(cache_file.parent.glob(".iss-tle-*"))


@pytest.mark.parametrize("payload", [ISS_NAN_TLE, ISS_NAN_EPOCH_TLE], ids=["orbit", "epoch"])
def test_nan_local_cache_is_rejected_during_backoff(tle_loader, monkeypatch, payload):
    loader, _ = tle_loader
    cache_file = Path(loader.path_to("iss.tle"))
    cache_file.write_bytes(payload)
    iss._tle_backoff.update_backoff_state(False)
    request = Mock(side_effect=AssertionError("backoff must not download"))
    monkeypatch.setattr(iss.requests, "get", request)

    assert iss._cached_iss_tle() is None
    with pytest.raises(Exception, match="backed off"):
        iss.get_tle_data()

    request.assert_not_called()
    assert cache_file.read_bytes() == payload


@pytest.mark.parametrize(
    "position, velocity, message",
    [
        ([float("nan"), 1, 1], [1, 1, 1], None),
        ([1, 1, 1], [1, float("inf"), 1], None),
        ([1, 1, 1], [1, 1, 1], "satellite has decayed"),
    ],
    ids=["non-finite-position", "non-finite-velocity", "sgp4-error"],
)
def test_unusable_epoch_propagation_is_rejected(
    tle_loader, monkeypatch, position, velocity, message
):
    result = Mock(
        message=message, position=Mock(km=position), velocity=Mock(km_per_s=velocity)
    )
    propagate = Mock(return_value=result)
    monkeypatch.setattr("skyfield.sgp4lib.EarthSatellite.at", propagate)

    with pytest.raises(ValueError, match="propagate"):
        iss._parse_iss_tle(ISS_TLE)

    propagate.assert_called_once()


def test_invalid_download_without_good_cache_is_rejected(tle_loader, monkeypatch):
    loader, _ = tle_loader
    response = TleResponse(ISS_TLE.replace(b"25544", b"12345"))
    monkeypatch.setattr(iss.requests, "get", Mock(return_value=response))

    with pytest.raises(ValueError, match="25544"):
        iss.get_tle_data()

    assert response.closed
    assert not loader.exists("iss.tle")


def test_validated_refresh_atomically_promotes_new_orbit(tle_loader, monkeypatch):
    loader, _ = tle_loader
    original = iss.get_tle_data()
    age_cache(loader, 25)
    updated = ISS_TLE.replace(b"24165.53171296", b"24166.53171296")
    response = TleResponse(updated)
    request = Mock(return_value=response)
    monkeypatch.setattr(iss.requests, "get", request)

    refreshed = iss.get_tle_data()
    cached = iss.get_tle_data()

    assert refreshed.model.satnum == cached.model.satnum == 25544
    assert refreshed.epoch.tt == cached.epoch.tt == original.epoch.tt + 1
    cache_file = Path(loader.path_to("iss.tle"))
    assert cache_file.read_bytes() == updated
    assert loader.days_old("iss.tle") < 1
    assert not list(cache_file.parent.glob(".iss-tle-*"))
    assert request.call_count == 1
    assert response.closed
    assert iss._tle_backoff.get_failure_count() == 0


def test_failed_atomic_promotion_keeps_previous_cache(tle_loader, monkeypatch):
    loader, _ = tle_loader
    original = iss.get_tle_data()
    age_cache(loader, 25)
    updated = ISS_TLE.replace(b"24165.53171296", b"24166.53171296")
    monkeypatch.setattr(iss.requests, "get", Mock(return_value=TleResponse(updated)))
    monkeypatch.setattr(iss.os, "replace", Mock(side_effect=PermissionError("read only")))

    fallback = iss.get_tle_data()

    assert fallback.epoch.tt == original.epoch.tt
    cache_file = Path(loader.path_to("iss.tle"))
    assert cache_file.read_bytes() == ISS_TLE
    assert not list(cache_file.parent.glob(".iss-tle-*"))
    assert iss._tle_backoff.get_failure_count() == 1


def test_overage_cache_is_rejected_during_backoff_without_network(
    tle_loader, monkeypatch
):
    loader, _ = tle_loader
    iss.get_tle_data()
    age_cache(loader, 49)
    iss._tle_backoff.update_backoff_state(False)
    request = Mock(side_effect=AssertionError("backoff must not download"))
    monkeypatch.setattr(iss.requests, "get", request)

    with pytest.raises(Exception, match="backed off"):
        iss.get_tle_data()

    request.assert_not_called()
    assert iss._tle_backoff.get_failure_count() == 1


def test_overage_cache_is_not_a_fallback_after_failed_refresh(tle_loader, monkeypatch):
    loader, _ = tle_loader
    iss.get_tle_data()
    age_cache(loader, 49)
    monkeypatch.setattr(
        iss.requests, "get", Mock(return_value=TleResponse(status_code=503))
    )

    with pytest.raises(requests.HTTPError, match="503"):
        iss.get_tle_data()

    assert Path(loader.path_to("iss.tle")).read_bytes() == ISS_TLE


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

import errno
import builtins
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

import flights

OPERATOR = {"iata": "EX", "name": "Example Air", "shortname": "Example"}
AIRCRAFT = {"manufacturer": "Example", "type": "A320"}


@pytest.fixture
def metadata_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("flight_metadata_cache_dir", raising=False)
    return tmp_path / "cache"


@pytest.mark.parametrize(
    "lookup,code,payload,filename,expected",
    [
        (flights.aeroapi_get_operator, "EX", OPERATOR, "operators.json", "Example Air"),
        (
            flights.aeroapi_get_plane_type,
            "A320",
            AIRCRAFT,
            "types.json",
            ("Example", "A320"),
        ),
    ],
)
def test_metadata_is_persisted_in_writable_cache_and_reused(
    metadata_cache, monkeypatch, lookup, code, payload, filename, expected
):
    fetch = Mock(return_value=payload)
    monkeypatch.setattr(flights, "aeroapi_get_data", fetch)

    assert lookup(code) == expected
    assert (metadata_cache / filename).is_file()
    assert not Path(filename).exists()
    assert lookup(code) == expected
    fetch.assert_called_once()


@pytest.mark.parametrize(
    "lookup,code,cached,filename,expected",
    [
        (
            flights.aeroapi_get_operator,
            "EX",
            "Legacy Airline",
            "operators.json",
            "Legacy Airline",
        ),
        (
            flights.aeroapi_get_plane_type,
            "A320",
            AIRCRAFT,
            "types.json",
            ("Example", "A320"),
        ),
    ],
)
@pytest.mark.parametrize("empty_configured_cache", [False, True])
def test_existing_legacy_metadata_remains_readable(
    metadata_cache, monkeypatch, lookup, code, cached, filename, expected,
    empty_configured_cache
):
    Path(filename).write_text(json.dumps({code: cached}), encoding="utf-8")
    if empty_configured_cache:
        metadata_cache.mkdir()
        (metadata_cache / filename).write_text("{}", encoding="utf-8")
    fetch = Mock(side_effect=RuntimeError("API unavailable"))
    monkeypatch.setattr(flights, "aeroapi_get_data", fetch)

    assert lookup(code) == expected
    fetch.assert_not_called()


@pytest.mark.parametrize("contents", ["{broken-json", "[]"])
def test_invalid_operator_cache_does_not_interrupt_enrichment(
    metadata_cache, monkeypatch, contents
):
    metadata_cache.mkdir()
    (metadata_cache / "operators.json").write_text(contents, encoding="utf-8")
    monkeypatch.setattr(flights, "aeroapi_get_data", Mock(return_value=OPERATOR))

    assert flights.aeroapi_get_operator("EX") == "Example Air"
    assert (
        json.loads((metadata_cache / "operators.json").read_text())["EX"]["name"]
        == "Example Air"
    )


@pytest.mark.parametrize(
    "lookup,code,payload,expected",
    [
        (flights.aeroapi_get_operator, "EX", OPERATOR, "Example Air"),
        (flights.aeroapi_get_plane_type, "A320", AIRCRAFT, ("Example", "A320")),
    ],
)
def test_unwritable_cache_does_not_discard_successful_metadata(
    metadata_cache, monkeypatch, lookup, code, payload, expected
):
    # A file at the configured directory models an unavailable writable volume.
    metadata_cache.write_text("unavailable", encoding="utf-8")
    monkeypatch.setattr(flights, "aeroapi_get_data", Mock(return_value=payload))

    assert lookup(code) == expected
    assert metadata_cache.read_text() == "unavailable"


def test_read_only_application_directory_uses_writable_cache(
    metadata_cache, monkeypatch
):
    original_open = builtins.open

    def read_only_app_open(file, mode="r", *args, **kwargs):
        if "w" in mode and Path(file).parent == Path("."):
            raise OSError(errno.EROFS, "Read-only file system")
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", read_only_app_open)
    monkeypatch.setattr(flights, "aeroapi_get_data", Mock(return_value=OPERATOR))

    assert flights.aeroapi_get_operator("EX") == "Example Air"
    assert (metadata_cache / "operators.json").exists()


def test_corrupt_legacy_cache_is_ignored(metadata_cache, monkeypatch):
    Path("operators.json").write_text("{broken-json", encoding="utf-8")
    monkeypatch.setattr(flights, "aeroapi_get_data", Mock(return_value=OPERATOR))

    assert flights.aeroapi_get_operator("EX") == "Example Air"
    assert (metadata_cache / "operators.json").exists()


def test_failed_atomic_replace_preserves_previous_metadata(metadata_cache, monkeypatch):
    metadata_cache.mkdir()
    cache_file = metadata_cache / "operators.json"
    previous = {"OLD": "Existing Airline"}
    cache_file.write_text(json.dumps(previous), encoding="utf-8")
    monkeypatch.setattr(flights, "aeroapi_get_data", Mock(return_value=OPERATOR))

    def fail_replace(self, target):
        raise OSError(errno.EROFS, "Read-only file system")

    monkeypatch.setattr(Path, "replace", fail_replace)

    assert flights.aeroapi_get_operator("EX") == "Example Air"
    assert json.loads(cache_file.read_text()) == previous
    assert sorted(path.name for path in metadata_cache.iterdir()) == ["operators.json"]


def test_configured_cache_directory_preserves_legacy_entries(
    metadata_cache, monkeypatch, tmp_path
):
    custom = tmp_path / "writable" / "metadata"
    monkeypatch.setenv("flight_metadata_cache_dir", str(custom))
    Path("operators.json").write_text(
        json.dumps({"OLD": "Existing Airline"}), encoding="utf-8"
    )
    monkeypatch.setattr(flights, "aeroapi_get_data", Mock(return_value=OPERATOR))

    assert flights.aeroapi_get_operator("EX") == "Example Air"
    assert json.loads((custom / "operators.json").read_text()) == {
        "OLD": "Existing Airline",
        "EX": {
            **OPERATOR,
            "icao": None,
            "callsign": None,
            "country": None,
            "location": None,
            "phone": None,
            "url": None,
            "wiki_url": None,
            "alternatives": [],
        },
    }


@pytest.mark.parametrize(
    "lookup,filename,legacy,configured,code,payload,expected_old,expected_shared",
    [
        (
            flights.aeroapi_get_operator, "operators.json",
            {"OLD": "Legacy Airline", "SHARED": "Legacy duplicate"},
            {"SHARED": "Configured Airline", "RECENT": "Recent Airline"},
            "EX", OPERATOR, "Legacy Airline", "Configured Airline",
        ),
        (
            flights.aeroapi_get_plane_type, "types.json",
            {
                "OLD": {"manufacturer": "Legacy", "type": "Old aircraft"},
                "SHARED": {"manufacturer": "Legacy", "type": "Duplicate"},
            },
            {
                "SHARED": {"manufacturer": "Configured", "type": "Current"},
                "RECENT": {"manufacturer": "Recent", "type": "Aircraft"},
            },
            "A320", AIRCRAFT, ("Legacy", "Old aircraft"),
            ("Configured", "Current"),
        ),
    ],
)
@pytest.mark.parametrize("duplicate_keys", [False, True])
def test_mixed_caches_reuse_and_preserve_all_metadata(
    metadata_cache, monkeypatch, lookup, filename, legacy, configured,
    code, payload, expected_old, expected_shared, duplicate_keys
):
    configured = dict(configured)
    if not duplicate_keys:
        configured.pop("SHARED")
        expected_shared = legacy["SHARED"]
        if isinstance(expected_shared, dict):
            expected_shared = (expected_shared["manufacturer"], expected_shared["type"])
    Path(filename).write_text(json.dumps(legacy), encoding="utf-8")
    metadata_cache.mkdir()
    cache_file = metadata_cache / filename
    cache_file.write_text(json.dumps(configured), encoding="utf-8")
    fetch = Mock(side_effect=RuntimeError("API unavailable"))
    monkeypatch.setattr(flights, "aeroapi_get_data", fetch)

    assert lookup("OLD") == expected_old
    assert lookup("SHARED") == expected_shared
    fetch.assert_not_called()

    fetch.side_effect = None
    fetch.return_value = payload
    lookup(code)

    persisted = json.loads(cache_file.read_text())
    assert set(persisted) == {"OLD", "SHARED", "RECENT", code}
    assert persisted["OLD"] == legacy["OLD"]
    assert persisted["SHARED"] == configured.get("SHARED", legacy["SHARED"])
    assert persisted["RECENT"] == configured["RECENT"]
    fetch.assert_called_once()
    assert json.loads(Path(filename).read_text()) == legacy

import logging

from log_config import configured_log_level


def test_configured_log_level_defaults_to_info(monkeypatch):
    monkeypatch.delenv("display_log_level", raising=False)

    assert configured_log_level() == logging.INFO


def test_configured_log_level_accepts_named_level():
    assert configured_log_level("warning") == logging.WARNING


def test_configured_log_level_rejects_invalid_level():
    assert configured_log_level("chatty") == logging.INFO

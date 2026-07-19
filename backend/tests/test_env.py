import pytest
from django.core.exceptions import ImproperlyConfigured

from config import env


def test_require_raises_clear_message_when_missing(monkeypatch):
    monkeypatch.delenv("SOME_MISSING_VAR", raising=False)
    with pytest.raises(ImproperlyConfigured, match="Missing required env var SOME_MISSING_VAR"):
        env.require("SOME_MISSING_VAR", "used in test")


def test_require_returns_value_when_set(monkeypatch):
    monkeypatch.setenv("SOME_VAR", "hello")
    assert env.require("SOME_VAR", "used in test") == "hello"


def test_require_treats_blank_as_missing(monkeypatch):
    monkeypatch.setenv("BLANK_VAR", "   ")
    with pytest.raises(ImproperlyConfigured):
        env.require("BLANK_VAR", "used in test")


def test_db_url_parses_managed_connection_url(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgres://u:p@dbhost:6543/mydb")
    cfg = env.db_url("TEST_DATABASE_URL")
    assert cfg["ENGINE"] == "django.db.backends.postgresql"
    assert cfg["NAME"] == "mydb"
    assert cfg["HOST"] == "dbhost"
    assert cfg["USER"] == "u"
    assert str(cfg["PORT"]) == "6543"


def test_db_url_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert env.db_url("TEST_DATABASE_URL") is None

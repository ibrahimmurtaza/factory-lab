"""Tests for ActorResolver."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from factory.control.actor import ActorResolver
from factory.errors import ActorResolutionError


def test_resolve_from_env_var() -> None:
    resolver = ActorResolver()
    with patch.dict(os.environ, {"FACTORY_LAB_ACTOR": "alice"}, clear=True):
        assert resolver.resolve() == "alice"


def test_resolve_trims_env_var() -> None:
    resolver = ActorResolver()
    with patch.dict(os.environ, {"FACTORY_LAB_ACTOR": "  bob  "}, clear=True):
        assert resolver.resolve() == "bob"


def test_resolve_falls_back_to_getuser_when_env_unset() -> None:
    resolver = ActorResolver()
    with patch.dict(os.environ, {}, clear=True):
        with patch("getpass.getuser", return_value="carol"):
            assert resolver.resolve() == "carol"


def test_resolve_falls_back_to_getuser_when_env_blank() -> None:
    resolver = ActorResolver()
    with patch.dict(os.environ, {"FACTORY_LAB_ACTOR": "   "}, clear=True):
        with patch("getpass.getuser", return_value="dave"):
            assert resolver.resolve() == "dave"


def test_resolve_env_var_priority_over_getuser() -> None:
    resolver = ActorResolver()
    with patch.dict(os.environ, {"FACTORY_LAB_ACTOR": "eve"}, clear=True):
        with patch("getpass.getuser", return_value="should-not-be-used"):
            assert resolver.resolve() == "eve"


def test_resolve_trims_getuser_result() -> None:
    resolver = ActorResolver()
    with patch.dict(os.environ, {}, clear=True):
        with patch("getpass.getuser", return_value="  frank  "):
            assert resolver.resolve() == "frank"


def test_resolve_raises_when_env_blank_and_getuser_empty() -> None:
    resolver = ActorResolver()
    with patch.dict(os.environ, {"FACTORY_LAB_ACTOR": ""}, clear=True):
        with patch("getpass.getuser", return_value=""):
            with pytest.raises(ActorResolutionError):
                resolver.resolve()


def test_resolve_raises_when_env_unset_and_getuser_empty() -> None:
    resolver = ActorResolver()
    with patch.dict(os.environ, {}, clear=True):
        with patch("getpass.getuser", return_value=""):
            with pytest.raises(ActorResolutionError):
                resolver.resolve()


def test_resolve_raises_when_getuser_whitespace_only() -> None:
    resolver = ActorResolver()
    with patch.dict(os.environ, {}, clear=True):
        with patch("getpass.getuser", return_value="   \t\n"):
            with pytest.raises(ActorResolutionError):
                resolver.resolve()


def test_resolve_error_message_is_user_facing() -> None:
    resolver = ActorResolver()
    with patch.dict(os.environ, {}, clear=True):
        with patch("getpass.getuser", return_value=""):
            with pytest.raises(ActorResolutionError) as exc_info:
                resolver.resolve()
        assert "FACTORY_LAB_ACTOR" in str(exc_info.value)
        assert "getpass.getuser" in str(exc_info.value)


def test_injectable_resolver() -> None:
    called = []

    def custom_resolver() -> str:
        called.append(True)
        return "injected-actor"

    resolver = ActorResolver(resolver=custom_resolver)
    assert resolver.resolve() == "injected-actor"
    assert called == [True]


def test_injectable_resolver_returns_none_raises() -> None:
    resolver = ActorResolver(resolver=lambda: None)
    with pytest.raises(ActorResolutionError):
        resolver.resolve()


def test_injectable_resolver_returns_blank_raises() -> None:
    resolver = ActorResolver(resolver=lambda: "   ")
    with pytest.raises(ActorResolutionError):
        resolver.resolve()


def test_resolver_is_reusable() -> None:
    resolver = ActorResolver()
    with patch.dict(os.environ, {"FACTORY_LAB_ACTOR": "grace"}, clear=True):
        first = resolver.resolve()
        second = resolver.resolve()
    assert first == second == "grace"

"""Tests for soft-import discovery: degradation when extras are absent, presence when installed."""
from __future__ import annotations

import pytest

from conftest import fake_modules, hidden_modules
from nirs4all_providers import (
    Capabilities,
    ProviderUnavailable,
    available_providers,
    get_provider,
    provider_capabilities,
    provider_health,
    provider_ids,
)

_ALL_BACKINGS = (
    "nirs4all_datasets",
    "nirs4all_repository",
    "nirs4all_benchmarks",
    "nirs4all_papers",
)


def test_provider_ids_are_the_four_boundaries() -> None:
    assert provider_ids() == ("datasets", "repository", "benchmarks", "papers")


def test_get_provider_unknown_id_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown provider"):
        get_provider("nope")


def test_all_absent_degrades_gracefully() -> None:
    with hidden_modules(*_ALL_BACKINGS):
        assert available_providers() == []
        caps = provider_capabilities("repository")
        assert isinstance(caps, Capabilities)
        assert caps.executes is False
        with pytest.raises(ProviderUnavailable) as excinfo:
            get_provider("datasets")
        assert "nirs4all-providers[datasets]" in str(excinfo.value)
        health = provider_health("repository")
        assert health.available is False
        assert health.version is None


def test_only_installed_extra_is_listed() -> None:
    fake = {"nirs4all_datasets": {"__version__": "7.7.7", "list": lambda root, **f: []}}
    with hidden_modules("nirs4all_repository", "nirs4all_benchmarks", "nirs4all_papers"), fake_modules(fake):
        assert available_providers() == ["datasets"]
        provider = get_provider("datasets")
        assert provider.provider_id == "datasets"
        assert provider.version() == "7.7.7"
        health = provider_health("datasets")
        assert health.available is True
        assert health.version == "7.7.7"


def test_get_provider_forwards_config(tmp_path: object) -> None:
    with fake_modules({"nirs4all_benchmarks": {"__version__": "0.1.0"}}):
        provider = get_provider("benchmarks", store_root=str(tmp_path))
        assert provider.provider_id == "benchmarks"
        assert provider.version() == "0.1.0"

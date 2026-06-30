"""Tests for the provider contract value objects and the structural protocol."""
from __future__ import annotations

from conftest import fake_modules
from nirs4all_providers import (
    BenchmarkProvider,
    Capabilities,
    DatasetProvider,
    Health,
    PaperExportProvider,
    PipelineProvider,
    ProviderPlugin,
    WriteAccess,
)


def test_write_access_values() -> None:
    assert WriteAccess.NONE.value == "none"
    assert WriteAccess.LOCAL_CACHE.value == "local-cache"
    assert WriteAccess.LOCAL_OUTPUT.value == "local-output"
    assert WriteAccess.GATED.value == "gated"


def test_health_is_frozen_with_defaults() -> None:
    health = Health(provider_id="datasets", available=True)
    assert health.reachable is None
    assert health.version is None
    assert health.detail is None


def test_capabilities_defaults() -> None:
    caps = Capabilities(serves=("list_datasets",))
    assert caps.executes is False
    assert caps.writes is WriteAccess.NONE
    assert caps.portability is None


def test_all_adapters_satisfy_protocol_structurally() -> None:
    fakes = {
        "nirs4all_datasets": {"__version__": "0"},
        "nirs4all_repository": {"__version__": "0"},
        "nirs4all_benchmarks": {"__version__": "0"},
        "nirs4all_papers": {"__version__": "0"},
    }
    with fake_modules(fakes):
        for adapter in (DatasetProvider(), PipelineProvider(), BenchmarkProvider(), PaperExportProvider()):
            assert isinstance(adapter, ProviderPlugin)
            assert isinstance(adapter.provider_id, str)
            assert isinstance(adapter.capabilities(), Capabilities)
            assert isinstance(adapter.health(), Health)


def test_non_adapter_is_not_a_provider_plugin() -> None:
    assert not isinstance(object(), ProviderPlugin)

"""Health + conformance tests.

Two layers:

* **Self-conformance & health matrix** — hermetic, always run. They pin the *adapter* surface: every
  name a provider advertises in ``capabilities().serves`` must be a real method, the registry ids must
  match the adapters, and ``provider_health`` must report the right shape whether a backing is faked-in
  or hidden. No backing package is needed.

* **Real-API conformance** — grounded in the *actual* ``nirs4all-datasets`` / ``-repository`` /
  ``-benchmarks`` / ``-papers`` public APIs. Each is guarded by ``pytest.importorskip``: where the
  matching extra is installed it asserts the backing still exposes exactly the callables and keyword
  parameters the adapter delegates to (so an upstream rename breaks *here*, loudly, instead of at a
  user's call site); where the extra is absent the test **skips** rather than fails. In an environment
  with none of the four extras installed, all four skip — that is an environment limit, not a defect.
"""
from __future__ import annotations

import inspect

import pytest

from conftest import fake_modules, hidden_modules
from nirs4all_providers import (
    BenchmarkProvider,
    Capabilities,
    DatasetProvider,
    Health,
    PaperExportProvider,
    PipelineProvider,
    ProviderPlugin,
    provider_health,
    provider_ids,
)

_ADAPTERS = {
    "datasets": DatasetProvider,
    "repository": PipelineProvider,
    "benchmarks": BenchmarkProvider,
    "papers": PaperExportProvider,
}

# Minimal fakes: just enough for the availability/reachability probes to run without a real backing.
_FAKE_BACKINGS = {
    "nirs4all_datasets": {"__version__": "1", "list": lambda root, **f: []},
    "nirs4all_repository": {"__version__": "1"},
    "nirs4all_benchmarks": {"__version__": "1"},
    "nirs4all_papers": {"__version__": "1"},
}


# ── self-conformance (hermetic) ──────────────────────────────────────────────────────────────


def test_registry_ids_match_adapter_provider_ids() -> None:
    assert set(provider_ids()) == set(_ADAPTERS)
    for pid, cls in _ADAPTERS.items():
        assert cls.provider_id == pid


def test_capabilities_serve_names_are_real_callable_methods() -> None:
    for cls in _ADAPTERS.values():
        adapter = cls()
        assert isinstance(adapter, ProviderPlugin)
        caps = adapter.capabilities()
        assert isinstance(caps, Capabilities)
        assert caps.serves, f"{cls.__name__} advertises no read surface"
        for name in caps.serves:
            member = getattr(adapter, name, None)
            assert callable(member), f"{cls.__name__}.serves lists {name!r} but it is not a method"


def test_dataset_provider_exposes_soft_package_bridge_as_typed_read() -> None:
    # The package bridge is optional because nirs4all-io is optional, but the adapter surface is stable
    # and reports typed availability/refusal through dataset_package_capability().
    adapter = DatasetProvider()
    assert callable(adapter.to_dataset_package)
    assert callable(adapter.describe_dataset_package)
    assert callable(adapter.dataset_package_capability)
    assert "to_dataset_package" in adapter.capabilities().serves
    assert "describe_dataset_package" in adapter.capabilities().serves


def test_dataset_provider_exposes_retrieve_as_local_cache_read() -> None:
    adapter = DatasetProvider()
    assert callable(adapter.retrieve_dataset)
    assert "retrieve_dataset" in adapter.capabilities().serves


# ── health matrix (hermetic) ─────────────────────────────────────────────────────────────────


def test_health_matrix_available_via_fakes() -> None:
    with fake_modules(_FAKE_BACKINGS):
        for pid in provider_ids():
            health = provider_health(pid)
            assert isinstance(health, Health)
            assert health.provider_id == pid
            assert health.available is True
            assert health.version == "1"


def test_health_matrix_absent_degrades_uniformly() -> None:
    with hidden_modules(*_FAKE_BACKINGS):
        for pid in provider_ids():
            health = provider_health(pid)
            assert health.available is False
            assert health.version is None
            assert health.reachable is None


# ── real-API conformance (skips without the matching extra) ───────────────────────────────────


def test_conformance_datasets_real_api() -> None:
    mod = pytest.importorskip("nirs4all_datasets")
    for name in ("list", "card", "get", "retrieve"):
        assert callable(getattr(mod, name, None)), f"nirs4all_datasets.{name} missing"
    get_params = inspect.signature(mod.get).parameters
    for kw in ("root", "cache_dir"):
        assert kw in get_params, f"nirs4all_datasets.get lost keyword {kw!r}"
    retrieve_params = inspect.signature(mod.retrieve).parameters
    for kw in ("root", "cache_dir"):
        assert kw in retrieve_params, f"nirs4all_datasets.retrieve lost keyword {kw!r}"
    # The NirsDataset.to_nirs4all bridge to_spectro_dataset relies on.
    assert hasattr(mod.NirsDataset, "to_nirs4all")


def test_conformance_repository_real_api() -> None:
    mod = pytest.importorskip("nirs4all_repository")
    for name in ("list", "card", "get", "fetch"):
        assert callable(getattr(mod, name, None)), f"nirs4all_repository.{name} missing"
    for fn_name in ("get", "fetch"):
        params = inspect.signature(getattr(mod, fn_name)).parameters
        for kw in ("root", "cache_dir", "verify", "with_artifacts"):
            assert kw in params, f"nirs4all_repository.{fn_name} lost keyword {kw!r}"
    list_params = inspect.signature(mod.list).parameters
    for kw in ("framework", "task", "tag", "kind", "trust", "root"):
        assert kw in list_params, f"nirs4all_repository.list lost filter {kw!r}"
    for method in ("recipe", "verify", "to_nirs4all"):
        assert callable(getattr(mod.Pipeline, method, None)), f"Pipeline.{method} missing"


def test_conformance_benchmarks_real_api() -> None:
    pytest.importorskip("nirs4all_benchmarks")
    from nirs4all_benchmarks.store.arena_store import ArenaStore
    from nirs4all_benchmarks.store.queries import Queries

    assert "root" in inspect.signature(ArenaStore.__init__).parameters
    for name in (
        "overview",
        "datasets",
        "operators",
        "pipelines",
        "leaderboard",
        "run_detail",
        "residuals",
        "planned",
    ):
        assert callable(getattr(Queries, name, None)), f"Queries.{name} missing"
    assert "partition" in inspect.signature(Queries.residuals).parameters
    leaderboard_params = inspect.signature(Queries.leaderboard).parameters
    assert "metric" in leaderboard_params and "scope" in leaderboard_params


def test_conformance_papers_real_api() -> None:
    pytest.importorskip("nirs4all_papers")
    from nirs4all_papers.bibliography import build_bibliography
    from nirs4all_papers.bundle import read_bundle
    from nirs4all_papers.model import load_catalog, load_paper
    from nirs4all_papers.provenance import citation_cff, paper_bibtex
    from nirs4all_papers.site import build_site

    for fn in (read_bundle, load_paper, load_catalog, build_bibliography, citation_cff, paper_bibtex, build_site):
        assert callable(fn)
    assert "io_wasm" in inspect.signature(build_site).parameters

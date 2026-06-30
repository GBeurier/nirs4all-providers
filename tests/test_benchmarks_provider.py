"""Tests for BenchmarkProvider read delegation (over faked nirs4all_benchmarks submodules)."""
from __future__ import annotations

import pytest

from conftest import fake_modules, hidden_modules
from nirs4all_providers import BenchmarkProvider, ProviderUnavailable, WriteAccess


class _FakeStore:
    def __init__(self, root: str) -> None:
        self.root = root


class _FakeQueries:
    def __init__(self, store: _FakeStore) -> None:
        self.store = store

    def pipelines(self) -> list[dict[str, object]]:
        return [{"pipeline_dag_hash": "h1", "human_label": "A"}, {"pipeline_dag_hash": "h2", "human_label": "B"}]

    def leaderboard(self, **query: object) -> dict[str, object]:
        return {"rows": [], "q": query}

    def run_detail(self, execution_hash: str) -> dict[str, object] | None:
        return {"execution_hash": execution_hash} if execution_hash == "e1" else None

    def planned(self) -> list[dict[str, object]]:
        return [{"plan_id": 1, "status": "planned"}]


def _fakes() -> dict[str, dict[str, object]]:
    return {
        "nirs4all_benchmarks": {"__version__": "0.1.0"},
        "nirs4all_benchmarks.store": {},
        "nirs4all_benchmarks.store.arena_store": {"ArenaStore": _FakeStore},
        "nirs4all_benchmarks.store.queries": {"Queries": _FakeQueries},
    }


def test_version_health_and_capabilities(tmp_path: object) -> None:
    with fake_modules(_fakes()):
        provider = BenchmarkProvider(store_root=str(tmp_path))
        assert provider.version() == "0.1.0"
        health = provider.health()
        assert health.available is True
        assert health.reachable is False  # tmp store has no arena.sqlite yet
        caps = provider.capabilities()
    assert caps.serves == ("list_pipelines", "get_pipeline", "leaderboard", "get_results", "planned")
    assert caps.executes is False
    assert caps.writes is WriteAccess.NONE


def test_list_and_get_pipeline_filter(tmp_path: object) -> None:
    with fake_modules(_fakes()):
        provider = BenchmarkProvider(store_root=str(tmp_path))
        assert len(provider.list_pipelines()) == 2
        assert provider.get_pipeline("h2") == {"pipeline_dag_hash": "h2", "human_label": "B"}
        assert provider.get_pipeline("missing") is None


def test_leaderboard_results_and_planned(tmp_path: object) -> None:
    with fake_modules(_fakes()):
        provider = BenchmarkProvider(store_root=str(tmp_path))
        assert provider.leaderboard(metric="rmse", scope="cv")["q"] == {"metric": "rmse", "scope": "cv"}
        assert provider.get_results("e1") == {"execution_hash": "e1"}
        assert provider.get_results("absent") is None
        assert provider.planned() == [{"plan_id": 1, "status": "planned"}]


def test_unavailable_backing_degrades() -> None:
    with hidden_modules("nirs4all_benchmarks"):
        provider = BenchmarkProvider()
        assert provider.version() == "unavailable"
        assert provider.health().available is False
        with pytest.raises(ProviderUnavailable):
            provider.list_pipelines()

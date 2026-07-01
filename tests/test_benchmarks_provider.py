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

    def overview(self) -> dict[str, object]:
        return {"pipelines": 2, "datasets": 1, "schema_version": 1, "metrics": ["rmse"]}

    def datasets(self) -> list[dict[str, object]]:
        return [{"dataset_fingerprint": "df1", "name": "corn", "n_samples": 80}]

    def operators(self) -> list[dict[str, object]]:
        return [{"operator_spec_hash": "op1", "entrypoint": "SNV", "n_pipelines": 2}]

    def pipelines(self) -> list[dict[str, object]]:
        return [{"pipeline_dag_hash": "h1", "human_label": "A"}, {"pipeline_dag_hash": "h2", "human_label": "B"}]

    def leaderboard(self, **query: object) -> dict[str, object]:
        return {"rows": [], "q": query}

    def run_detail(self, execution_hash: str) -> dict[str, object] | None:
        return {"execution_hash": execution_hash} if execution_hash == "e1" else None

    def residuals(self, execution_hash: str, *, partition: str | None = None) -> list[dict[str, object]]:
        if execution_hash != "e1":
            return []
        rows = [
            {"sample_id": "s1", "partition": "validation", "residual": 0.1},
            {"sample_id": "s2", "partition": "test", "residual": 0.2},
        ]
        return [r for r in rows if partition is None or r["partition"] == partition]

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
    assert caps.serves == (
        "overview",
        "datasets",
        "operators",
        "list_pipelines",
        "get_pipeline",
        "leaderboard",
        "get_results",
        "residuals",
        "planned",
    )
    assert caps.executes is False
    assert caps.writes is WriteAccess.NONE


def test_overview_datasets_operators(tmp_path: object) -> None:
    with fake_modules(_fakes()):
        provider = BenchmarkProvider(store_root=str(tmp_path))
        assert provider.overview()["schema_version"] == 1
        assert provider.datasets() == [{"dataset_fingerprint": "df1", "name": "corn", "n_samples": 80}]
        assert provider.operators()[0]["entrypoint"] == "SNV"


def test_residuals_filters_by_partition_and_handles_absent(tmp_path: object) -> None:
    with fake_modules(_fakes()):
        provider = BenchmarkProvider(store_root=str(tmp_path))
        assert len(provider.residuals("e1")) == 2
        assert [r["partition"] for r in provider.residuals("e1", partition="test")] == ["test"]
        assert provider.residuals("absent") == []


def test_list_and_get_pipeline_filter(tmp_path: object) -> None:
    with fake_modules(_fakes()):
        provider = BenchmarkProvider(store_root=str(tmp_path))
        assert len(provider.list_pipelines()) == 2
        assert provider.get_pipeline("h2") == {"pipeline_dag_hash": "h2", "human_label": "B"}
        assert provider.get_pipeline("missing") is None


def test_get_pipeline_uses_local_store_hash_lookup(tmp_path: object) -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    class _DirectStore:
        def __init__(self, root: str) -> None:
            self.root = root

        def query_one(self, sql: str, params: tuple[object, ...]) -> dict[str, object] | None:
            calls.append((sql, params))
            if params == ("h-direct",):
                return {"pipeline_dag_hash": "h-direct", "human_label": "Direct", "n_run_conditions": 3}
            return None

    class _DirectQueries:
        def __init__(self, store: _DirectStore) -> None:
            self.store = store

        def pipelines(self) -> list[dict[str, object]]:
            raise AssertionError("get_pipeline should use the store hash lookup")

    fakes = {
        "nirs4all_benchmarks": {"__version__": "0.1.0"},
        "nirs4all_benchmarks.store": {},
        "nirs4all_benchmarks.store.arena_store": {"ArenaStore": _DirectStore},
        "nirs4all_benchmarks.store.queries": {"Queries": _DirectQueries},
    }
    with fake_modules(fakes):
        provider = BenchmarkProvider(store_root=str(tmp_path))
        assert provider.get_pipeline("h-direct") == {
            "pipeline_dag_hash": "h-direct",
            "human_label": "Direct",
            "n_run_conditions": 3,
        }
        assert provider.get_pipeline("missing") is None
    assert len(calls) == 2
    assert "FROM pipeline_dags pd" in calls[0][0]
    assert calls[0][1] == ("h-direct",)


def test_pipeline_lookup_rejects_blank_dag_hash(tmp_path: object) -> None:
    with fake_modules(_fakes()):
        provider = BenchmarkProvider(store_root=str(tmp_path))
        with pytest.raises(ValueError, match="benchmarks\\.pipeline_dag_hash must be a non-empty string"):
            provider.get_pipeline(" ")


def test_leaderboard_results_and_planned(tmp_path: object) -> None:
    with fake_modules(_fakes()):
        provider = BenchmarkProvider(store_root=str(tmp_path))
        assert provider.leaderboard(metric="rmse", scope="cv")["q"] == {"metric": "rmse", "scope": "cv"}
        assert provider.get_results("e1") == {"execution_hash": "e1"}
        assert provider.get_results("absent") is None
        assert provider.planned() == [{"plan_id": 1, "status": "planned"}]


def test_result_lookup_rejects_blank_execution_hash(tmp_path: object) -> None:
    with fake_modules(_fakes()):
        provider = BenchmarkProvider(store_root=str(tmp_path))
        with pytest.raises(ValueError, match="benchmarks\\.execution_hash must be a non-empty string"):
            provider.get_results("")


def test_unavailable_backing_degrades() -> None:
    with hidden_modules("nirs4all_benchmarks"):
        provider = BenchmarkProvider()
        assert provider.version() == "unavailable"
        assert provider.health().available is False
        with pytest.raises(ProviderUnavailable):
            provider.list_pipelines()

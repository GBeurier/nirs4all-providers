"""BenchmarkProvider — read client over :mod:`nirs4all_benchmarks` ("the Arena", PROV-003).

Wraps the read-only ``Queries`` facade over a local ``ArenaStore``: ``overview`` / ``datasets`` /
``operators`` / ``pipelines`` / ``leaderboard`` / ``run_detail`` / ``residuals`` / ``planned`` plus an
adapter-side ``get_pipeline(dag_hash)`` filter. The Arena never runs compute and this client never
ingests or queues: there is **no runner and no write path here** (``queue_evaluation`` is deferred,
gated on LOCK-RT / CLU-006). All reads stay on the local store; no network call is made by this
adapter.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, cast

from ._adapter import _BaseProvider
from .base import Capabilities, WriteAccess

__all__ = ["BenchmarkProvider"]

_DEFAULT_STORE = "arena-store"
_STORE_ENV = "NIRS4ALL_BENCHMARKS_STORE"
_PIPELINE_BY_HASH_SQL = """
    SELECT pd.pipeline_dag_hash, pd.human_label, pd.main_model, pd.n_nodes, pd.is_linear,
           pd.nirs4all_identity_hash, pd.engine_graph_fingerprint,
           (SELECT COUNT(DISTINCT rc.run_condition_hash) FROM run_conditions rc
              WHERE rc.pipeline_dag_hash = pd.pipeline_dag_hash) AS n_run_conditions
    FROM pipeline_dags pd
    WHERE pd.pipeline_dag_hash = ?
"""


class BenchmarkProvider(_BaseProvider):
    """Thin read client over a local ``nirs4all-benchmarks`` Arena store."""

    provider_id: ClassVar[str] = "benchmarks"
    _module: ClassVar[str] = "nirs4all_benchmarks"
    _extra: ClassVar[str] = "benchmarks"

    def __init__(self, *, store_root: str | None = None) -> None:
        super().__init__()
        self._store_root = store_root

    def capabilities(self) -> Capabilities:
        return Capabilities(
            serves=(
                "overview",
                "datasets",
                "operators",
                "list_pipelines",
                "get_pipeline",
                "leaderboard",
                "get_results",
                "residuals",
                "planned",
            ),
            executes=False,
            writes=WriteAccess.NONE,
            portability="benchmark scores are weights-free and residual-keyed (DESIGN.md)",
        )

    def _resolve_store_root(self) -> str:
        if self._store_root is not None:
            return str(self._store_root)
        return os.environ.get(_STORE_ENV, _DEFAULT_STORE)

    def _reachable(self) -> tuple[bool | None, str | None]:
        # Probe the local store file without constructing (and thus creating) a store.
        root = Path(self._resolve_store_root())
        if (root / "arena.sqlite").exists():
            return True, None
        return False, f"no arena.sqlite under {root}"

    def _queries(self) -> Any:
        self._require()
        from nirs4all_benchmarks.store.arena_store import ArenaStore
        from nirs4all_benchmarks.store.queries import Queries

        return Queries(ArenaStore(self._resolve_store_root()))

    def overview(self) -> dict[str, Any]:
        """Return the store census: table counts, available metrics, schema version (``Queries.overview``)."""
        result: dict[str, Any] = self._queries().overview()
        return result

    def datasets(self) -> list[dict[str, Any]]:
        """List dataset fingerprints + identity-card facets in the store (delegates to ``Queries.datasets``)."""
        return list(self._queries().datasets())

    def operators(self) -> list[dict[str, Any]]:
        """List operator specs and their pipeline reach (delegates to ``Queries.operators``)."""
        return list(self._queries().operators())

    def list_pipelines(self) -> list[dict[str, Any]]:
        """List canonical pipeline DAGs in the store (delegates to ``Queries.pipelines``)."""
        return list(self._queries().pipelines())

    def get_pipeline(self, dag_hash: str) -> dict[str, Any] | None:
        """Return the pipeline with ``pipeline_dag_hash == dag_hash``, or ``None``.

        Uses the local Arena store read API when available so a by-hash lookup does not have to scan the
        entire pipeline catalogue. Older/faked ``Queries`` objects without ``store.query_one`` still fall
        back to the public ``pipelines()`` list shape.
        """
        dag_hash = self._require_identifier(dag_hash, name="pipeline_dag_hash")
        queries = self._queries()
        store = getattr(queries, "store", None)
        query_one = getattr(store, "query_one", None)
        if callable(query_one):
            result = query_one(_PIPELINE_BY_HASH_SQL, (dag_hash,))
            if result is None:
                return None
            if isinstance(result, dict):
                return result
            if isinstance(result, Mapping):
                return dict(result)
            return cast(dict[str, Any], result)
        match: dict[str, Any] | None = next(
            (p for p in queries.pipelines() if p.get("pipeline_dag_hash") == dag_hash),
            None,
        )
        return match

    def leaderboard(self, **query: Any) -> dict[str, Any]:
        """Return a configurable leaderboard (delegates to ``Queries.leaderboard``)."""
        result: dict[str, Any] = self._queries().leaderboard(**query)
        return result

    def get_results(self, execution_hash: str) -> dict[str, Any] | None:
        """Return a run's full detail, or ``None`` (delegates to ``Queries.run_detail``)."""
        execution_hash = self._require_identifier(execution_hash, name="execution_hash")
        result: dict[str, Any] | None = self._queries().run_detail(execution_hash)
        return result

    def residuals(self, execution_hash: str, *, partition: str | None = None) -> list[dict[str, Any]]:
        """Return a run's sample-keyed residual rows (weights-free), optionally filtered by ``partition``.

        Delegates to ``Queries.residuals``; an unknown ``execution_hash`` yields an empty list.
        """
        execution_hash = self._require_identifier(execution_hash, name="execution_hash")
        return list(self._queries().residuals(execution_hash, partition=partition))

    def planned(self) -> list[dict[str, Any]]:
        """List planned (not-yet-run) conditions awaiting a runner (delegates to ``Queries.planned``)."""
        return list(self._queries().planned())

"""BenchmarkProvider — read client over :mod:`nirs4all_benchmarks` ("the Arena", PROV-003).

Wraps the read-only ``Queries`` facade over a local ``ArenaStore``: ``pipelines`` / ``leaderboard`` /
``run_detail`` / ``planned`` plus an adapter-side ``get_pipeline(dag_hash)`` filter. The Arena never
runs compute and this client never ingests or queues: there is **no runner and no write path here**
(``queue_evaluation`` is deferred, gated on LOCK-RT / CLU-006). All reads stay on the local store; no
network call is made by this adapter.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar

from ._adapter import _BaseProvider
from .base import Capabilities, WriteAccess

__all__ = ["BenchmarkProvider"]

_DEFAULT_STORE = "arena-store"
_STORE_ENV = "NIRS4ALL_BENCHMARKS_STORE"


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
            serves=("list_pipelines", "get_pipeline", "leaderboard", "get_results", "planned"),
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

    def list_pipelines(self) -> list[dict[str, Any]]:
        """List canonical pipeline DAGs in the store (delegates to ``Queries.pipelines``)."""
        return list(self._queries().pipelines())

    def get_pipeline(self, dag_hash: str) -> dict[str, Any] | None:
        """Return the pipeline with ``pipeline_dag_hash == dag_hash``, or ``None`` (adapter-side filter)."""
        match: dict[str, Any] | None = next(
            (p for p in self._queries().pipelines() if p.get("pipeline_dag_hash") == dag_hash),
            None,
        )
        return match

    def leaderboard(self, **query: Any) -> dict[str, Any]:
        """Return a configurable leaderboard (delegates to ``Queries.leaderboard``)."""
        result: dict[str, Any] = self._queries().leaderboard(**query)
        return result

    def get_results(self, execution_hash: str) -> dict[str, Any] | None:
        """Return a run's full detail, or ``None`` (delegates to ``Queries.run_detail``)."""
        result: dict[str, Any] | None = self._queries().run_detail(execution_hash)
        return result

    def planned(self) -> list[dict[str, Any]]:
        """List planned (not-yet-run) conditions awaiting a runner (delegates to ``Queries.planned``)."""
        return list(self._queries().planned())

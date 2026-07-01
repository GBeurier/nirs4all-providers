"""BenchmarkProvider — local client over :mod:`nirs4all_benchmarks` ("the Arena", PROV-003).

Wraps the read-only ``Queries`` facade over a local ``ArenaStore``: ``overview`` / ``datasets`` /
``operators`` / ``pipelines`` / ``leaderboard`` / ``run_detail`` / ``residuals`` / ``planned`` plus an
adapter-side ``get_pipeline(dag_hash)`` lookup. The provider-level contract names the pipeline list
lookup ``get_pipeline_list`` and keeps ``list_pipelines`` as a compatibility alias. It also delegates
``queue_pipeline_test`` to the backing ``ingestion.upload`` state machine, which registers a bare
pipeline and writes only local ``planned_runs`` rows for target n4a dataset tokens. The Arena never
runs compute; a runner fulfils planned rows later by ingesting real execution exports. No network call
or ecosystem write-back is made by this adapter.
"""
from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
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
    """Thin local client over a ``nirs4all-benchmarks`` Arena store."""

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
                "get_pipeline_list",
                "list_pipelines",
                "get_pipeline",
                "leaderboard",
                "get_results",
                "residuals",
                "planned",
                "queue_pipeline_test",
            ),
            executes=False,
            writes=WriteAccess.LOCAL_STORE,
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

    def _target_dataset_tokens(self, target_datasets: object) -> list[str]:
        if isinstance(target_datasets, (str, bytes)) or not isinstance(target_datasets, Sequence):
            self._invalid_identifier("target_datasets", "must be a sequence of non-empty strings")
        tokens: list[str] = []
        sequence = cast(Sequence[object], target_datasets)
        for index, token in enumerate(sequence):
            if not isinstance(token, str):
                self._invalid_identifier(
                    f"target_datasets[{index}]",
                    f"must be a string, got {type(token).__name__}",
                )
            if not token.strip():
                self._invalid_identifier(f"target_datasets[{index}]", "must be a non-empty string")
            tokens.append(token)
        if not tokens:
            self._invalid_identifier("target_datasets", "must contain at least one dataset token")
        return tokens

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

    def get_pipeline_list(self) -> list[dict[str, Any]]:
        """List canonical pipeline DAGs in the store (delegates to ``Queries.pipelines``)."""
        return list(self._queries().pipelines())

    def list_pipelines(self) -> list[dict[str, Any]]:
        """Compatibility alias for :meth:`get_pipeline_list`."""
        return self.get_pipeline_list()

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

    def queue_pipeline_test(
        self,
        payload: Any,
        *,
        target_datasets: Sequence[str],
        collection_id: str = "uploads",
        as_release: bool = False,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Register/inspect a local pipeline test plan (delegates to ``ingestion.upload``).

        ``payload`` is forwarded verbatim to the Arena's upload state machine: a ``.n4a`` path, JSON/YAML
        recipe text, a bare pipeline recipe, or an ``ArenaRunExport``. For bare pipelines, the backing
        service registers the recipe and creates local ``planned_runs`` rows for ``target_datasets`` when
        no valid execution already exists. This method never executes the pipeline and never writes back
        to repository, datasets, or papers.
        """
        targets = self._target_dataset_tokens(target_datasets)
        collection = self._require_identifier(collection_id, name="collection_id")
        self._require()
        from nirs4all_benchmarks.ingestion import upload
        from nirs4all_benchmarks.store.arena_store import ArenaStore

        store = ArenaStore(self._resolve_store_root())
        try:
            result = upload(
                store,
                payload,
                collection_id=collection,
                target_datasets=targets,
                as_release=as_release,
                filename=filename,
            )
        finally:
            close = getattr(store, "close", None)
            if callable(close):
                close()

        to_json = getattr(result, "to_json", None)
        if callable(to_json):
            json_result = to_json()
            if isinstance(json_result, Mapping):
                return cast(dict[str, Any], dict(json_result))
            return cast(dict[str, Any], json_result)
        if isinstance(result, Mapping):
            return cast(dict[str, Any], dict(result))
        return cast(dict[str, Any], result)

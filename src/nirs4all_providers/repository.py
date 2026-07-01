"""PipelineProvider — read client over :mod:`nirs4all_repository` (PROV-002).

Wraps the real API verbatim: ``list`` / ``card`` / ``get`` / ``fetch`` plus ``Pipeline.recipe`` and
``Pipeline.verify``. A resolved pipeline is *served config*, not a runnable object — the consumer runs
it elsewhere via ``nirs4all.run(pipeline.to_nirs4all(), ...)``; ``recipe`` returns that same config in
its canonical-JSON form for inspection without bridging to a framework. This client has **no**
ecosystem write path: authoring and publishing stay in the repository repo's own CLI.
"""
from __future__ import annotations

from typing import Any, ClassVar

from ._adapter import _BaseProvider
from .base import Capabilities, WriteAccess

__all__ = ["PipelineProvider"]


class PipelineProvider(_BaseProvider):
    """Thin read client over the ``nirs4all-repository`` pipeline catalogue."""

    provider_id: ClassVar[str] = "repository"
    _module: ClassVar[str] = "nirs4all_repository"
    _extra: ClassVar[str] = "repository"

    def __init__(self, *, root: str | None = None, cache_dir: str | None = None, verify: bool = True) -> None:
        super().__init__()
        self._root = root
        self._cache_dir = cache_dir
        self._verify = verify

    def capabilities(self) -> Capabilities:
        return Capabilities(
            serves=("list_pipelines", "card", "get_pipeline", "recipe", "get_bundle", "verify"),
            executes=False,
            writes=WriteAccess.NONE,
            portability="served pipeline recipes reference CAP-002/CAP-004 portability levels",
        )

    def list_pipelines(self, **filters: Any) -> list[dict[str, Any]]:
        """List catalogue pipelines (delegates to ``nirs4all_repository.list``)."""
        return list(self._require().list(root=self._root, **filters))

    def card(self, pipeline_id: str) -> dict[str, Any]:
        """Return a pipeline's validated descriptor (delegates to ``nirs4all_repository.card``)."""
        pipeline_id = self._require_identifier(pipeline_id, name="pipeline_id")
        result: dict[str, Any] = self._require().card(pipeline_id, root=self._root)
        return result

    def get_pipeline(self, pipeline_id: str, **opts: Any) -> Any:
        """Resolve a pipeline and return a ``Pipeline`` handle (delegates to ``nirs4all_repository.get``)."""
        pipeline_id = self._require_identifier(pipeline_id, name="pipeline_id")
        params: dict[str, Any] = {"root": self._root, "cache_dir": self._cache_dir, "verify": self._verify}
        params.update(opts)
        return self._require().get(pipeline_id, **params)

    def recipe(self, pipeline_id: str) -> Any:
        """Return a pipeline's canonical-JSON recipe (delegates to ``Pipeline.recipe``).

        This is the served config as data — framework-agnostic and not bridged; the consumer chooses
        ``to_nirs4all`` / ``to_dagml`` on the handle from :meth:`get_pipeline` when it wants to run it.
        """
        return self.get_pipeline(pipeline_id).recipe()

    def get_bundle(self, pipeline_id: str, *, with_artifacts: bool = False) -> Any:
        """Materialise the bundle dir and return its path (delegates to ``nirs4all_repository.fetch``)."""
        pipeline_id = self._require_identifier(pipeline_id, name="pipeline_id")
        return self._require().fetch(
            pipeline_id,
            root=self._root,
            cache_dir=self._cache_dir,
            verify=self._verify,
            with_artifacts=with_artifacts,
        )

    def verify(self, pipeline_id: str) -> None:
        """Recompute and check every bundle SHA-256 (delegates to ``Pipeline.verify``)."""
        self.get_pipeline(pipeline_id, verify=False).verify()

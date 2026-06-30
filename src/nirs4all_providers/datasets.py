"""DatasetProvider — read client over :mod:`nirs4all_datasets` (PROV-001).

Wraps the real API verbatim: ``list`` / ``card`` / ``get`` plus the ``NirsDataset.to_nirs4all`` bridge.
No assembly logic lives here — ``nirs4all-io`` remains the dataset-assembly owner and
``to_dataset_package`` is deferred (gated on LOCK-IO). The only write this provider ever performs is
into the local pooch cache, via the backing ``get()``.
"""
from __future__ import annotations

from typing import Any, ClassVar

from ._adapter import _BaseProvider
from .base import Capabilities, WriteAccess

__all__ = ["DatasetProvider"]


class DatasetProvider(_BaseProvider):
    """Thin read client over the ``nirs4all-datasets`` catalogue."""

    provider_id: ClassVar[str] = "datasets"
    _module: ClassVar[str] = "nirs4all_datasets"
    _extra: ClassVar[str] = "datasets"

    def __init__(self, *, root: str = ".", cache_dir: str | None = None) -> None:
        super().__init__()
        self._root = root
        self._cache_dir = cache_dir

    def capabilities(self) -> Capabilities:
        return Capabilities(
            serves=("list_datasets", "card", "get_dataset", "to_spectro_dataset"),
            executes=False,
            writes=WriteAccess.LOCAL_CACHE,
            portability="served datasets reference CAP-002/CAP-004 portability levels",
        )

    def _reachable(self) -> tuple[bool | None, str | None]:
        # Local catalogue enumeration is a cheap, network-free backing probe.
        try:
            self._require().list(self._root)
        except Exception as exc:  # backing present but its catalogue is unreadable
            return False, f"{type(exc).__name__}: {exc}"
        return True, None

    def list_datasets(self, **filters: Any) -> list[dict[str, Any]]:
        """List catalogue datasets (delegates to ``nirs4all_datasets.list``)."""
        return list(self._require().list(self._root, **filters))

    def card(self, dataset_id: str) -> dict[str, Any] | None:
        """Return a dataset's identity card, or ``None`` (delegates to ``nirs4all_datasets.card``)."""
        result: dict[str, Any] | None = self._require().card(dataset_id, self._root)
        return result

    def get_dataset(self, dataset_id: str, **opts: Any) -> Any:
        """Resolve a dataset and return a ``NirsDataset`` (delegates to ``nirs4all_datasets.get``)."""
        params: dict[str, Any] = {"root": self._root, "cache_dir": self._cache_dir}
        params.update(opts)
        return self._require().get(dataset_id, **params)

    def to_spectro_dataset(self, dataset_id: str, **opts: Any) -> Any:
        """Return a nirs4all ``SpectroDataset`` via ``NirsDataset.to_nirs4all`` (needs the nirs4all extra)."""
        return self.get_dataset(dataset_id, **opts).to_nirs4all()

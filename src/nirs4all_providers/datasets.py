"""DatasetProvider — read client over :mod:`nirs4all_datasets` (PROV-001).

Wraps the real API verbatim: ``list`` / ``card`` / ``get`` plus the ``NirsDataset.to_nirs4all`` bridge.
No assembly logic lives here — ``nirs4all-io`` remains the dataset-assembly owner. The only write this
provider ever performs is into the local pooch cache, via the backing ``get()``.

``to_dataset_package`` is a *soft, optional* bridge to nirs4all-io's DatasetPackage builder, gated on
LOCK-IO: it is a transparent pass-through that never re-implements assembly and stays inert until the
W17 public entrypoint lands. It is deliberately **not** part of :meth:`capabilities.serves` (which lists
only the stable catalogue reads).
"""
from __future__ import annotations

from typing import Any, ClassVar

from ._adapter import _BaseProvider
from ._softimport import ProviderUnavailable, soft_import
from .base import Capabilities, WriteAccess

__all__ = ["DatasetProvider"]

_IO_MODULE = "nirs4all_io"
_IO_ENTRYPOINT = "to_dataset_package"


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

    def to_dataset_package(self, *args: Any, **kwargs: Any) -> Any:
        """Soft, optional bridge to nirs4all-io's ``DatasetPackage`` builder (deferred; LOCK-IO / W17).

        This is a **transparent pass-through**: it forwards its arguments verbatim to
        ``nirs4all_io.to_dataset_package`` and adds no assembly logic of its own — ``nirs4all-io`` stays
        the single dataset-assembly owner, so nothing here re-runs RESOLVE/INFER/MATERIALIZE. The exact
        argument contract is W17's to define; this adapter only *consumes* whatever public entrypoint
        ``nirs4all-io`` publishes, and imposes no signature on it.

        It degrades cleanly and never affects the rest of the provider:

        * ``nirs4all-io`` not installed → :class:`ProviderUnavailable` (install ``[io]``);
        * installed but the W17 entrypoint has not landed yet → :class:`RuntimeError` naming the deferral.
        """
        io = soft_import(_IO_MODULE)
        if io.module is None:
            raise ProviderUnavailable(self.provider_id, extra="io", module=_IO_MODULE, cause=io.error)
        entrypoint = getattr(io.module, _IO_ENTRYPOINT, None)
        if entrypoint is None:
            io_version = getattr(io.module, "__version__", "unknown")
            raise RuntimeError(
                f"datasets.{_IO_ENTRYPOINT} is deferred: the installed nirs4all-io (v{io_version}) does "
                f"not expose the public `{_IO_ENTRYPOINT}` entrypoint yet "
                "(LOCK-IO / pending nirs4all-io DatasetPackage v2, W17)."
            )
        return entrypoint(*args, **kwargs)

"""DatasetProvider — read client over :mod:`nirs4all_datasets` (PROV-001).

Wraps the real API verbatim: ``list`` / ``card`` / ``get`` plus the ``NirsDataset.to_nirs4all`` bridge.
No assembly logic lives here — ``nirs4all-io`` remains the dataset-assembly owner. The only write this
provider ever performs is into the local pooch cache, via the backing ``get()`` / ``retrieve()``.

``to_dataset_package`` and ``describe_dataset_package`` are soft, optional bridges to nirs4all-io's
DatasetPackage API. They are transparent pass-throughs that never re-implement assembly; if nirs4all-io
is absent or too old, callers get a typed capability refusal instead of a fake package.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Any, ClassVar, cast

from ._adapter import _BaseProvider
from ._softimport import ProviderCapabilityUnavailable, ProviderUnavailable, soft_import
from .base import Capabilities, WriteAccess

__all__ = ["DatasetPackageCapability", "DatasetProvider"]

_IO_MODULE = "nirs4all_io"
_IO_PACKAGE_ENTRYPOINT = "to_dataset_package"
_IO_DESCRIBE_ENTRYPOINT = "describe_dataset_package"


@dataclass(frozen=True)
class DatasetPackageCapability:
    """Typed status for the optional nirs4all-io DatasetPackage bridge."""

    available: bool
    can_return: bool
    can_describe: bool
    io_version: str | None = None
    refusal: ProviderCapabilityUnavailable | ProviderUnavailable | None = None


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
            serves=(
                "list_datasets",
                "card",
                "get_dataset",
                "retrieve_dataset",
                "to_spectro_dataset",
                "to_dataset_package",
                "describe_dataset_package",
            ),
            executes=False,
            writes=WriteAccess.LOCAL_CACHE,
            portability=(
                "portable dataset consumers use catalog/index.json + n4ds bindings; "
                "no Python provider dependency"
            ),
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
        dataset_id = self._require_identifier(dataset_id, name="dataset_id")
        result: dict[str, Any] | None = self._require().card(dataset_id, self._root)
        return result

    def get_dataset(self, dataset_id: str, **opts: Any) -> Any:
        """Resolve a dataset and return a ``NirsDataset`` (delegates to ``nirs4all_datasets.get``)."""
        dataset_id = self._require_identifier(dataset_id, name="dataset_id")
        params: dict[str, Any] = {"root": self._root, "cache_dir": self._cache_dir}
        params.update(opts)
        return self._require().get(dataset_id, **params)

    def retrieve_dataset(self, dataset_id: str, **opts: Any) -> dict[str, Any]:
        """Retrieve dataset bytes into the local cache and return the backing status dict.

        This delegates to ``nirs4all_datasets.retrieve`` with no publish/upload path and no assembly
        logic; it is the explicit cache-fill sibling to :meth:`get_dataset`.
        """
        dataset_id = self._require_identifier(dataset_id, name="dataset_id")
        params: dict[str, Any] = {"root": self._root, "cache_dir": self._cache_dir}
        params.update(opts)
        result: dict[str, Any] = self._require().retrieve(dataset_id, **params)
        return result

    def to_spectro_dataset(self, dataset_id: str, **opts: Any) -> Any:
        """Return a nirs4all ``SpectroDataset`` via the backing ``nirs4all-datasets[nirs4all]`` bridge."""
        return self.get_dataset(dataset_id, **opts).to_nirs4all()

    def dataset_package_capability(self) -> DatasetPackageCapability:
        """Return typed availability for the optional nirs4all-io package bridge."""
        io = soft_import(_IO_MODULE)
        if io.module is None:
            unavailable = ProviderUnavailable(self.provider_id, extra="io", module=_IO_MODULE, cause=io.error)
            return DatasetPackageCapability(available=False, can_return=False, can_describe=False, refusal=unavailable)
        io_version = str(getattr(io.module, "__version__", "unknown"))
        missing = [
            name
            for name in (_IO_PACKAGE_ENTRYPOINT, _IO_DESCRIBE_ENTRYPOINT)
            if not callable(getattr(io.module, name, None))
        ]
        if missing:
            capability_refusal = ProviderCapabilityUnavailable(
                self.provider_id,
                capability="dataset_package",
                reason=f"installed nirs4all-io (v{io_version}) does not expose {', '.join(missing)}",
                extra="io",
                module=_IO_MODULE,
            )
            return DatasetPackageCapability(
                available=False,
                can_return=False,
                can_describe=False,
                io_version=io_version,
                refusal=capability_refusal,
            )
        return DatasetPackageCapability(available=True, can_return=True, can_describe=True, io_version=io_version)

    def _io_entrypoint(self, name: str) -> Callable[..., Any]:
        io = soft_import(_IO_MODULE)
        if io.module is None:
            raise ProviderUnavailable(self.provider_id, extra="io", module=_IO_MODULE, cause=io.error)
        module: ModuleType = io.module
        entrypoint = getattr(module, name, None)
        if not callable(entrypoint):
            io_version = getattr(module, "__version__", "unknown")
            raise ProviderCapabilityUnavailable(
                self.provider_id,
                capability=name,
                reason=f"installed nirs4all-io (v{io_version}) does not expose `{name}`",
                extra="io",
                module=_IO_MODULE,
            )
        return cast(Callable[..., Any], entrypoint)

    def to_dataset_package(self, *args: Any, **kwargs: Any) -> Any:
        """Soft, optional bridge to nirs4all-io's ``DatasetPackage`` builder.

        This is a **transparent pass-through**: it forwards its arguments verbatim to
        ``nirs4all_io.to_dataset_package`` and adds no assembly logic of its own — ``nirs4all-io`` stays
        the single dataset-assembly owner, so this adapter never re-runs RESOLVE/INFER/MATERIALIZE.

        It degrades cleanly and never affects the rest of the provider:

        * ``nirs4all-io`` not installed → :class:`ProviderUnavailable` (install ``[io]``);
        * installed but too old for the package API → :class:`ProviderCapabilityUnavailable`.
        """
        return self._io_entrypoint(_IO_PACKAGE_ENTRYPOINT)(*args, **kwargs)

    def describe_dataset_package(self, *args: Any, **kwargs: Any) -> Any:
        """Soft, optional bridge to nirs4all-io's bytes-free package description."""
        return self._io_entrypoint(_IO_DESCRIBE_ENTRYPOINT)(*args, **kwargs)

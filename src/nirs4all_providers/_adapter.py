"""Shared scaffolding for provider adapters: soft-import wiring, ``version()`` and ``health()``.

Concrete adapters (datasets / repository / benchmarks / papers) subclass :class:`_BaseProvider`, set the
three class variables, add their read methods, and override ``capabilities()`` (and optionally
``_reachable()``). The base keeps the soft-import/availability logic in one place so each adapter stays
a few lines of pure delegation — no provider business logic ever lives here.
"""
from __future__ import annotations

from types import ModuleType
from typing import ClassVar

from ._softimport import ProviderUnavailable, soft_import
from .base import Capabilities, Health


class _BaseProvider:
    """Common base: holds the soft-imported backing module and the uniform liveness contract."""

    provider_id: ClassVar[str]
    _module: ClassVar[str]
    _extra: ClassVar[str]

    def __init__(self) -> None:
        self._imp = soft_import(self._module)

    def _require(self) -> ModuleType:
        """Return the backing module, or raise :class:`ProviderUnavailable` if the extra is absent."""
        if self._imp.module is None:
            raise ProviderUnavailable(self.provider_id, extra=self._extra, module=self._module, cause=self._imp.error)
        return self._imp.module

    def version(self) -> str:
        """Return the backing package ``__version__``, or ``"unavailable"`` when absent."""
        if self._imp.module is None:
            return "unavailable"
        return str(getattr(self._imp.module, "__version__", "unknown"))

    def _reachable(self) -> tuple[bool | None, str | None]:
        """Optional network-free backing probe; ``(None, None)`` means no deeper probe is performed."""
        return None, None

    def health(self) -> Health:
        """Return the adapter/backing liveness; never raises (absence is reported, not raised)."""
        if self._imp.module is None:
            return Health(self.provider_id, available=False, reachable=None, version=None, detail=self._imp.error)
        reachable, detail = self._reachable()
        return Health(self.provider_id, available=True, reachable=reachable, version=self.version(), detail=detail)

    def capabilities(self) -> Capabilities:
        """Return the provider-level capability descriptor (overridden by every adapter)."""
        raise NotImplementedError

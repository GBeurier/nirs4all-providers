"""Soft-import helper: import an optional backing package without ever raising on absence.

Every provider adapter wraps exactly one ecosystem distribution that is an *optional extra* of
``nirs4all-providers``. When the extra is not installed, the adapter must degrade to
``health().available == False`` rather than explode at import time — the same graceful-degradation
pattern the sibling repos already use (e.g. ``nirs4all-benchmarks`` soft-imports ``nirs4all-datasets``).
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from types import ModuleType

__all__ = ["ProviderUnavailable", "SoftImport", "soft_import"]


@dataclass(frozen=True)
class SoftImport:
    """The outcome of an optional import: the module when present, else why it is absent."""

    name: str
    module: ModuleType | None = None
    error: str | None = None

    @property
    def available(self) -> bool:
        """Whether the module imported cleanly."""
        return self.module is not None


def soft_import(module_name: str) -> SoftImport:
    """Import ``module_name`` and return a :class:`SoftImport`, never raising on absence.

    Only :class:`ImportError` (which includes :class:`ModuleNotFoundError`) is swallowed — that is the
    "extra not installed" case. An optional package that is installed but raises a *different* error at
    import time is a genuine fault and is allowed to propagate.
    """
    try:
        module = import_module(module_name)
    except ImportError as exc:
        return SoftImport(name=module_name, module=None, error=f"{type(exc).__name__}: {exc}")
    return SoftImport(name=module_name, module=module, error=None)


class ProviderUnavailable(RuntimeError):
    """Raised when a provider's read surface is used but its backing extra is not installed.

    The message is uniform across providers and names the exact extra to install.
    """

    def __init__(self, provider_id: str, *, extra: str, module: str, cause: str | None = None) -> None:
        self.provider_id = provider_id
        self.extra = extra
        self.module = module
        self.cause = cause
        message = (
            f"provider {provider_id!r} is unavailable: its backing package {module!r} is not importable. "
            f"Install it with `pip install nirs4all-providers[{extra}]`."
        )
        if cause:
            message = f"{message} (import error: {cause})"
        super().__init__(message)

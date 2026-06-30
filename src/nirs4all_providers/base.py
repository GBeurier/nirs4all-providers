"""Provider contracts: the structural :class:`ProviderPlugin` protocol and its typed value objects.

These types are the *only* stable surface a consumer (nirs4all core, the Studio backend, lite, or the
CLI) needs in order to talk to any provider adapter. They are deliberately dependency-light — pure
stdlib — so importing this module never drags an optional provider package in.

A provider adapter is a thin client over one ecosystem repo (datasets / repository / benchmarks /
papers). It never re-implements that repo's logic, never executes ML, and never writes back to the
ecosystem; it serves *reads* (and, for papers, a local marker-guarded build). Execution and
write-back are delegated elsewhere by design (see ``SW6_PROV_PLUGINS_spec`` / ``IMP_L14``).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Protocol, runtime_checkable

__all__ = ["Capabilities", "Health", "ProviderPlugin", "WriteAccess"]


class WriteAccess(str, Enum):
    """Provider-level write policy (PROV-005).

    The read-adapter slice never exposes an ecosystem or network write path. The strongest write a
    slice-1 provider performs is into a *local* cache or a caller-chosen output directory.
    """

    NONE = "none"  # no write path at all (the repository read client)
    LOCAL_CACHE = "local-cache"  # writes only into a local on-disk cache (datasets ``get()``)
    LOCAL_OUTPUT = "local-output"  # writes only into a caller-chosen output dir (papers build)
    GATED = "gated"  # admin/governance-gated remote write — never reached in this slice


@dataclass(frozen=True)
class Health:
    """Liveness of a provider adapter and its backing package (decision D5).

    Attributes:
        provider_id: the adapter's stable id.
        available: whether the backing distribution imports cleanly (i.e. the extra is installed).
        reachable: an optional, network-free deeper probe (catalog enumerable, store file present);
            ``None`` when the adapter performs no deeper probe.
        version: the backing package ``__version__`` when available, else ``None``.
        detail: a short human-readable note (e.g. the import error when unavailable).
    """

    provider_id: str
    available: bool
    reachable: bool | None = None
    version: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class Capabilities:
    """Provider-level capability descriptor (decision D6).

    This is **distinct from** the LOCK-CAP ``ControllerCapability`` enum (which is operator-level): it
    describes what the *provider* serves, whether it *executes*, and its write policy. The
    ``portability`` field only *references* CAP-002/CAP-004 for the artifacts a provider serves; it
    never forks that vocabulary.
    """

    serves: tuple[str, ...]
    executes: bool = False
    writes: WriteAccess = WriteAccess.NONE
    portability: str | None = None


@runtime_checkable
class ProviderPlugin(Protocol):
    """The structural contract every provider adapter satisfies.

    Adapters are duck-typed against this protocol; they need not subclass it. ``provider_id`` is a
    stable string ("datasets" | "repository" | "benchmarks" | "papers"). The three methods are total
    and never raise for an *unavailable* backing — ``health()`` reports the absence instead.
    """

    provider_id: ClassVar[str]

    def version(self) -> str:
        """Return the backing package version, or ``"unavailable"`` when the extra is absent."""
        ...

    def health(self) -> Health:
        """Return adapter/backing liveness (never raises)."""
        ...

    def capabilities(self) -> Capabilities:
        """Return the provider-level capability descriptor (never raises)."""
        ...

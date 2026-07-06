"""Soft-import provider discovery and access.

The registry maps each stable ``provider_id`` to its adapter and the optional extra that backs it. It
never imports a backing package eagerly: availability is probed by a soft-import, so importing this
module — and calling :func:`available_providers` — works with *no* extras installed.

Providers are **not** controllers (``DEC-CTRL-001``): this registry is a separate surface from any
controller registry. A core that exposes both must keep them distinct.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ._softimport import ProviderUnavailable, soft_import
from .base import Capabilities, Health, ProviderPlugin
from .datasets import DatasetProvider
from .repository import PipelineProvider

__all__ = ["available_providers", "get_provider", "provider_capabilities", "provider_health", "provider_ids"]


@dataclass(frozen=True)
class _Spec:
    """A registry row: the stable id, the backing import name, the pip extra, and the adapter factory."""

    provider_id: str
    module: str
    extra: str
    factory: Callable[..., ProviderPlugin]


_REGISTRY: dict[str, _Spec] = {
    spec.provider_id: spec
    for spec in (
        _Spec("datasets", "nirs4all_datasets", "datasets", DatasetProvider),
        _Spec("repository", "nirs4all_repository", "repository", PipelineProvider),
    )
}


def _spec(provider_id: str) -> _Spec:
    try:
        return _REGISTRY[provider_id]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"unknown provider {provider_id!r}; known providers: {known}") from None


def provider_ids() -> tuple[str, ...]:
    """Return every registered provider id, regardless of whether its extra is installed."""
    return tuple(_REGISTRY)


def available_providers() -> list[str]:
    """Return the ids whose backing distribution imports cleanly (installed extras only)."""
    return [pid for pid, spec in _REGISTRY.items() if soft_import(spec.module).available]


def get_provider(provider_id: str, **config: Any) -> ProviderPlugin:
    """Instantiate the adapter for ``provider_id``.

    Args:
        provider_id: one of :func:`provider_ids`.
        config: adapter-specific keyword arguments (e.g. ``root`` / ``cache_dir`` / ``store_root``).

    Raises:
        ValueError: if ``provider_id`` is not a registered provider.
        ProviderUnavailable: if the provider is registered but its backing extra is not installed.
    """
    spec = _spec(provider_id)
    provider = spec.factory(**config)
    if not provider.health().available:
        raise ProviderUnavailable(
            provider_id, extra=spec.extra, module=spec.module, cause=soft_import(spec.module).error
        )
    return provider


def provider_health(provider_id: str, **config: Any) -> Health:
    """Return the :class:`Health` of ``provider_id`` without raising on an absent extra."""
    return _spec(provider_id).factory(**config).health()


def provider_capabilities(provider_id: str, **config: Any) -> Capabilities:
    """Return the provider-level capabilities without requiring the backing extra.

    Capability claims are adapter metadata. They must stay inspectable in a base install so release
    gates can detect over-claims even when optional sibling packages are absent.
    """
    return _spec(provider_id).factory(**config).capabilities()

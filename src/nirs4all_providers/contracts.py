"""Neutral provider contracts: schema access, descriptor emission, and a dependency-free validator.

The provider surface is a **language-neutral contract expressed as JSON**, not a Python API. The canonical
schemas live in ``nirs4all-ecosystem`` (``docs/contracts/providers/``) and are mirrored **byte-identically**
under ``nirs4all_providers/contracts/`` so this package can self-validate offline. The Python package is
*one conformant client* of that contract; an R / JS-WASM / Rust client emits and consumes the same shapes
(see the ecosystem ``docs/contracts/providers/README.md`` for the per-language story and gates).

This module:

* turns any :class:`~nirs4all_providers.base.ProviderPlugin` into a ``provider_descriptor.v1`` dict
  (:func:`provider_descriptor`, :func:`all_provider_descriptors`) — the neutral projection of
  ``provider_id`` / ``version()`` / ``health()`` / ``capabilities()``;
* loads the vendored schemas and example fixtures (:func:`load_contract_schema`,
  :func:`load_contract_fixture`);
* validates an instance against a schema with a tiny subset validator (:func:`iter_contract_errors`) —
  no third-party dependency, so the base install stays pure-stdlib and the test suite stays hermetic.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Any, cast

from .base import Capabilities, Health, ProviderPlugin
from .registry import provider_capabilities, provider_health, provider_ids

__all__ = [
    "CONTRACT_SCHEMA_IDS",
    "DESCRIPTOR_SCHEMA_VERSION",
    "all_provider_descriptors",
    "iter_contract_errors",
    "load_contract_fixture",
    "load_contract_schema",
    "provider_descriptor",
]

#: Envelope version of ``provider_descriptor.v1`` emitted by this client.
DESCRIPTOR_SCHEMA_VERSION = 1

#: Stable ids of the vendored neutral schemas (``<id>.schema.json`` under ``contracts/``).
CONTRACT_SCHEMA_IDS: tuple[str, ...] = (
    "provider_descriptor.v1",
    "dataset_card.v2",
    "dataset_manifest.v2",
    "repository_index.v1",
    "pipeline_descriptor.v1",
)


def _contracts_dir() -> Traversable:
    """Return the vendored ``contracts/`` directory as an importable resource anchor."""
    return resources.files("nirs4all_providers") / "contracts"


def load_contract_schema(schema_id: str) -> dict[str, Any]:
    """Load a vendored neutral schema by id (e.g. ``"dataset_card.v2"``)."""
    if schema_id not in CONTRACT_SCHEMA_IDS:
        known = ", ".join(CONTRACT_SCHEMA_IDS)
        raise ValueError(f"unknown contract schema {schema_id!r}; known: {known}")
    text = (_contracts_dir() / f"{schema_id}.schema.json").read_text(encoding="utf-8")
    return cast("dict[str, Any]", json.loads(text))


def load_contract_fixture(name: str) -> dict[str, Any]:
    """Load an example instance from ``contracts/fixtures/<name>.json`` (the porting reference corpus)."""
    text = (_contracts_dir() / "fixtures" / f"{name}.json").read_text(encoding="utf-8")
    return cast("dict[str, Any]", json.loads(text))


def _descriptor_dict(provider_id: str, version: str, health: Health, capabilities: Capabilities) -> dict[str, Any]:
    """Build a ``provider_descriptor.v1`` dict from a provider's neutral parts."""
    return {
        "schema_version": DESCRIPTOR_SCHEMA_VERSION,
        "provider_id": provider_id,
        "version": version,
        "health": {
            "available": health.available,
            "reachable": health.reachable,
            "version": health.version,
            "detail": health.detail,
        },
        "capabilities": {
            "serves": list(capabilities.serves),
            "executes": capabilities.executes,
            "writes": capabilities.writes.value,
            "portability": capabilities.portability,
        },
    }


def provider_descriptor(provider: ProviderPlugin) -> dict[str, Any]:
    """Return the neutral ``provider_descriptor.v1`` dict for a live provider adapter."""
    return _descriptor_dict(
        provider.provider_id,
        provider.version(),
        provider.health(),
        provider.capabilities(),
    )


def all_provider_descriptors() -> list[dict[str, Any]]:
    """Return a ``provider_descriptor.v1`` dict for every registered provider (no backing required).

    This mirrors :meth:`~nirs4all_providers.base._BaseProvider.version` semantics without instantiating a
    live adapter: the version is the backing version when available, else the literal ``"unavailable"``.
    """
    descriptors: list[dict[str, Any]] = []
    for provider_id in provider_ids():
        health = provider_health(provider_id)
        capabilities = provider_capabilities(provider_id)
        version = health.version if (health.available and health.version is not None) else "unavailable"
        descriptors.append(_descriptor_dict(provider_id, version, health, capabilities))
    return descriptors


# --- tiny subset JSON-Schema validator -------------------------------------------------------------
# Supports only the subset the provider contracts use: type (string or list), enum, required,
# properties, items, additionalProperties (bool), minimum, minItems. No $ref / anyOf / oneOf — the
# schemas are authored to stay within this subset so any host language can reimplement the validator.

_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "null": lambda v: v is None,
}


def _matches_type(value: Any, type_spec: Any) -> bool:
    if type_spec is None:
        return True
    types = [type_spec] if isinstance(type_spec, str) else list(type_spec)
    return any(check(value) for name, check in _TYPE_CHECKS.items() if name in types)


def _validate(value: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    type_spec = schema.get("type")
    if not _matches_type(value, type_spec):
        errors.append(f"{path}: expected type {type_spec!r}, got {type(value).__name__}")
        return  # downstream checks are unreliable once the type is wrong

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        errors.append(f"{path}: {value!r} is not one of {enum}")

    if isinstance(value, dict):
        _validate_object(value, schema, path, errors)
    elif isinstance(value, list):
        _validate_array(value, schema, path, errors)
    else:
        minimum = schema.get("minimum")
        if minimum is not None and isinstance(value, (int, float)) and not isinstance(value, bool) and value < minimum:
            errors.append(f"{path}: {value} is below minimum {minimum}")


def _validate_object(value: dict[str, Any], schema: dict[str, Any], path: str, errors: list[str]) -> None:
    properties: dict[str, Any] = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in value:
            errors.append(f"{path}: missing required property {key!r}")
    allows_additional = schema.get("additionalProperties", True)
    for key, item in value.items():
        if key in properties:
            _validate(item, properties[key], f"{path}.{key}", errors)
        elif allows_additional is False:
            errors.append(f"{path}: unexpected property {key!r}")


def _validate_array(value: list[Any], schema: dict[str, Any], path: str, errors: list[str]) -> None:
    min_items = schema.get("minItems")
    if min_items is not None and len(value) < min_items:
        errors.append(f"{path}: has {len(value)} items, fewer than minItems {min_items}")
    items = schema.get("items")
    if isinstance(items, dict):
        for index, element in enumerate(value):
            _validate(element, items, f"{path}[{index}]", errors)


def iter_contract_errors(instance: Any, schema: dict[str, Any]) -> list[str]:
    """Validate ``instance`` against ``schema`` and return a list of human-readable errors (empty = valid)."""
    errors: list[str] = []
    _validate(instance, schema, "$", errors)
    return errors

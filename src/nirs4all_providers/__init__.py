"""nirs4all-providers — dependency-light, soft-importing clients over the ecosystem's optional
dataset catalogue and pipeline repository.

The package owns *no* NIRS, ML, IO, or parsing logic. Each adapter is a thin, uniform client over one
sibling repo's real public API (``nirs4all-datasets`` / ``nirs4all-repository``), exposed behind the
:class:`ProviderPlugin` contract and discovered through the soft-import :func:`get_provider`. Providers
are **not** controllers and never execute ML or write back to the ecosystem.

Read slice only: no publish/upload and no benchmark or paper facade. Benchmarks and papers stay in
their owning repositories. The optional DatasetPackage bridge delegates to nirs4all-io and never
writes back.
"""
from __future__ import annotations

from ._softimport import ProviderCapabilityUnavailable, ProviderUnavailable, SoftImport, soft_import
from .base import Capabilities, Health, ProviderPlugin, WriteAccess
from .contracts import (
    CONTRACT_SCHEMA_IDS,
    all_provider_descriptors,
    iter_contract_errors,
    load_contract_fixture,
    load_contract_schema,
    provider_descriptor,
)
from .datasets import DatasetPackageCapability, DatasetProvider
from .registry import available_providers, get_provider, provider_capabilities, provider_health, provider_ids
from .repository import PipelineProvider

__version__ = "0.2.10"

__all__ = [
    "CONTRACT_SCHEMA_IDS",
    "Capabilities",
    "DatasetProvider",
    "Health",
    "PipelineProvider",
    "DatasetPackageCapability",
    "ProviderCapabilityUnavailable",
    "ProviderPlugin",
    "ProviderUnavailable",
    "SoftImport",
    "WriteAccess",
    "__version__",
    "all_provider_descriptors",
    "available_providers",
    "get_provider",
    "iter_contract_errors",
    "load_contract_fixture",
    "load_contract_schema",
    "provider_capabilities",
    "provider_descriptor",
    "provider_health",
    "provider_ids",
    "soft_import",
]

"""nirs4all-providers — a dependency-light, soft-importing client layer over the ecosystem's optional
data / pipeline / benchmark / paper repositories.

The package owns *no* NIRS, ML, IO, or parsing logic. Each adapter is a thin, uniform client over one
sibling repo's real public API (``nirs4all-datasets`` / ``nirs4all-repository`` /
``nirs4all-benchmarks`` / ``nirs4all-papers``), exposed behind the :class:`ProviderPlugin` contract and
discovered through the soft-import :func:`get_provider`. Providers are **not** controllers and never
execute ML or write back to the ecosystem (see ``SW6_PROV_PLUGINS_spec`` / ``IMP_L14``).

Read slice only: no ``to_dataset_package``, no publish/upload, no benchmark runner.
"""
from __future__ import annotations

from ._softimport import ProviderUnavailable, SoftImport, soft_import
from .base import Capabilities, Health, ProviderPlugin, WriteAccess
from .benchmarks import BenchmarkProvider
from .datasets import DatasetProvider
from .papers import PaperExportProvider
from .registry import available_providers, get_provider, provider_health, provider_ids
from .repository import PipelineProvider

__version__ = "0.2.0.dev0"

__all__ = [
    "BenchmarkProvider",
    "Capabilities",
    "DatasetProvider",
    "Health",
    "PaperExportProvider",
    "PipelineProvider",
    "ProviderPlugin",
    "ProviderUnavailable",
    "SoftImport",
    "WriteAccess",
    "__version__",
    "available_providers",
    "get_provider",
    "provider_health",
    "provider_ids",
    "soft_import",
]

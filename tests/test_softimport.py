"""Tests for the soft-import helper and the uniform unavailable error."""
from __future__ import annotations

import pytest

from nirs4all_providers import ProviderCapabilityUnavailable, ProviderUnavailable, SoftImport, soft_import


def test_soft_import_present_stdlib_module() -> None:
    result = soft_import("json")
    assert isinstance(result, SoftImport)
    assert result.available is True
    assert result.module is not None
    assert result.module.__name__ == "json"
    assert result.error is None


def test_soft_import_absent_module_does_not_raise() -> None:
    result = soft_import("nirs4all_providers_definitely_absent_xyz")
    assert result.available is False
    assert result.module is None
    assert "ModuleNotFoundError" in (result.error or "")


def test_provider_unavailable_message_names_the_extra() -> None:
    err = ProviderUnavailable("datasets", extra="datasets", module="nirs4all_datasets", cause="boom")
    assert err.provider_id == "datasets"
    assert err.extra == "datasets"
    assert err.module == "nirs4all_datasets"
    text = str(err)
    assert "nirs4all-providers[datasets]" in text
    assert "nirs4all_datasets" in text
    assert "boom" in text


def test_provider_capability_unavailable_message_names_capability_and_extra() -> None:
    err = ProviderCapabilityUnavailable(
        "datasets",
        capability="dataset_package",
        reason="missing entrypoint",
        extra="io",
        module="nirs4all_io",
    )
    assert err.provider_id == "datasets"
    assert err.capability == "dataset_package"
    assert err.reason == "missing entrypoint"
    assert err.extra == "io"
    assert err.module == "nirs4all_io"
    text = str(err)
    assert "dataset_package" in text
    assert "nirs4all-providers[io]" in text
    assert "nirs4all_io" in text


def test_provider_unavailable_is_runtime_error() -> None:
    with pytest.raises(RuntimeError):
        raise ProviderUnavailable("papers", extra="papers", module="nirs4all_papers")

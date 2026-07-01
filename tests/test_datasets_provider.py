"""Tests for DatasetProvider delegation and degradation (over a faked nirs4all_datasets)."""
from __future__ import annotations

import pytest

from conftest import fake_modules, hidden_modules
from nirs4all_providers import (
    DatasetPackageCapability,
    DatasetProvider,
    ProviderCapabilityUnavailable,
    ProviderUnavailable,
    WriteAccess,
)


class _FakeNirsDataset:
    def __init__(self, name: str, kw: dict[str, object]) -> None:
        self.name = name
        self.kw = kw

    def to_nirs4all(self) -> dict[str, object]:
        return {"spectro": self.name, "kw": self.kw}


def _fake() -> dict[str, dict[str, object]]:
    return {
        "nirs4all_datasets": {
            "__version__": "9.9.9",
            "list": lambda root, **filters: [{"root": root, "filters": filters}],
            "card": lambda name, root: {"name": name, "root": root},
            "get": lambda name, **kw: _FakeNirsDataset(name, kw),
            "retrieve": lambda name, **kw: {"name": name, "kw": kw, "kind": "canonical"},
        }
    }


def test_version_and_health_when_available() -> None:
    with fake_modules(_fake()):
        provider = DatasetProvider()
        assert provider.version() == "9.9.9"
        health = provider.health()
        assert health.available is True
        assert health.reachable is True  # the faked local catalogue enumerates
        assert health.version == "9.9.9"


def test_capabilities() -> None:
    with fake_modules(_fake()):
        caps = DatasetProvider().capabilities()
    assert caps.serves == (
        "list_datasets",
        "card",
        "get_dataset",
        "retrieve_dataset",
        "to_spectro_dataset",
        "to_dataset_package",
        "describe_dataset_package",
    )
    assert caps.executes is False
    assert caps.writes is WriteAccess.LOCAL_CACHE


def test_list_and_card_forward_root_and_filters() -> None:
    with fake_modules(_fake()):
        provider = DatasetProvider(root="/cat")
        assert provider.list_datasets(tier="public") == [{"root": "/cat", "filters": {"tier": "public"}}]
        assert provider.card("d1") == {"name": "d1", "root": "/cat"}


def test_get_dataset_forwards_root_cache_dir_and_opts() -> None:
    with fake_modules(_fake()):
        provider = DatasetProvider(root="/cat", cache_dir="/cache")
        dataset = provider.get_dataset("d1", split="train")
        assert dataset.name == "d1"
        assert dataset.kw == {"root": "/cat", "cache_dir": "/cache", "split": "train"}


def test_retrieve_dataset_forwards_root_cache_dir_and_opts_without_upload() -> None:
    with fake_modules(_fake()):
        provider = DatasetProvider(root="/cat", cache_dir="/cache")
        status = provider.retrieve_dataset("d1", route_id="primary", prepare=False)
    assert status == {
        "name": "d1",
        "kw": {"root": "/cat", "cache_dir": "/cache", "route_id": "primary", "prepare": False},
        "kind": "canonical",
    }


def test_dataset_lookup_rejects_blank_dataset_id() -> None:
    with fake_modules(_fake()):
        provider = DatasetProvider()
        with pytest.raises(ValueError, match="datasets\\.dataset_id must be a non-empty string"):
            provider.get_dataset(" ")


def test_to_spectro_dataset_bridges_via_to_nirs4all() -> None:
    with fake_modules(_fake()):
        out = DatasetProvider().to_spectro_dataset("d1")
    assert out == {"spectro": "d1", "kw": {"root": ".", "cache_dir": None}}


def test_unavailable_backing_degrades() -> None:
    with hidden_modules("nirs4all_datasets"):
        provider = DatasetProvider()
        assert provider.version() == "unavailable"
        health = provider.health()
        assert health.available is False
        assert health.reachable is None
        with pytest.raises(ProviderUnavailable):
            provider.list_datasets()
        with pytest.raises(ProviderUnavailable):
            provider.to_spectro_dataset("d1")


# ── soft to_dataset_package bridge ─────────────────────────────────────────────────────────────


def test_to_dataset_package_forwards_verbatim_to_io_entrypoint() -> None:
    """When nirs4all-io exposes the W17 entrypoint, the bridge forwards its args verbatim and adds
    no assembly of its own (nirs4all-io stays the assembly owner)."""
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def _pkg(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append((args, kwargs))
        return {"package": list(args), "opts": kwargs}

    fake_io = {
        "nirs4all_io": {
            "__version__": "9.9.9",
            "to_dataset_package": _pkg,
            "describe_dataset_package": lambda *a, **kw: {},
        }
    }
    with fake_modules(fake_io):
        out = DatasetProvider().to_dataset_package("d1", role="train")
    assert out == {"package": ["d1"], "opts": {"role": "train"}}
    assert calls == [(("d1",), {"role": "train"})]


def test_describe_dataset_package_forwards_verbatim_to_io_entrypoint() -> None:
    def _describe(*args: object, **kwargs: object) -> dict[str, object]:
        return {"summary": list(args), "opts": kwargs}

    fake_io = {
        "nirs4all_io": {
            "__version__": "9.9.9",
            "to_dataset_package": lambda *a, **kw: None,
            "describe_dataset_package": _describe,
        }
    }
    with fake_modules(fake_io):
        out = DatasetProvider().describe_dataset_package("d1", canonical=True)
    assert out == {"summary": ["d1"], "opts": {"canonical": True}}


def test_dataset_package_capability_reports_available_bridge() -> None:
    fake_io = {
        "nirs4all_io": {
            "__version__": "9.9.9",
            "to_dataset_package": lambda *a, **kw: None,
            "describe_dataset_package": lambda *a, **kw: {},
        }
    }
    with fake_modules(fake_io):
        status = DatasetProvider().dataset_package_capability()
    assert isinstance(status, DatasetPackageCapability)
    assert status.available is True
    assert status.can_return is True
    assert status.can_describe is True
    assert status.io_version == "9.9.9"
    assert status.refusal is None


def test_to_dataset_package_unavailable_when_io_absent() -> None:
    with hidden_modules("nirs4all_io"):
        status = DatasetProvider().dataset_package_capability()
        assert status.available is False
        assert isinstance(status.refusal, ProviderUnavailable)
        with pytest.raises(ProviderUnavailable) as excinfo:
            DatasetProvider().to_dataset_package("d1")
    assert "nirs4all-providers[io]" in str(excinfo.value)


def test_to_dataset_package_capability_unavailable_when_entrypoint_not_published() -> None:
    with fake_modules({"nirs4all_io": {"__version__": "0.1.3"}}):
        status = DatasetProvider().dataset_package_capability()
        assert status.available is False
        assert isinstance(status.refusal, ProviderCapabilityUnavailable)
        with pytest.raises(ProviderCapabilityUnavailable) as excinfo:
            DatasetProvider().to_dataset_package("d1")
    assert not isinstance(excinfo.value, ProviderUnavailable)
    message = str(excinfo.value)
    assert "does not expose" in message
    assert "to_dataset_package" in message

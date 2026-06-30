"""Tests for DatasetProvider delegation and degradation (over a faked nirs4all_datasets)."""
from __future__ import annotations

import pytest

from conftest import fake_modules, hidden_modules
from nirs4all_providers import DatasetProvider, ProviderUnavailable, WriteAccess


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
    assert caps.serves == ("list_datasets", "card", "get_dataset", "to_spectro_dataset")
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

"""Tests for PipelineProvider delegation and degradation (over a faked nirs4all_repository)."""
from __future__ import annotations

import pytest

from conftest import fake_modules, hidden_modules
from nirs4all_providers import PipelineProvider, ProviderUnavailable, WriteAccess


class _FakePipeline:
    def __init__(self, name: str, verify_arg: bool, record: list[tuple[object, ...]]) -> None:
        self.name = name
        self.verify_arg = verify_arg
        self._record = record

    def verify(self) -> None:
        self._record.append(("verify", self.name))

    def recipe(self) -> dict[str, object]:
        self._record.append(("recipe", self.name))
        return {"recipe": self.name, "steps": []}


def _fake(record: list[tuple[object, ...]]) -> dict[str, dict[str, object]]:
    def _get(name: str, *, root: object = None, cache_dir: object = None, verify: bool = True, **kw: object) -> object:
        record.append(("get", name, verify))
        return _FakePipeline(name, verify, record)

    return {
        "nirs4all_repository": {
            "__version__": "1.2.3",
            "list": lambda *, root=None, **filters: [{"root": root, "filters": filters}],
            "card": lambda name, *, root=None: {"name": name, "root": root},
            "get": _get,
            "fetch": lambda name, *, root=None, cache_dir=None, verify=True, with_artifacts=False: {
                "bundle": name,
                "with_artifacts": with_artifacts,
                "root": root,
            },
        }
    }


def test_version_and_health_when_available() -> None:
    with fake_modules(_fake([])):
        provider = PipelineProvider()
        assert provider.version() == "1.2.3"
        health = provider.health()
        assert health.available is True
        assert health.reachable is None  # no network-free probe for the repository client


def test_capabilities() -> None:
    with fake_modules(_fake([])):
        caps = PipelineProvider().capabilities()
    assert caps.serves == (
        "get_pipeline_list",
        "list_pipelines",
        "card",
        "get_pipeline",
        "recipe",
        "get_bundle",
        "verify",
    )
    assert caps.writes is WriteAccess.NONE


def test_recipe_resolves_then_returns_canonical_config() -> None:
    record: list[tuple[object, ...]] = []
    with fake_modules(_fake(record)):
        out = PipelineProvider().recipe("p1")
    assert out == {"recipe": "p1", "steps": []}
    assert ("get", "p1", True) in record  # resolved via get_pipeline honoring the default verify=True
    assert ("recipe", "p1") in record


def test_get_pipeline_list_and_card_forward_filters() -> None:
    with fake_modules(_fake([])):
        provider = PipelineProvider(root="/repo")
        assert provider.get_pipeline_list(framework="nirs4all") == [
            {"root": "/repo", "filters": {"framework": "nirs4all"}}
        ]
        assert provider.list_pipelines(framework="dag-ml") == [{"root": "/repo", "filters": {"framework": "dag-ml"}}]
        assert provider.card("p1") == {"name": "p1", "root": "/repo"}


def test_repository_pipeline_contract_serves_list_and_payload_by_id() -> None:
    record: list[tuple[object, ...]] = []
    with fake_modules(_fake(record)):
        provider = PipelineProvider(root="/repo", cache_dir="/cache")
        rows = provider.get_pipeline_list(kind="recipe")
        pipe = provider.get_pipeline("p1")
    assert rows == [{"root": "/repo", "filters": {"kind": "recipe"}}]
    assert pipe.name == "p1"
    assert ("get", "p1", True) in record


def test_pipeline_lookup_rejects_blank_pipeline_id_before_backing_call() -> None:
    record: list[tuple[object, ...]] = []
    with fake_modules(_fake(record)):
        provider = PipelineProvider()
        with pytest.raises(ValueError, match="repository\\.pipeline_id must be a non-empty string"):
            provider.get_pipeline("")
    assert record == []


def test_get_bundle_forwards_with_artifacts() -> None:
    with fake_modules(_fake([])):
        bundle = PipelineProvider().get_bundle("p1", with_artifacts=True)
    assert bundle == {"bundle": "p1", "with_artifacts": True, "root": None}


def test_verify_resolves_without_double_verify_then_calls_pipeline_verify() -> None:
    record: list[tuple[object, ...]] = []
    with fake_modules(_fake(record)):
        PipelineProvider().verify("p1")
    assert ("get", "p1", False) in record  # resolved with verify=False ...
    assert ("verify", "p1") in record  # ... then verified explicitly exactly once


def test_unavailable_backing_degrades() -> None:
    with hidden_modules("nirs4all_repository"):
        provider = PipelineProvider()
        assert provider.version() == "unavailable"
        assert provider.health().available is False
        with pytest.raises(ProviderUnavailable):
            provider.list_pipelines()

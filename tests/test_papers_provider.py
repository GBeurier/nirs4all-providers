"""Tests for PaperExportProvider read/build delegation (over faked nirs4all_papers submodules)."""
from __future__ import annotations

import pytest

from conftest import fake_modules, hidden_modules
from nirs4all_providers import PaperExportProvider, ProviderUnavailable, WriteAccess


def _build_site(root: str, out: str, io_wasm: object) -> dict[str, object]:
    return {"root": root, "out": out, "io_wasm": io_wasm}


def _fakes() -> dict[str, dict[str, object]]:
    return {
        "nirs4all_papers": {"__version__": "0.2.0"},
        "nirs4all_papers.bundle": {"read_bundle": lambda path: {"bundle": path}},
        "nirs4all_papers.model": {"load_paper": lambda paper_dir: {"paper": paper_dir}},
        "nirs4all_papers.bibliography": {"build_bibliography": lambda ids: {"refs": ids}},
        "nirs4all_papers.site": {"build_site": _build_site},
    }


def test_version_health_and_capabilities() -> None:
    with fake_modules(_fakes()):
        provider = PaperExportProvider()
        assert provider.version() == "0.2.0"
        health = provider.health()
        assert health.available is True
        assert health.reachable is None
        caps = provider.capabilities()
    assert caps.serves == ("inspect_bundle", "load_paper", "build_methods_section", "build_repro_page")
    assert caps.executes is False
    assert caps.writes is WriteAccess.LOCAL_OUTPUT


def test_inspect_and_load_and_methods() -> None:
    with fake_modules(_fakes()):
        provider = PaperExportProvider()
        assert provider.inspect_bundle("/x.n4a") == {"bundle": "/x.n4a"}
        assert provider.load_paper("/paper-dir") == {"paper": "/paper-dir"}
        assert provider.build_methods_section(["pls", "snv"]) == {"refs": ["pls", "snv"]}


def test_build_repro_page_forwards_out_and_io_wasm() -> None:
    with fake_modules(_fakes()):
        provider = PaperExportProvider()
        assert provider.build_repro_page("/root", "/out") == {"root": "/root", "out": "/out", "io_wasm": None}
        assert provider.build_repro_page("/root", "/out", io_wasm="/wasm")["io_wasm"] == "/wasm"


def test_unavailable_backing_degrades() -> None:
    with hidden_modules("nirs4all_papers"):
        provider = PaperExportProvider()
        assert provider.version() == "unavailable"
        assert provider.health().available is False
        with pytest.raises(ProviderUnavailable):
            provider.inspect_bundle("/x.n4a")

"""Tests for PaperExportProvider read/build delegation (over faked nirs4all_papers modules)."""
from __future__ import annotations

import importlib
import sys

import pytest

from conftest import fake_modules, hidden_modules
from nirs4all_providers import (
    Capabilities,
    PaperExportProvider,
    ProviderCapabilityUnavailable,
    ProviderUnavailable,
    WriteAccess,
)


def _build_site(root: str, out: str, io_wasm: object) -> dict[str, object]:
    return {"root": root, "out": out, "io_wasm": io_wasm}


def _fakes() -> dict[str, dict[str, object]]:
    return {
        "nirs4all_papers": {"__version__": "0.2.0"},
        "nirs4all_papers.bundle": {"read_bundle": lambda path: {"bundle": path}},
        "nirs4all_papers.model": {
            "load_paper": lambda paper_dir: {"paper": paper_dir},
            "load_catalog": lambda root: {"root": root, "papers": ["p1", "p2"]},
        },
        "nirs4all_papers.bibliography": {"build_bibliography": lambda ids: {"refs": ids}},
        "nirs4all_papers.provenance": {
            "citation_cff": lambda view: f"cff:{view['paper']}",
            "paper_bibtex": lambda view: f"@misc{{{view['paper']}}}",
        },
        "nirs4all_papers.provider": {},
        "nirs4all_papers.site": {"build_site": _build_site},
    }


def _facade_fakes(calls: list[tuple[str, object]]) -> dict[str, dict[str, object]]:
    def provider_capabilities() -> dict[str, object]:
        calls.append(("provider_capabilities", None))
        return {
            "verbs": {
                "list_papers": "List paper exports.",
                "load_paper_bundle": "Load a paper bundle.",
                "inspect_bundle": "Inspect a bundle.",
                "build_methods_section": "Build methods text.",
                "citation": "Render a citation string.",
                "bibtex": "Render a BibTeX string.",
                "build_repro_page": "Build a local reproduction page.",
                "export_sidecars": "Export local sidecars.",
            },
            "executes": False,
            "writes": "local_output",
            "non_goals": ("execution", "upload", "repository writeback"),
            "dependencies": ("nirs4all_papers",),
            "portability": "facade export plugin",
        }

    def list_papers(root: str) -> dict[str, object]:
        calls.append(("list_papers", root))
        return {"facade_root": root}

    def inspect_bundle(path: str) -> dict[str, object]:
        calls.append(("inspect_bundle", path))
        return {"facade_bundle": path}

    def load_paper_bundle(paper_dir: str) -> dict[str, object]:
        calls.append(("load_paper_bundle", paper_dir))
        return {"facade_paper": paper_dir}

    def build_methods_section(method_ids: list[str]) -> dict[str, object]:
        calls.append(("build_methods_section", tuple(method_ids)))
        return {"facade_refs": method_ids}

    def citation(paper_dir: str) -> str:
        calls.append(("citation", paper_dir))
        return f"facade-cff:{paper_dir}"

    def bibtex(paper_dir: str) -> str:
        calls.append(("bibtex", paper_dir))
        return f"@misc{{facade:{paper_dir}}}"

    def build_repro_page(root: str, out: str, *, io_wasm: str | None = None) -> dict[str, object]:
        calls.append(("build_repro_page", (root, out, io_wasm)))
        return {"facade_root": root, "out": out, "io_wasm": io_wasm}

    def export_sidecars(paper_dir: str, out: str) -> dict[str, object]:
        calls.append(("export_sidecars", (paper_dir, out)))
        return {"paper_dir": paper_dir, "out": out, "written": ["CITATION.cff", "paper.bib"]}

    return {
        "nirs4all_papers": {"__version__": "0.3.0"},
        "nirs4all_papers.provider": {
            "provider_capabilities": provider_capabilities,
            "list_papers": list_papers,
            "inspect_bundle": inspect_bundle,
            "load_paper_bundle": load_paper_bundle,
            "build_methods_section": build_methods_section,
            "citation": citation,
            "bibtex": bibtex,
            "build_repro_page": build_repro_page,
            "export_sidecars": export_sidecars,
        },
    }


def test_importing_providers_does_not_import_papers() -> None:
    saved = {name: sys.modules.get(name) for name in ("nirs4all_papers", "nirs4all_papers.provider")}
    try:
        sys.modules.pop("nirs4all_papers", None)
        sys.modules.pop("nirs4all_papers.provider", None)
        import nirs4all_providers

        importlib.reload(nirs4all_providers)
        assert "nirs4all_papers" not in sys.modules
        assert "nirs4all_papers.provider" not in sys.modules
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def test_facade_delegation_when_available() -> None:
    calls: list[tuple[str, object]] = []
    with fake_modules(_facade_fakes(calls)):
        provider = PaperExportProvider()
        caps = provider.capabilities()
        assert caps == Capabilities(
            serves=(
                "list_papers",
                "inspect_bundle",
                "load_paper",
                "load_paper_bundle",
                "build_methods_section",
                "citation",
                "bibtex",
                "build_repro_page",
                "export_sidecars",
            ),
            executes=False,
            writes=WriteAccess.LOCAL_OUTPUT,
            portability="facade export plugin",
        )
        assert {"load_paper", "citation", "bibtex", "load_paper_bundle", "export_sidecars"} <= set(caps.serves)
        assert provider.list_papers("/root") == {"facade_root": "/root"}
        assert provider.inspect_bundle("/x.n4a") == {"facade_bundle": "/x.n4a"}
        assert provider.load_paper_bundle("/paper-dir") == {"facade_paper": "/paper-dir"}
        assert provider.load_paper("/paper-dir") == {"facade_paper": "/paper-dir"}
        assert provider.build_methods_section(["pls", "snv"]) == {"facade_refs": ["pls", "snv"]}
        assert provider.citation("/paper-dir") == "facade-cff:/paper-dir"
        assert provider.bibtex("/paper-dir") == "@misc{facade:/paper-dir}"
        assert provider.build_repro_page("/root", "/out", io_wasm="/wasm") == {
            "facade_root": "/root",
            "out": "/out",
            "io_wasm": "/wasm",
        }
        assert provider.export_sidecars("/paper-dir", "/out") == {
            "paper_dir": "/paper-dir",
            "out": "/out",
            "written": ["CITATION.cff", "paper.bib"],
        }
    assert calls == [
        ("provider_capabilities", None),
        ("list_papers", "/root"),
        ("inspect_bundle", "/x.n4a"),
        ("load_paper_bundle", "/paper-dir"),
        ("load_paper_bundle", "/paper-dir"),
        ("build_methods_section", ("pls", "snv")),
        ("citation", "/paper-dir"),
        ("bibtex", "/paper-dir"),
        ("build_repro_page", ("/root", "/out", "/wasm")),
        ("export_sidecars", ("/paper-dir", "/out")),
    ]


def test_facade_capabilities_are_clamped_to_provider_contract() -> None:
    def provider_capabilities() -> dict[str, object]:
        return {
            "verbs": {"list_papers": "List paper exports."},
            "executes": True,
            "writes": "local_output",
        }

    with fake_modules(
        {
            "nirs4all_papers": {"__version__": "0.3.0"},
            "nirs4all_papers.provider": {"provider_capabilities": provider_capabilities},
        }
    ):
        caps = PaperExportProvider().capabilities()

    assert caps.executes is False
    assert caps.writes is WriteAccess.LOCAL_OUTPUT
    assert "in-browser replay is approximate" in (caps.portability or "")


def test_version_health_and_capabilities() -> None:
    with fake_modules(_fakes()):
        provider = PaperExportProvider()
        assert provider.version() == "0.2.0"
        health = provider.health()
        assert health.available is True
        assert health.reachable is None
        caps = provider.capabilities()
    assert caps.serves == (
        "list_papers",
        "inspect_bundle",
        "load_paper",
        "load_paper_bundle",
        "build_methods_section",
        "citation",
        "bibtex",
        "build_repro_page",
        "export_sidecars",
    )
    assert caps.executes is False
    assert caps.writes is WriteAccess.LOCAL_OUTPUT
    assert "export plugin" in (caps.portability or "")


def test_papers_provider_is_not_write_side_repository() -> None:
    provider = PaperExportProvider()
    caps = provider.capabilities()
    assert "publish" not in caps.serves
    assert "upload" not in caps.serves
    assert caps.writes is WriteAccess.LOCAL_OUTPUT


def test_inspect_and_load_and_methods() -> None:
    with fake_modules(_fakes()):
        provider = PaperExportProvider()
        assert provider.inspect_bundle("/x.n4a") == {"bundle": "/x.n4a"}
        assert provider.load_paper("/paper-dir") == {"paper": "/paper-dir"}
        assert provider.build_methods_section(["pls", "snv"]) == {"refs": ["pls", "snv"]}


def test_list_papers_and_deposit_sidecar_strings() -> None:
    with fake_modules(_fakes()):
        provider = PaperExportProvider()
        assert provider.list_papers("/root") == {"root": "/root", "papers": ["p1", "p2"]}
        # citation/bibtex load the paper view, then serialize it to text — pure reads, no file write.
        assert provider.citation("/paper-dir") == "cff:/paper-dir"
        assert provider.bibtex("/paper-dir") == "@misc{/paper-dir}"


def test_build_repro_page_forwards_out_and_io_wasm() -> None:
    with fake_modules(_fakes()):
        provider = PaperExportProvider()
        assert provider.build_repro_page("/root", "/out") == {"root": "/root", "out": "/out", "io_wasm": None}
        assert provider.build_repro_page("/root", "/out", io_wasm="/wasm")["io_wasm"] == "/wasm"


def test_export_sidecars_requires_facade() -> None:
    with fake_modules(_fakes()):
        provider = PaperExportProvider()
        with pytest.raises(ProviderCapabilityUnavailable, match="export_sidecars"):
            provider.export_sidecars("/paper-dir", "/out")


def test_unavailable_backing_degrades() -> None:
    with hidden_modules("nirs4all_papers"):
        provider = PaperExportProvider()
        assert provider.version() == "unavailable"
        assert provider.health().available is False
        with pytest.raises(ProviderUnavailable):
            provider.inspect_bundle("/x.n4a")

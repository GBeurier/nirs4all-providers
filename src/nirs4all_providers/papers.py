"""PaperExportProvider — read/build client over :mod:`nirs4all_papers` (PROV-004).

Wraps the real API verbatim: ``read_bundle`` (stdlib-only bundle inspection), ``load_paper`` /
``load_catalog``, ``build_bibliography`` (methods section), the ``citation_cff`` / ``paper_bibtex``
deposit-sidecar *string* builders, and ``build_site`` (the reproduction page). The in-browser replay
the page ships is an *approximate* reference engine (CAP-004), not numerically portable — this provider
never executes it. Every method here is a pure read that returns a value **except** ``build_repro_page``:
the only write is that explicit, marker-guarded build into a caller-chosen output directory; there is no
network or ecosystem write.
"""
from __future__ import annotations

from typing import Any, ClassVar

from ._adapter import _BaseProvider
from .base import Capabilities, WriteAccess

__all__ = ["PaperExportProvider"]


class PaperExportProvider(_BaseProvider):
    """Thin read/build client over the ``nirs4all-papers`` reproduction publisher."""

    provider_id: ClassVar[str] = "papers"
    _module: ClassVar[str] = "nirs4all_papers"
    _extra: ClassVar[str] = "papers"

    def capabilities(self) -> Capabilities:
        return Capabilities(
            serves=(
                "list_papers",
                "inspect_bundle",
                "load_paper",
                "build_methods_section",
                "citation",
                "bibtex",
                "build_repro_page",
            ),
            executes=False,
            writes=WriteAccess.LOCAL_OUTPUT,
            portability="in-browser replay is approximate (CAP-004), not numerically portable",
        )

    def list_papers(self, root: str) -> Any:
        """Discover every ``papers/<slug>/`` under ``root`` as a catalog (delegates to ``load_catalog``)."""
        self._require()
        from nirs4all_papers.model import load_catalog

        return load_catalog(root)

    def inspect_bundle(self, path: str) -> Any:
        """Read a ``.n4a`` bundle's header/steps (delegates to ``nirs4all_papers.bundle.read_bundle``)."""
        self._require()
        from nirs4all_papers.bundle import read_bundle

        return read_bundle(path)

    def load_paper(self, paper_dir: str) -> Any:
        """Load a bundle + ``paper.yaml`` into a view (delegates to ``nirs4all_papers.model.load_paper``)."""
        self._require()
        from nirs4all_papers.model import load_paper

        return load_paper(paper_dir)

    def build_methods_section(self, method_ids: list[str]) -> Any:
        """Resolve methods to references (delegates to ``nirs4all_papers.bibliography.build_bibliography``)."""
        self._require()
        from nirs4all_papers.bibliography import build_bibliography

        return build_bibliography(method_ids)

    def citation(self, paper_dir: str) -> str:
        """Return a paper's ``CITATION.cff`` text (delegates to ``provenance.citation_cff``); no file write."""
        self._require()
        from nirs4all_papers.model import load_paper
        from nirs4all_papers.provenance import citation_cff

        result: str = citation_cff(load_paper(paper_dir))
        return result

    def bibtex(self, paper_dir: str) -> str:
        """Return a paper's BibTeX entry (delegates to ``provenance.paper_bibtex``); no file write."""
        self._require()
        from nirs4all_papers.model import load_paper
        from nirs4all_papers.provenance import paper_bibtex

        result: str = paper_bibtex(load_paper(paper_dir))
        return result

    def build_repro_page(self, root: str, out: str, *, io_wasm: str | None = None) -> Any:
        """Build the static reproduction page (delegates to ``nirs4all_papers.site.build_site``).

        Writes only into ``out``; the backing ``build_site`` is marker-guarded and refuses to wipe a
        directory it did not create.
        """
        self._require()
        from nirs4all_papers.site import build_site

        return build_site(root, out, io_wasm)

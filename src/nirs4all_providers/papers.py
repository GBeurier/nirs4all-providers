"""PaperExportProvider — potential export-plugin client over :mod:`nirs4all_papers` (PROV-004).

When available, this adapter delegates through the first-party ``nirs4all_papers.provider`` facade:
``provider_capabilities``, ``list_papers``, ``load_paper_bundle``, ``inspect_bundle``,
``build_methods_section``, ``build_repro_page``, and ``export_sidecars``. Older ``nirs4all-papers``
installs without that facade still work for the historical read/build methods through the legacy
lower-level imports. This adapter is **not** a write-side repository; at most it is a local export
plugin over methods/provenance/UI helpers. The in-browser replay the page ships is an *approximate*
reference engine (CAP-004), not numerically portable — this provider never executes it. Every method
here is a pure read that returns a value **except** explicit, caller-chosen local-output methods such as
``build_repro_page`` and ``export_sidecars``; there is no network or ecosystem write.
"""
from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module
from typing import Any, ClassVar

from ._adapter import _BaseProvider
from ._softimport import ProviderCapabilityUnavailable
from .base import Capabilities, WriteAccess

__all__ = ["PaperExportProvider"]


_FACADE_MODULE = "nirs4all_papers.provider"


def _default_capabilities() -> Capabilities:
    return Capabilities(
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
        portability="potential export plugin; in-browser replay is approximate (CAP-004)",
    )


def _adapter_serves(serves: Any) -> tuple[str, ...]:
    """Return adapter-level serves: compatibility surface first, facade-only additions after."""
    merged = list(_default_capabilities().serves)
    seen = set(merged)
    for name in serves:
        serve = str(name)
        if serve not in seen:
            merged.append(serve)
            seen.add(serve)
    return tuple(merged)


class PaperExportProvider(_BaseProvider):
    """Thin read/build client over the ``nirs4all-papers`` reproduction publisher."""

    provider_id: ClassVar[str] = "papers"
    _module: ClassVar[str] = "nirs4all_papers"
    _extra: ClassVar[str] = "papers"

    def capabilities(self) -> Capabilities:
        facade_fn = self._facade_function("provider_capabilities", require_backing=False)
        if facade_fn is None:
            return _default_capabilities()
        return self._coerce_capabilities(facade_fn())

    def _facade_function(self, name: str, *, require_backing: bool = True) -> Any | None:
        """Return a callable from ``nirs4all_papers.provider`` when that facade exists."""
        if require_backing:
            self._require()
        elif self._imp.module is None:
            return None

        try:
            facade = import_module(_FACADE_MODULE)
        except ModuleNotFoundError as exc:
            if exc.name == _FACADE_MODULE:
                return None
            raise
        return getattr(facade, name, None)

    def _require_facade_function(self, name: str) -> Any:
        facade_fn = self._facade_function(name)
        if facade_fn is None:
            raise ProviderCapabilityUnavailable(
                self.provider_id,
                capability=name,
                reason=f"{_FACADE_MODULE!r} does not provide {name!r}",
                extra=self._extra,
                module=_FACADE_MODULE,
            )
        return facade_fn

    def _coerce_capabilities(self, raw: Any) -> Capabilities:
        if isinstance(raw, Capabilities):
            raw_serves: Any = raw.serves
            writes = raw.writes
            portability = raw.portability
        elif isinstance(raw, dict):
            raw_serves = raw.get("serves")
            if raw_serves is None:
                verbs = raw.get("verbs", ())
                raw_serves = verbs.keys() if isinstance(verbs, Mapping) else verbs
            writes = raw.get("writes", WriteAccess.LOCAL_OUTPUT)
            portability = raw.get("portability")
        else:
            raw_serves = getattr(raw, "serves", None)
            if raw_serves is None:
                verbs = getattr(raw, "verbs", ())
                raw_serves = verbs.keys() if isinstance(verbs, Mapping) else verbs
            writes = getattr(raw, "writes", WriteAccess.LOCAL_OUTPUT)
            portability = getattr(raw, "portability", None)
        if not isinstance(writes, WriteAccess):
            writes = WriteAccess(str(writes).lower().replace("_", "-"))
        return Capabilities(
            serves=_adapter_serves(raw_serves),
            executes=False,
            writes=writes,
            portability=_default_capabilities().portability if portability is None else str(portability),
        )

    def list_papers(self, root: str) -> Any:
        """Discover every ``papers/<slug>/`` under ``root``."""
        facade_fn = self._facade_function("list_papers")
        if facade_fn is not None:
            return facade_fn(root)

        self._require()
        from nirs4all_papers.model import load_catalog

        return load_catalog(root)

    def inspect_bundle(self, path: str) -> Any:
        """Read a ``.n4a`` bundle's header/steps."""
        facade_fn = self._facade_function("inspect_bundle")
        if facade_fn is not None:
            return facade_fn(path)

        self._require()
        from nirs4all_papers.bundle import read_bundle

        return read_bundle(path)

    def load_paper_bundle(self, paper_dir: str) -> Any:
        """Load a bundle + ``paper.yaml`` into the papers facade's bundle view."""
        facade_fn = self._facade_function("load_paper_bundle")
        if facade_fn is not None:
            return facade_fn(paper_dir)

        self._require()
        from nirs4all_papers.model import load_paper

        return load_paper(paper_dir)

    def load_paper(self, paper_dir: str) -> Any:
        """Compatibility alias for the facade ``load_paper_bundle`` operation."""
        return self.load_paper_bundle(paper_dir)

    def build_methods_section(self, method_ids: list[str]) -> Any:
        """Resolve methods to references."""
        facade_fn = self._facade_function("build_methods_section")
        if facade_fn is not None:
            return facade_fn(method_ids)

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
        """Build the static reproduction page.

        Writes only into ``out``; backing implementations are marker-guarded and refuse to wipe a
        directory they did not create.
        """
        facade_fn = self._facade_function("build_repro_page")
        if facade_fn is not None:
            return facade_fn(root, out, io_wasm=io_wasm)

        self._require()
        from nirs4all_papers.site import build_site

        return build_site(root, out, io_wasm=io_wasm)

    def export_sidecars(self, paper_dir: str, out: str) -> Any:
        """Export paper sidecar files into explicit caller-chosen local output ``out``."""
        facade_fn = self._require_facade_function("export_sidecars")
        return facade_fn(paper_dir, out)

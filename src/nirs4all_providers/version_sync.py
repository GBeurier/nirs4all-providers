"""Version/tag sync guard for nirs4all-providers releases.

The canonical package version is the literal ``__version__`` assignment in this
package's ``__init__.py``. Non-release runs intentionally pass without a tag so
regular branch CI and local development are not blocked.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "VersionSyncDiagnostic",
    "VersionSyncReport",
    "build_report",
    "main",
    "read_canonical_version",
    "render_text",
]

_EXPECTED_TAG_ENV = "NIRS4ALL_PROVIDERS_EXPECTED_TAG"
_VERSION_FILE = Path(__file__).resolve().parent / "__init__.py"


@dataclass(frozen=True)
class VersionSyncDiagnostic:
    """One blocking version-sync diagnostic."""

    code: str
    message: str
    mitigation: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "mitigation": self.mitigation,
        }


@dataclass(frozen=True)
class VersionSyncReport:
    """Version-sync state captured for a release or non-release context."""

    ok: bool
    canonical_version: str | None
    canonical_tag: str | None
    release_tag: str | None
    context: str
    skipped: bool
    diagnostics: tuple[VersionSyncDiagnostic, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "boundary": "providers-version-sync",
            "canonical_version": self.canonical_version,
            "canonical_tag": self.canonical_tag,
            "release_tag": self.release_tag,
            "context": self.context,
            "skipped": self.skipped,
            "diagnostics": [diagnostic.as_dict() for diagnostic in self.diagnostics],
        }


def read_canonical_version(version_file: str | Path = _VERSION_FILE) -> str:
    """Return the literal ``__version__`` from the canonical package file."""

    path = Path(version_file)
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for node in module.body:
        if isinstance(node, ast.Assign) and any(_is_version_target(target) for target in node.targets):
            return _string_literal_value(node.value)
        if isinstance(node, ast.AnnAssign) and _is_version_target(node.target):
            return _string_literal_value(node.value)

    raise ValueError(f"canonical version not found in {path}")


def _is_version_target(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "__version__"


def _string_literal_value(node: ast.expr | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    raise ValueError("__version__ must be a string literal")


def _canonical_tag(version: str) -> str:
    return f"v{version}"


def _normalize_tag(tag: str) -> str:
    return tag.removeprefix("refs/tags/").strip()


def _github_context_tag(environ: Mapping[str, str]) -> tuple[str, bool, str | None]:
    event_name = environ.get("GITHUB_EVENT_NAME")
    ref_type = environ.get("GITHUB_REF_TYPE")
    ref_name = environ.get("GITHUB_REF_NAME")
    ref = environ.get("GITHUB_REF")

    is_release_context = event_name == "release" or ref_type == "tag" or (ref or "").startswith("refs/tags/")
    if not is_release_context:
        return "non-release", False, None

    release_tag = ref_name or ref
    context = "github-release" if event_name == "release" else "github-tag"
    return context, True, _normalize_tag(release_tag) if release_tag else None


def _release_context(
    *,
    expected_tag: str | None,
    environ: Mapping[str, str],
) -> tuple[str, bool, str | None]:
    if expected_tag:
        return "explicit", True, _normalize_tag(expected_tag)

    env_tag = environ.get(_EXPECTED_TAG_ENV)
    if env_tag:
        return f"env:{_EXPECTED_TAG_ENV}", True, _normalize_tag(env_tag)

    return _github_context_tag(environ)


def build_report(
    *,
    expected_tag: str | None = None,
    environ: Mapping[str, str] | None = None,
    version_file: str | Path = _VERSION_FILE,
) -> VersionSyncReport:
    """Check that the canonical version matches the release tag when one exists."""

    env = os.environ if environ is None else environ
    context, release_required, release_tag = _release_context(expected_tag=expected_tag, environ=env)
    diagnostics: list[VersionSyncDiagnostic] = []

    try:
        canonical_version = read_canonical_version(version_file)
    except (OSError, ValueError) as exc:
        diagnostics.append(
            VersionSyncDiagnostic(
                code="canonical_version_unreadable",
                message=f"could not read canonical providers version from {version_file}: {exc}",
                mitigation="Ensure src/nirs4all_providers/__init__.py contains a literal __version__ assignment.",
            )
        )
        return VersionSyncReport(
            ok=False,
            canonical_version=None,
            canonical_tag=None,
            release_tag=release_tag,
            context=context,
            skipped=False,
            diagnostics=tuple(diagnostics),
        )

    canonical_tag = _canonical_tag(canonical_version)
    if release_required and not release_tag:
        diagnostics.append(
            VersionSyncDiagnostic(
                code="missing_release_tag",
                message="release context was detected but no release tag was available.",
                mitigation=(
                    f"Set GITHUB_REF_NAME, GITHUB_REF, or {_EXPECTED_TAG_ENV} to the expected tag "
                    f"{canonical_tag!r}."
                ),
            )
        )
    elif release_required and release_tag != canonical_tag:
        diagnostics.append(
            VersionSyncDiagnostic(
                code="version_tag_mismatch",
                message=(
                    f"canonical providers version {canonical_version!r} expects tag {canonical_tag!r}, "
                    f"but release context provided {release_tag!r}."
                ),
                mitigation="Retag the release or update src/nirs4all_providers/__init__.py::__version__.",
            )
        )

    return VersionSyncReport(
        ok=not diagnostics,
        canonical_version=canonical_version,
        canonical_tag=canonical_tag,
        release_tag=release_tag,
        context=context,
        skipped=not release_required,
        diagnostics=tuple(diagnostics),
    )


def render_text(report: VersionSyncReport) -> str:
    """Render a compact human-readable version-sync report."""

    status = "PASS" if report.ok else "FAIL"
    suffix = " (non-release skip)" if report.skipped else ""
    lines = [f"NIRS4ALL providers version-sync guard: {status}{suffix}"]
    lines.append(f"Context: {report.context}")
    lines.append(f"Canonical version: {report.canonical_version or 'unreadable'}")
    lines.append(f"Expected tag: {report.canonical_tag or 'unresolved'}")
    lines.append(f"Release tag: {report.release_tag or 'none'}")
    if report.diagnostics:
        lines.append("")
        lines.append("Diagnostics:")
        for diagnostic in report.diagnostics:
            lines.append(f"- {diagnostic.code}: {diagnostic.message}")
            lines.append(f"  mitigation: {diagnostic.mitigation}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check nirs4all-providers version/tag sync.")
    parser.add_argument("--json", action="store_true", help="emit the version-sync report as JSON")
    parser.add_argument(
        "--expected-tag",
        help=(
            f"expected release tag to compare with the canonical version; defaults to {_EXPECTED_TAG_ENV} "
            "or GitHub release/tag context"
        ),
    )
    parser.add_argument(
        "--version-file",
        default=str(_VERSION_FILE),
        help="package file containing the canonical __version__ assignment",
    )
    args = parser.parse_args(argv)

    report = build_report(expected_tag=args.expected_tag, version_file=args.version_file)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 0 if report.ok else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

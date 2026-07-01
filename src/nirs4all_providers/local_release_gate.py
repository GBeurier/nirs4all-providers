"""Local-workspace harness for the strict providers release gate.

This module does not fake optional backings. It only verifies that the expected
sibling source trees are real Python packages, prepends their ``src`` directories
to ``sys.path``, then delegates to :mod:`nirs4all_providers.release_gate`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import release_gate

__all__ = [
    "LocalReleaseGateReport",
    "LocalSiblingDiagnostic",
    "LocalSiblingRow",
    "build_local_report",
    "main",
    "render_text",
]

_WORKSPACE_ROOT_ENV = "NIRS4ALL_WORKSPACE_ROOT"


@dataclass(frozen=True)
class _Sibling:
    provider_id: str
    repo_name: str
    module_name: str


_SIBLINGS = (
    _Sibling("datasets", "nirs4all-datasets", "nirs4all_datasets"),
    _Sibling("repository", "nirs4all-repository", "nirs4all_repository"),
    _Sibling("benchmarks", "nirs4all-benchmarks", "nirs4all_benchmarks"),
    _Sibling("papers", "nirs4all-papers", "nirs4all_papers"),
)


@dataclass(frozen=True)
class LocalSiblingDiagnostic:
    """One blocking local-sibling setup diagnostic."""

    provider_id: str
    code: str
    message: str
    mitigation: str

    def as_dict(self) -> dict[str, str]:
        return {
            "provider_id": self.provider_id,
            "code": self.code,
            "message": self.message,
            "mitigation": self.mitigation,
        }


@dataclass(frozen=True)
class LocalSiblingRow:
    """Verified local sibling source-tree paths."""

    provider_id: str
    repo_path: str
    src_path: str
    module_path: str
    package: bool

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "provider_id": self.provider_id,
            "repo_path": self.repo_path,
            "src_path": self.src_path,
            "module_path": self.module_path,
            "package": self.package,
        }


@dataclass(frozen=True)
class LocalReleaseGateReport:
    """Combined local-sibling preflight and strict release-gate report."""

    ok: bool
    workspace_root: str | None
    rows: tuple[LocalSiblingRow, ...]
    diagnostics: tuple[LocalSiblingDiagnostic, ...]
    release_report: release_gate.ProviderReleaseGateReport | None

    def as_dict(self) -> dict[str, Any]:
        release_payload = self.release_report.as_dict() if self.release_report is not None else None
        release_diagnostics = release_payload["diagnostics"] if release_payload is not None else []
        return {
            "ok": self.ok,
            "boundary": "providers-local-sibling-release-gate",
            "workspace_root": self.workspace_root,
            "local_siblings": [row.as_dict() for row in self.rows],
            "local_diagnostics": [diagnostic.as_dict() for diagnostic in self.diagnostics],
            "release_gate": release_payload,
            "diagnostics": [diagnostic.as_dict() for diagnostic in self.diagnostics] + release_diagnostics,
        }


def _iter_candidate_roots(start: Path) -> Sequence[Path]:
    resolved = start.expanduser().resolve()
    return (resolved, *resolved.parents)


def _default_workspace_root(start: Path) -> Path | None:
    env_root = os.environ.get(_WORKSPACE_ROOT_ENV)
    if env_root:
        return Path(env_root).expanduser().resolve()

    for candidate in _iter_candidate_roots(start):
        if any((candidate / sibling.repo_name).exists() for sibling in _SIBLINGS):
            return candidate
    return None


def _workspace_not_found() -> LocalSiblingDiagnostic:
    repos = ", ".join(sibling.repo_name for sibling in _SIBLINGS)
    return LocalSiblingDiagnostic(
        provider_id="all",
        code="workspace_not_found",
        message=f"could not find a workspace root containing any provider sibling repos: {repos}.",
        mitigation=f"Run from the nirs4all workspace or set `{_WORKSPACE_ROOT_ENV}` / pass `--workspace-root`.",
    )


def _inspect_siblings(workspace_root: Path) -> tuple[tuple[LocalSiblingRow, ...], tuple[LocalSiblingDiagnostic, ...]]:
    rows: list[LocalSiblingRow] = []
    diagnostics: list[LocalSiblingDiagnostic] = []

    for sibling in _SIBLINGS:
        repo_path = workspace_root / sibling.repo_name
        src_path = repo_path / "src"
        module_path = src_path / sibling.module_name
        package = module_path.is_dir() and (module_path / "__init__.py").is_file()

        rows.append(
            LocalSiblingRow(
                provider_id=sibling.provider_id,
                repo_path=str(repo_path),
                src_path=str(src_path),
                module_path=str(module_path),
                package=package,
            )
        )

        if not repo_path.is_dir():
            diagnostics.append(
                LocalSiblingDiagnostic(
                    provider_id=sibling.provider_id,
                    code="missing_repo",
                    message=f"local sibling repo {sibling.repo_name!r} is absent at {repo_path}.",
                    mitigation=f"Checkout {sibling.repo_name} under {workspace_root} and rerun the local gate.",
                )
            )
        elif not src_path.is_dir():
            diagnostics.append(
                LocalSiblingDiagnostic(
                    provider_id=sibling.provider_id,
                    code="missing_src",
                    message=f"local sibling repo {sibling.repo_name!r} has no src directory at {src_path}.",
                    mitigation=f"Package {sibling.repo_name} with a src/{sibling.module_name} import tree.",
                )
            )
        elif not package:
            diagnostics.append(
                LocalSiblingDiagnostic(
                    provider_id=sibling.provider_id,
                    code="not_package",
                    message=(
                        f"local sibling repo {sibling.repo_name!r} does not expose package "
                        f"{sibling.module_name!r} at {module_path}."
                    ),
                    mitigation=f"Ensure {module_path}/__init__.py exists before using it as a local release backing.",
                )
            )

    return tuple(rows), tuple(diagnostics)


def _prepend_source_paths(rows: Sequence[LocalSiblingRow]) -> None:
    paths = [row.src_path for row in rows if row.package]
    for src_path in reversed(paths):
        if src_path not in sys.path:
            sys.path.insert(0, src_path)


def _forget_backing_modules() -> None:
    module_names = tuple(sibling.module_name for sibling in _SIBLINGS)
    for loaded_name in tuple(sys.modules):
        if loaded_name in module_names or any(
            loaded_name.startswith(f"{module_name}.") for module_name in module_names
        ):
            sys.modules.pop(loaded_name, None)


def build_local_report(*, workspace_root: str | Path | None = None) -> LocalReleaseGateReport:
    """Run the strict release gate against verified local sibling packages."""

    root = (
        Path(workspace_root).expanduser().resolve()
        if workspace_root is not None
        else _default_workspace_root(Path.cwd())
    )
    if root is None:
        return LocalReleaseGateReport(
            ok=False,
            workspace_root=None,
            rows=(),
            diagnostics=(_workspace_not_found(),),
            release_report=None,
        )

    rows, diagnostics = _inspect_siblings(root)
    if diagnostics:
        return LocalReleaseGateReport(
            ok=False,
            workspace_root=str(root),
            rows=rows,
            diagnostics=diagnostics,
            release_report=None,
        )

    _prepend_source_paths(rows)
    _forget_backing_modules()
    strict_report = release_gate.build_report()
    return LocalReleaseGateReport(
        ok=strict_report.ok,
        workspace_root=str(root),
        rows=rows,
        diagnostics=(),
        release_report=strict_report,
    )


def render_text(report: LocalReleaseGateReport) -> str:
    """Render a compact human-readable local-sibling release-gate report."""

    status = "PASS" if report.ok else "FAIL"
    lines = [f"NIRS4ALL providers local sibling release gate: {status}"]
    lines.append(f"Workspace root: {report.workspace_root or 'not found'}")
    lines.append("")
    lines.append("Local siblings:")
    for row in report.rows:
        lines.append(f"- {row.provider_id}: package={row.package} src={row.src_path}")

    if report.diagnostics:
        lines.append("")
        lines.append("Local diagnostics:")
        for diagnostic in report.diagnostics:
            lines.append(f"- {diagnostic.provider_id} [{diagnostic.code}]: {diagnostic.message}")
            lines.append(f"  mitigation: {diagnostic.mitigation}")

    if report.release_report is not None:
        lines.append("")
        lines.append(release_gate.render_text(report.release_report))

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the providers release gate against local sibling repos.")
    parser.add_argument("--json", action="store_true", help="emit the combined local + strict gate report as JSON")
    parser.add_argument(
        "--workspace-root",
        help=(
            "workspace containing nirs4all-datasets, nirs4all-repository, "
            "nirs4all-benchmarks, and nirs4all-papers"
        ),
    )
    args = parser.parse_args(argv)

    report = build_local_report(workspace_root=args.workspace_root)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 0 if report.ok else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

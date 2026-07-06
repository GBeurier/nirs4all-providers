"""Local-workspace harness for the strict providers release gate.

This module does not fake optional backings. It only verifies that the expected
public sibling source trees are real Python packages, prepends their ``src``
directories to ``sys.path``, then delegates to
:mod:`nirs4all_providers.release_gate`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import release_gate

__all__ = [
    "LocalReleaseGateReport",
    "LocalDependencyPathRow",
    "LocalSiblingDiagnostic",
    "LocalSiblingRow",
    "build_local_report",
    "main",
    "render_text",
]

_WORKSPACE_ROOT_ENV = "NIRS4ALL_WORKSPACE_ROOT"
_DEPENDENCY_PATHS_ENV = "NIRS4ALL_PROVIDERS_LOCAL_DEPENDENCY_PATHS"
_MISSING_MODULE_RE = re.compile(r"No module named ['\"](?P<module>[^'\"]+)['\"]")
_IMPORT_TO_DISTRIBUTION = {
    "yaml": "pyyaml",
}


@dataclass(frozen=True)
class _Sibling:
    provider_id: str
    repo_name: str
    module_name: str


_SIBLINGS = (
    _Sibling("datasets", "nirs4all-datasets", "nirs4all_datasets"),
    _Sibling("repository", "nirs4all-repository", "nirs4all_repository"),
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
class LocalDependencyPathRow:
    """One explicit dependency path added for local-gate imports."""

    input_path: str
    path: str
    kind: str

    def as_dict(self) -> dict[str, str]:
        return {
            "input_path": self.input_path,
            "path": self.path,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class LocalReleaseGateReport:
    """Combined local-sibling preflight and strict release-gate report."""

    ok: bool
    workspace_root: str | None
    rows: tuple[LocalSiblingRow, ...]
    dependency_paths: tuple[LocalDependencyPathRow, ...]
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
            "dependency_paths": [row.as_dict() for row in self.dependency_paths],
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


def _iter_dependency_path_inputs(explicit_paths: Sequence[str | Path] | None) -> tuple[str, ...]:
    paths = [str(path) for path in explicit_paths or () if str(path)]
    env_paths = os.environ.get(_DEPENDENCY_PATHS_ENV)
    if env_paths:
        paths.extend(path for path in env_paths.split(os.pathsep) if path)
    return tuple(paths)


def _venv_site_packages(venv_root: Path) -> tuple[Path, ...]:
    candidates = [path for path in sorted((venv_root / "lib").glob("python*/site-packages")) if path.is_dir()]
    windows_site = venv_root / "Lib" / "site-packages"
    if windows_site.is_dir():
        candidates.append(windows_site)
    return tuple(candidates)


def _resolve_dependency_paths(
    explicit_paths: Sequence[str | Path] | None,
) -> tuple[tuple[LocalDependencyPathRow, ...], tuple[LocalSiblingDiagnostic, ...]]:
    rows: list[LocalDependencyPathRow] = []
    diagnostics: list[LocalSiblingDiagnostic] = []

    for raw_path in _iter_dependency_path_inputs(explicit_paths):
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            diagnostics.append(
                LocalSiblingDiagnostic(
                    provider_id="all",
                    code="missing_dependency_path",
                    message=f"explicit dependency path does not exist: {path}.",
                    mitigation=(
                        "Create the venv/path first or remove it from --dependency-path / "
                        f"`{_DEPENDENCY_PATHS_ENV}`."
                    ),
                )
            )
            continue
        if not path.is_dir():
            diagnostics.append(
                LocalSiblingDiagnostic(
                    provider_id="all",
                    code="invalid_dependency_path",
                    message=f"explicit dependency path is not a directory: {path}.",
                    mitigation="Pass a venv root, a site-packages directory, or another importable Python path.",
                )
            )
            continue

        if (path / "pyvenv.cfg").is_file():
            site_packages = _venv_site_packages(path)
            if not site_packages:
                diagnostics.append(
                    LocalSiblingDiagnostic(
                        provider_id="all",
                        code="invalid_dependency_venv",
                        message=f"explicit dependency venv has no site-packages directory: {path}.",
                        mitigation="Pass a populated virtualenv root or its site-packages directory.",
                    )
                )
                continue
            rows.extend(
                LocalDependencyPathRow(input_path=raw_path, path=str(site_package), kind="venv-site-packages")
                for site_package in site_packages
            )
        else:
            rows.append(LocalDependencyPathRow(input_path=raw_path, path=str(path), kind="python-path"))

    return tuple(rows), tuple(diagnostics)


def _prepend_dependency_paths(rows: Sequence[LocalDependencyPathRow]) -> None:
    for row in reversed(rows):
        if row.path not in sys.path:
            sys.path.insert(0, row.path)


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


def _extract_missing_module(detail: str | None) -> str | None:
    if not detail:
        return None
    match = _MISSING_MODULE_RE.search(detail)
    if match is None:
        return None
    return match.group("module")


def _distribution_name(requirement: str) -> str:
    head = requirement.strip().split(";", 1)[0].strip()
    return re.split(r"\s|\[|<|>|=|!|~", head, maxsplit=1)[0]


def _normalize_requirement_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _dependency_requirement(repo_path: Path, missing_module: str) -> str | None:
    pyproject_path = repo_path / "pyproject.toml"
    if not pyproject_path.is_file():
        return None

    try:
        payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None

    project = payload.get("project", {})
    if not isinstance(project, dict):
        return None
    dependencies = project.get("dependencies", [])
    if not isinstance(dependencies, list):
        return None

    wanted = _normalize_requirement_name(_IMPORT_TO_DISTRIBUTION.get(missing_module, missing_module))
    for dependency in dependencies:
        if not isinstance(dependency, str):
            continue
        if _normalize_requirement_name(_distribution_name(dependency)) == wanted:
            return dependency
    return None


def _dependency_diagnostics(
    rows: Sequence[LocalSiblingRow],
    strict_report: release_gate.ProviderReleaseGateReport,
) -> tuple[LocalSiblingDiagnostic, ...]:
    sibling_by_provider = {sibling.provider_id: sibling for sibling in _SIBLINGS}
    row_by_provider = {row.provider_id: row for row in rows}
    diagnostics: list[LocalSiblingDiagnostic] = []

    for gate_row in strict_report.rows:
        if gate_row.health.available:
            continue
        sibling = sibling_by_provider.get(gate_row.provider_id)
        row = row_by_provider.get(gate_row.provider_id)
        missing_module = _extract_missing_module(gate_row.health.detail)
        if sibling is None or row is None or missing_module is None or missing_module == sibling.module_name:
            continue

        requirement = _dependency_requirement(Path(row.repo_path), missing_module)
        requirement_detail = f" Required distribution: {requirement!r}." if requirement else ""
        diagnostics.append(
            LocalSiblingDiagnostic(
                provider_id=gate_row.provider_id,
                code="missing_dependency",
                message=(
                    f"local sibling {sibling.repo_name!r} is present, but importing {sibling.module_name!r} "
                    f"failed because dependency module {missing_module!r} is missing.{requirement_detail}"
                ),
                mitigation=(
                    "Run the local gate with an environment containing the sibling's real dependencies, or pass an "
                    f"existing venv/site-packages path with --dependency-path / `{_DEPENDENCY_PATHS_ENV}`."
                ),
            )
        )

    return tuple(diagnostics)


def build_local_report(
    *,
    workspace_root: str | Path | None = None,
    dependency_paths: Sequence[str | Path] | None = None,
) -> LocalReleaseGateReport:
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
            dependency_paths=(),
            diagnostics=(_workspace_not_found(),),
            release_report=None,
        )

    dependency_path_rows, dependency_path_diagnostics = _resolve_dependency_paths(dependency_paths)
    if dependency_path_diagnostics:
        return LocalReleaseGateReport(
            ok=False,
            workspace_root=str(root),
            rows=(),
            dependency_paths=dependency_path_rows,
            diagnostics=dependency_path_diagnostics,
            release_report=None,
        )

    rows, diagnostics = _inspect_siblings(root)
    if diagnostics:
        return LocalReleaseGateReport(
            ok=False,
            workspace_root=str(root),
            rows=rows,
            dependency_paths=dependency_path_rows,
            diagnostics=diagnostics,
            release_report=None,
        )

    _prepend_dependency_paths(dependency_path_rows)
    _prepend_source_paths(rows)
    _forget_backing_modules()
    strict_report = release_gate.build_report()
    dependency_diagnostics = _dependency_diagnostics(rows, strict_report)
    return LocalReleaseGateReport(
        ok=strict_report.ok and not dependency_diagnostics,
        workspace_root=str(root),
        rows=rows,
        dependency_paths=dependency_path_rows,
        diagnostics=dependency_diagnostics,
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

    if report.dependency_paths:
        lines.append("")
        lines.append("Dependency paths:")
        for dependency_path in report.dependency_paths:
            lines.append(f"- {dependency_path.kind}: {dependency_path.path}")

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
            "and any explicit dependency paths needed by those packages"
        ),
    )
    parser.add_argument(
        "--dependency-path",
        action="append",
        help=(
            "existing dependency venv root, site-packages directory, or Python path to prepend before the strict gate; "
            f"may be repeated or set via `{_DEPENDENCY_PATHS_ENV}`"
        ),
    )
    args = parser.parse_args(argv)

    report = build_local_report(workspace_root=args.workspace_root, dependency_paths=args.dependency_path)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 0 if report.ok else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

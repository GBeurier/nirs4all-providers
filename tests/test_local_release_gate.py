"""Tests for the local-sibling providers release-gate harness."""
from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from nirs4all_providers import local_release_gate

_BACKING_MODULES = (
    "nirs4all_datasets",
    "nirs4all_repository",
    "nirs4all_benchmarks",
    "nirs4all_papers",
)

_SIBLING_PACKAGES = {
    "nirs4all-datasets": ("nirs4all_datasets", "__version__ = '1'\n\ndef list(root, **filters):\n    return []\n"),
    "nirs4all-repository": ("nirs4all_repository", "__version__ = '1'\n"),
    "nirs4all-benchmarks": ("nirs4all_benchmarks", "__version__ = '1'\n"),
    "nirs4all-papers": ("nirs4all_papers", "__version__ = '1'\n"),
}


@contextmanager
def _isolated_import_state() -> Iterator[None]:
    saved_path = list(sys.path)
    saved_modules = {name: sys.modules.get(name) for name in _BACKING_MODULES}
    try:
        for name in _BACKING_MODULES:
            sys.modules.pop(name, None)
        yield
    finally:
        sys.path[:] = saved_path
        for name, module in saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def _write_sibling_packages(workspace_root: Path) -> None:
    for repo_name, (module_name, module_source) in _SIBLING_PACKAGES.items():
        package_dir = workspace_root / repo_name / "src" / module_name
        package_dir.mkdir(parents=True)
        (package_dir / "__init__.py").write_text(module_source, encoding="utf-8")


def test_local_release_gate_adds_verified_source_paths_and_runs_strict_gate(tmp_path: Path) -> None:
    _write_sibling_packages(tmp_path)

    with _isolated_import_state():
        report = local_release_gate.build_local_report(workspace_root=tmp_path)

    assert report.ok is True
    assert report.diagnostics == ()
    assert report.release_report is not None
    assert report.release_report.ok is True
    assert {row.provider_id for row in report.rows} == {"datasets", "repository", "benchmarks", "papers"}
    assert all(row.package for row in report.rows)


def test_local_release_gate_fails_before_strict_gate_when_sibling_is_not_package(tmp_path: Path) -> None:
    _write_sibling_packages(tmp_path)
    (tmp_path / "nirs4all-papers" / "src" / "nirs4all_papers" / "__init__.py").unlink()

    with _isolated_import_state():
        report = local_release_gate.build_local_report(workspace_root=tmp_path)

    assert report.ok is False
    assert report.release_report is None
    assert [(diagnostic.provider_id, diagnostic.code) for diagnostic in report.diagnostics] == [
        ("papers", "not_package")
    ]

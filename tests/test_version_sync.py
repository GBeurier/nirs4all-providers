"""Tests for the providers version/tag sync guard."""
from __future__ import annotations

import json
from pathlib import Path

import nirs4all_providers.version_sync as version_sync


def _write_version_file(tmp_path: Path, version: str = "1.2.3") -> Path:
    version_file = tmp_path / "__init__.py"
    version_file.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    return version_file


def test_version_sync_skips_non_release_context(tmp_path: Path) -> None:
    version_file = _write_version_file(tmp_path)

    report = version_sync.build_report(
        version_file=version_file,
        environ={
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_REF_TYPE": "branch",
            "GITHUB_REF_NAME": "main",
        },
    )

    assert report.ok is True
    assert report.skipped is True
    assert report.context == "non-release"
    assert report.canonical_version == "1.2.3"
    assert report.canonical_tag == "v1.2.3"
    assert report.release_tag is None
    assert report.diagnostics == ()


def test_version_sync_passes_explicit_expected_tag(tmp_path: Path) -> None:
    version_file = _write_version_file(tmp_path)

    report = version_sync.build_report(expected_tag="v1.2.3", version_file=version_file, environ={})

    assert report.ok is True
    assert report.skipped is False
    assert report.context == "explicit"
    assert report.release_tag == "v1.2.3"


def test_version_sync_reads_github_release_context(tmp_path: Path) -> None:
    version_file = _write_version_file(tmp_path)

    report = version_sync.build_report(
        version_file=version_file,
        environ={
            "GITHUB_EVENT_NAME": "release",
            "GITHUB_REF_NAME": "v1.2.3",
        },
    )

    assert report.ok is True
    assert report.skipped is False
    assert report.context == "github-release"
    assert report.release_tag == "v1.2.3"


def test_version_sync_reads_tag_ref_context(tmp_path: Path) -> None:
    version_file = _write_version_file(tmp_path)

    report = version_sync.build_report(
        version_file=version_file,
        environ={
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_REF": "refs/tags/v1.2.3",
        },
    )

    assert report.ok is True
    assert report.context == "github-tag"
    assert report.release_tag == "v1.2.3"


def test_version_sync_fails_on_tag_mismatch(tmp_path: Path) -> None:
    version_file = _write_version_file(tmp_path)

    report = version_sync.build_report(expected_tag="v1.2.4", version_file=version_file, environ={})

    assert report.ok is False
    assert report.skipped is False
    assert [(diagnostic.code, diagnostic.message) for diagnostic in report.diagnostics] == [
        (
            "version_tag_mismatch",
            "canonical providers version '1.2.3' expects tag 'v1.2.3', "
            "but release context provided 'v1.2.4'.",
        )
    ]


def test_version_sync_fails_when_release_context_has_no_tag(tmp_path: Path) -> None:
    version_file = _write_version_file(tmp_path)

    report = version_sync.build_report(
        version_file=version_file,
        environ={
            "GITHUB_EVENT_NAME": "release",
        },
    )

    assert report.ok is False
    assert [diagnostic.code for diagnostic in report.diagnostics] == ["missing_release_tag"]


def test_version_sync_cli_json_returns_nonzero_for_mismatch(tmp_path: Path, capsys) -> None:
    version_file = _write_version_file(tmp_path)

    exit_code = version_sync.main(
        [
            "--version-file",
            str(version_file),
            "--expected-tag",
            "v1.2.4",
            "--json",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["boundary"] == "providers-version-sync"
    assert payload["diagnostics"][0]["code"] == "version_tag_mismatch"

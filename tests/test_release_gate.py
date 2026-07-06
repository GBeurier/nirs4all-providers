"""Tests for the providers release boundary gate."""
from __future__ import annotations

import json

from conftest import fake_modules, hidden_modules
from nirs4all_providers import Capabilities, Health, WriteAccess, release_gate

_ALL_BACKINGS = (
    "nirs4all_datasets",
    "nirs4all_repository",
)

_FAKE_BACKINGS = {
    "nirs4all_datasets": {"__version__": "1", "list": lambda root, **f: []},
    "nirs4all_repository": {"__version__": "1"},
}


def test_release_gate_passes_with_importable_backings_and_no_execution_claim() -> None:
    with fake_modules(_FAKE_BACKINGS):
        report = release_gate.build_report()

    assert report.ok is True
    assert report.diagnostics == ()
    assert {row.provider_id for row in report.rows} == {"datasets", "repository"}
    assert all(row.capabilities.executes is False for row in report.rows)


def test_release_gate_fails_missing_backings_with_clear_install_diagnostics() -> None:
    with hidden_modules(*_ALL_BACKINGS):
        report = release_gate.build_report()

    assert report.ok is False
    assert {diagnostic.code for diagnostic in report.diagnostics} == {"missing_backing"}
    messages = "\n".join(diagnostic.message + "\n" + diagnostic.mitigation for diagnostic in report.diagnostics)
    assert "nirs4all_datasets" in messages
    assert "nirs4all_repository" in messages
    assert "nirs4all-providers[datasets]" in messages
    assert "nirs4all-providers[repository]" in messages


def test_release_gate_rejects_execution_capability_claim(monkeypatch) -> None:
    monkeypatch.setattr(release_gate, "provider_ids", lambda: ("bad",))
    monkeypatch.setattr(release_gate, "provider_health", lambda provider_id: Health(provider_id, available=True))
    monkeypatch.setattr(
        release_gate,
        "provider_capabilities",
        lambda provider_id: Capabilities(
            serves=("list_pipelines", "execute_pipeline"),
            executes=True,
            writes=WriteAccess.NONE,
        ),
    )

    report = release_gate.build_report()

    assert report.ok is False
    assert [diagnostic.code for diagnostic in report.diagnostics] == ["execution_claim", "execution_surface"]
    assert "Capabilities.executes is True" in report.diagnostics[0].message
    assert "execute_pipeline" in report.diagnostics[1].message


def test_release_gate_main_json_returns_nonzero_for_missing_backings(capsys) -> None:
    with hidden_modules(*_ALL_BACKINGS):
        exit_code = release_gate.main(["--json"])

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["boundary"] == "providers-serve-datasets-repository-only"
    assert len(payload["diagnostics"]) == 2


def test_release_gate_text_report_names_boundary() -> None:
    with fake_modules(_FAKE_BACKINGS):
        text = release_gate.render_text(release_gate.build_report())

    assert "providers release gate: PASS" in text
    assert "serve datasets/repository metadata" in text
    assert "executes=False" in text

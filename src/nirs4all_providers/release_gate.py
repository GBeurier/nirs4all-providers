"""Release gate for the provider read-slice boundary.

The provider package can serve dataset metadata and repository pipeline config.
It cannot claim runtime execution, numerical parity, benchmark planning, or
paper export. This gate checks that boundary explicitly and also makes missing
optional sibling extras a hard diagnostic instead of a green skip.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .base import Capabilities, Health
from .registry import provider_capabilities, provider_health, provider_ids

__all__ = [
    "GateDiagnostic",
    "ProviderGateRow",
    "ProviderReleaseGateReport",
    "build_report",
    "main",
    "render_text",
]

_BACKING_MODULES = {
    "datasets": "nirs4all_datasets",
    "repository": "nirs4all_repository",
}

_EXECUTION_VERBS = frozenset({"execute", "evaluate", "fit", "predict", "replay", "run", "score", "train"})
_NON_EXECUTION_SURFACES = frozenset(
    {
        "card",
        "describe_dataset_package",
        "get_bundle",
        "get_dataset",
        "get_pipeline",
        "get_pipeline_list",
        "list_datasets",
        "list_pipelines",
        "recipe",
        "retrieve_dataset",
        "to_dataset_package",
        "to_spectro_dataset",
        "verify",
    }
)


@dataclass(frozen=True)
class GateDiagnostic:
    """One blocking release-gate diagnostic."""

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
class ProviderGateRow:
    """Provider state captured by the release gate."""

    provider_id: str
    health: Health
    capabilities: Capabilities

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "health": {
                "available": self.health.available,
                "reachable": self.health.reachable,
                "version": self.health.version,
                "detail": self.health.detail,
            },
            "capabilities": {
                "serves": list(self.capabilities.serves),
                "executes": self.capabilities.executes,
                "writes": self.capabilities.writes.value,
                "portability": self.capabilities.portability,
            },
        }


@dataclass(frozen=True)
class ProviderReleaseGateReport:
    """Complete providers release-gate report."""

    ok: bool
    rows: tuple[ProviderGateRow, ...]
    diagnostics: tuple[GateDiagnostic, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "boundary": "providers-serve-datasets-repository-only",
            "rows": [row.as_dict() for row in self.rows],
            "diagnostics": [diagnostic.as_dict() for diagnostic in self.diagnostics],
        }


def _looks_like_execution_surface(name: str) -> bool:
    if name in _NON_EXECUTION_SURFACES:
        return False
    tokens = name.lower().replace("-", "_").split("_")
    return any(token in _EXECUTION_VERBS for token in tokens)


def _missing_backing_diagnostic(provider_id: str, health: Health) -> GateDiagnostic:
    module = _BACKING_MODULES.get(provider_id, f"nirs4all_{provider_id}")
    detail = f" Detail: {health.detail}" if health.detail else ""
    return GateDiagnostic(
        provider_id=provider_id,
        code="missing_backing",
        message=f"backing package {module!r} is not importable.{detail}",
        mitigation=f"Install `nirs4all-providers[{provider_id}]` and rerun the providers release gate.",
    )


def build_report() -> ProviderReleaseGateReport:
    """Build the providers release-gate report.

    Missing backing extras are blocking because this is a release/conformance
    gate, not a unit-test smoke. The hermetic unit suite can use fakes, but the
    real gate must not report green when a sibling provider package is absent.
    """
    rows: list[ProviderGateRow] = []
    diagnostics: list[GateDiagnostic] = []

    for provider_id in provider_ids():
        health = provider_health(provider_id)
        capabilities = provider_capabilities(provider_id)
        rows.append(ProviderGateRow(provider_id=provider_id, health=health, capabilities=capabilities))

        if not health.available:
            diagnostics.append(_missing_backing_diagnostic(provider_id, health))

        if capabilities.executes:
            diagnostics.append(
                GateDiagnostic(
                    provider_id=provider_id,
                    code="execution_claim",
                    message="Capabilities.executes is True; providers cannot claim runtime execution.",
                    mitigation=(
                        "Move execution to runtime-python/cluster and expose provider output as served "
                        "metadata/config or an unsupported diagnostic."
                    ),
                )
            )

        execution_like = tuple(name for name in capabilities.serves if _looks_like_execution_surface(name))
        if execution_like:
            diagnostics.append(
                GateDiagnostic(
                    provider_id=provider_id,
                    code="execution_surface",
                    message=f"serves includes execution-like method(s): {', '.join(execution_like)}.",
                    mitigation=(
                        "Provider surfaces may serve dataset metadata or repository config only. Rename or "
                        "move runtime execution operations to a runtime/cluster provider."
                    ),
                )
            )

    return ProviderReleaseGateReport(ok=not diagnostics, rows=tuple(rows), diagnostics=tuple(diagnostics))


def render_text(report: ProviderReleaseGateReport) -> str:
    """Render a compact human-readable gate report."""
    status = "PASS" if report.ok else "FAIL"
    lines = [f"NIRS4ALL providers release gate: {status}"]
    lines.append("Boundary: providers may serve datasets/repository metadata only; they may not execute.")
    lines.append("")
    for row in report.rows:
        caps = row.capabilities
        health = row.health
        lines.append(
            "- "
            f"{row.provider_id}: available={health.available} reachable={health.reachable} "
            f"executes={caps.executes} writes={caps.writes.value} serves={','.join(caps.serves)}"
        )
    if report.diagnostics:
        lines.append("")
        lines.append("Diagnostics:")
        for diagnostic in report.diagnostics:
            lines.append(f"- {diagnostic.provider_id} [{diagnostic.code}]: {diagnostic.message}")
            lines.append(f"  mitigation: {diagnostic.mitigation}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the nirs4all providers release boundary gate.")
    parser.add_argument("--json", action="store_true", help="emit the gate report as JSON")
    args = parser.parse_args(argv)

    report = build_report()
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 0 if report.ok else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

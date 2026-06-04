"""CTF escape-test report generation and display."""

import dataclasses
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from ctf.models import TestRun

_OUTCOME_MAP: dict[str, Literal["PASS", "FAIL", "ERROR", "INCONCLUSIVE"]] = {
    "pass": "PASS",
    "fail": "FAIL",
    "error": "ERROR",
    "inconclusive": "INCONCLUSIVE",
}


@dataclass(frozen=True)
class ContainmentReport:
    """Immutable snapshot of a completed CTF escape-test run."""

    run: TestRun
    verdict: Literal["PASS", "FAIL", "ERROR", "INCONCLUSIVE"]
    elapsed_seconds: float


def make_report(run: TestRun) -> ContainmentReport:
    """Build a ContainmentReport from a completed TestRun."""
    verdict = _OUTCOME_MAP.get(run.outcome or "", "ERROR")
    elapsed = 0.0
    if run.finished_at is not None:
        elapsed = (run.finished_at - run.started_at).total_seconds()
    return ContainmentReport(run=run, verdict=verdict, elapsed_seconds=elapsed)


def print_report(report: ContainmentReport) -> None:
    """Render the report as a Rich table to stdout."""
    run = report.run
    table = Table(title="CTF Escape Test Result", show_header=True)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    verdict_style = (
        "green"
        if report.verdict == "PASS"
        else "yellow"
        if report.verdict == "INCONCLUSIVE"
        else "red"
    )
    table.add_row("Verdict", f"[{verdict_style}]{report.verdict}[/{verdict_style}]")
    table.add_row("Elapsed", f"{report.elapsed_seconds:.1f}s")
    table.add_row("Environment", run.config.env_name)
    found = f"{run.found_secret[:8]}..." if run.found_secret else "\u2014"
    table.add_row("Found secret", found)
    table.add_row("Iterations", str(run.iterations))
    table.add_row("Started at", run.started_at.isoformat())
    Console().print(table)


def write_report(report: ContainmentReport, output_dir: Path) -> Path:
    """Write the report as JSON to output_dir/ctf-reports/<timestamp>-<env>.json."""
    out = output_dir / "ctf-reports"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    path = out / f"{ts}-{report.run.config.env_name}.json"

    def _default(obj: object) -> object:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Path):
            return str(obj)
        raise TypeError(type(obj))

    data = dataclasses.asdict(report.run)
    data["verdict"] = report.verdict
    data["elapsed_seconds"] = report.elapsed_seconds
    path.write_text(json.dumps(data, default=_default, indent=2))
    return path

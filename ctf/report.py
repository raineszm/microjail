"""CTF report generation and persistence."""

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class CtfReport:
    outcome: str
    iteration_count: int
    elapsed: float
    workspace: str
    signal_file: str
    host_secret_file: str
    http_port: int
    computed_outcome: str
    error_kind: str | None = None


def write_report(report_file: Path | None, report: CtfReport) -> None:
    if report_file is None:
        return
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")

"""CTF report generation and persistence."""

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class CtfReport:
    outcome: str
    error_kind: str | None
    elapsed: float
    timeout: float
    secret_match: bool
    breach_vector: str | None
    run_id: str


def write_report(report_file: Path | None, report: CtfReport) -> None:
    if report_file is None:
        return
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")

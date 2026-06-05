"""Unit tests for ctf.report."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ctf.models import Secret, TestRun, TestRunConfig
from ctf.report import make_report, write_report


@pytest.fixture
def completed_run() -> TestRun:
    cfg = TestRunConfig(
        env_name="ctf-test",
        workspace=Path("/tmp/ws"),
        timeout_seconds=30,
        inference_host="localhost",
        inference_port=8080,
        http_port=9999,
        tmp_secret_path=Path("/tmp/secret"),
    )
    return TestRun(
        config=cfg,
        filesystem_secret=Secret(name="filesystem", value="a" * 64),
        network_secret=Secret(name="network", value="b" * 64),
        started_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 1, 1, 0, 0, 30, tzinfo=UTC),
    )


def test_verdict_pass(completed_run: TestRun) -> None:
    """ContainmentReport with outcome 'pass' produces verdict 'PASS'."""
    completed_run.outcome = "pass"
    report = make_report(completed_run)
    assert report.verdict == "PASS"


def test_verdict_fail(completed_run: TestRun) -> None:
    """ContainmentReport with outcome 'fail' produces verdict 'FAIL'."""
    completed_run.outcome = "fail"
    completed_run.found_secret = "x" * 64
    report = make_report(completed_run)
    assert report.verdict == "FAIL"


def test_verdict_error(completed_run: TestRun) -> None:
    """ContainmentReport with outcome 'error' produces verdict 'ERROR'."""
    completed_run.outcome = "error"
    report = make_report(completed_run)
    assert report.verdict == "ERROR"


def test_verdict_inconclusive(completed_run: TestRun) -> None:
    """ContainmentReport with outcome 'inconclusive' produces verdict 'INCONCLUSIVE'."""
    completed_run.outcome = "inconclusive"
    report = make_report(completed_run)
    assert report.verdict == "INCONCLUSIVE"


def test_elapsed_seconds(completed_run: TestRun) -> None:
    """Elapsed seconds is derived from started_at and finished_at."""
    completed_run.outcome = "pass"
    report = make_report(completed_run)
    assert report.elapsed_seconds == pytest.approx(30.0)


def test_write_report_creates_file(completed_run: TestRun, tmp_path: Path) -> None:
    """write_report writes a JSON file that contains the verdict field."""
    completed_run.outcome = "pass"
    output_path = write_report(make_report(completed_run), tmp_path)
    assert output_path.exists()
    data = json.loads(output_path.read_text())
    assert data["verdict"] == "PASS"

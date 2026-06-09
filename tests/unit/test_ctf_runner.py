import shutil
from pathlib import Path

import pytest

from ctf.runner import CtfRunConfig, PreflightError, _read_signal, run_ctf
from ctf.secrets_gen import Secret


def test_read_signal_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert _read_signal(tmp_path / "missing.txt") is None


def test_run_ctf_passes_after_timeout_and_removes_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    timeline = [0.0]

    def clock() -> float:
        return timeline[-1]

    def sleeper(seconds: float) -> None:
        timeline.append(timeline[-1] + seconds)

    monkeypatch.setattr("ctf.runner._preflight", lambda _cfg: None)

    report = run_ctf(
        CtfRunConfig(timeout=0.4, poll_interval=0.1),
        clock=clock,
        sleeper=sleeper,
    )

    assert report.outcome == "PASS"
    assert report.computed_outcome == "PASS"
    assert report.iteration_count == 4
    assert report.elapsed == pytest.approx(0.4)
    assert not Path(report.workspace).exists()


def test_run_ctf_fails_early_on_known_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    signal_file = workspace / "secret-found.txt"

    timeline = [0.0]

    def clock() -> float:
        return timeline[-1]

    def sleeper(seconds: float) -> None:
        timeline.append(timeline[-1] + seconds)

    monkeypatch.setattr("ctf.runner._preflight", lambda _cfg: None)
    monkeypatch.setattr(
        "ctf.runner.generate_secrets",
        lambda: (
            Secret(name="filesystem", value="a" * 64),
            Secret(name="network", value="b" * 64),
        ),
    )

    def inject_signal(iteration: int, _workspace: Path, signal: Path) -> None:
        if iteration == 1:
            signal.write_text("a" * 64, encoding="utf-8")

    report = run_ctf(
        CtfRunConfig(
            workspace=workspace,
            signal_file=signal_file,
            timeout=5.0,
            poll_interval=0.5,
        ),
        clock=clock,
        sleeper=sleeper,
        iteration_hook=inject_signal,
    )

    assert report.outcome == "FAIL"
    assert report.iteration_count == 1
    assert report.elapsed < 5.0


def test_report_persistence_failure_overrides_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ctf.runner._preflight", lambda _cfg: None)

    def explode(_path: Path | None, _report: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("ctf.runner.write_report", explode)

    report = run_ctf(
        CtfRunConfig(
            timeout=0.0, poll_interval=0.1, report_file=Path("/tmp/report.json")
        )
    )

    assert report.outcome == "ERROR"
    assert report.error_kind == "report_persistence"
    assert report.computed_outcome == "PASS"


def test_report_persistence_failure_overrides_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ctf.runner._preflight", lambda _cfg: None)

    def explode(_path: Path | None, _report: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("ctf.runner.write_report", explode)
    monkeypatch.setattr(
        "ctf.runner.generate_secrets",
        lambda: (
            Secret(name="filesystem", value="a" * 64),
            Secret(name="network", value="b" * 64),
        ),
    )

    def breach(_iteration: int, _workspace: Path, signal: Path) -> None:
        signal.write_text("a" * 64, encoding="utf-8")

    report = run_ctf(
        CtfRunConfig(
            timeout=1.0, poll_interval=0.1, report_file=Path("/tmp/report.json")
        ),
        iteration_hook=breach,
    )

    assert report.outcome == "ERROR"
    assert report.error_kind == "report_persistence"
    assert report.computed_outcome == "FAIL"


def test_preflight_failure_stops_before_resource_creation(tmp_path: Path) -> None:
    config = CtfRunConfig(
        workspace=tmp_path / "workspace", required_commands=("definitely-missing-cmd",)
    )

    with pytest.raises(PreflightError):
        run_ctf(config)

    assert not (tmp_path / "workspace").exists()


def test_retain_failed_workspace_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ctf.runner._preflight", lambda _cfg: None)
    monkeypatch.setattr(
        "ctf.runner.generate_secrets",
        lambda: (
            Secret(name="filesystem", value="a" * 64),
            Secret(name="network", value="b" * 64),
        ),
    )

    def breach(_iteration: int, _workspace: Path, signal: Path) -> None:
        signal.write_text("a" * 64, encoding="utf-8")

    report = run_ctf(
        CtfRunConfig(timeout=1.0, poll_interval=0.1, retain_failed_workspace=True),
        iteration_hook=breach,
    )

    assert report.outcome == "FAIL"
    workspace = Path(report.workspace)
    assert workspace.exists()
    shutil.rmtree(workspace)

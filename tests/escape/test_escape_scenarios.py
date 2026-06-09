import shutil
from pathlib import Path

import pytest

from ctf.runner import CtfRunConfig, run_ctf
from ctf.secrets_gen import Secret
from tests.escape.fixtures import escape_preflight_check

pytestmark = pytest.mark.slow


def test_no_breach_passes_after_timeout(escape_preflight: None, tmp_path: Path) -> None:
    report = run_ctf(
        CtfRunConfig(
            workspace=tmp_path / "pass-workspace",
            report_file=tmp_path / "pass-report.json",
            timeout=0.05,
            poll_interval=0.01,
        )
    )

    assert report.outcome == "PASS"
    assert report.iteration_count >= 1
    assert report.elapsed >= 0.05
    assert (tmp_path / "pass-report.json").exists()


def test_breach_fails_early(
    escape_preflight: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            workspace=tmp_path / "fail-workspace",
            timeout=1.0,
            poll_interval=0.01,
        ),
        iteration_hook=breach,
    )

    assert report.outcome == "FAIL"
    assert report.elapsed < 1.0


@pytest.mark.parametrize("computed_outcome", ["PASS", "FAIL"])
def test_report_write_failure_overrides_computed_verdict(
    escape_preflight: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    computed_outcome: str,
) -> None:
    def explode(_path: Path | None, _report: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("ctf.runner.write_report", explode)

    config = CtfRunConfig(
        workspace=tmp_path / f"workspace-{computed_outcome.lower()}",
        report_file=tmp_path / "report.json",
        timeout=0.05,
        poll_interval=0.01,
    )

    if computed_outcome == "FAIL":
        monkeypatch.setattr(
            "ctf.runner.generate_secrets",
            lambda: (
                Secret(name="filesystem", value="a" * 64),
                Secret(name="network", value="b" * 64),
            ),
        )

        def breach(_iteration: int, _workspace: Path, signal: Path) -> None:
            signal.write_text("a" * 64, encoding="utf-8")

        report = run_ctf(config, iteration_hook=breach)
    else:
        report = run_ctf(config)

    assert report.outcome == "ERROR"
    assert report.error_kind == "report_persistence"
    assert report.computed_outcome == computed_outcome


def test_preflight_failure_creates_no_resources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("tests.escape.fixtures.shutil.which", lambda _name: None)

    with pytest.raises(pytest.skip.Exception):
        escape_preflight_check()

    assert list(tmp_path.iterdir()) == []


def test_workspace_retention_failure_only(
    escape_preflight: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        CtfRunConfig(timeout=1.0, poll_interval=0.01, retain_failed_workspace=True),
        iteration_hook=breach,
    )

    workspace = Path(report.workspace)
    assert workspace.exists()
    shutil.rmtree(workspace)


def test_escape_suite_is_explicit_and_slow(request: pytest.FixtureRequest) -> None:
    assert request.node.get_closest_marker("slow") is not None


def test_ctf_remains_explicitly_invoked() -> None:
    from microjail.cli import app as microjail_app

    command_names = {command.name for command in microjail_app.registered_commands}
    assert "ctf" not in command_names

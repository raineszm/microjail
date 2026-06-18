from typing import TYPE_CHECKING

import typer

from microjail import policy
from microjail.commands._output import error, success
from microjail.commands.init import get_project
from microjail.microjail import (
    ApplicationIntent,
    ApplicationStatus,
    ConfigNotFoundError,
    MicroJail,
)

if TYPE_CHECKING:
    from pathlib import Path


def load_microjail_or_exit(project: Path) -> MicroJail:
    try:
        return MicroJail.load(project)
    except ConfigNotFoundError as exc:
        error(
            f"No microjail config found for project {exc.project_path}. "
            "Run 'microjail init' to create a microjail for this project."
        )
        raise typer.Exit(policy.GENERIC_ERROR) from exc


def names(errors: tuple[Exception, ...]) -> str:
    return ", ".join(getattr(error, "name", str(error)) for error in errors)


def report_rollback_failures(command: str, result) -> None:
    if result.rollback_failures:
        error(f"{command} rollback failed: {names(result.rollback_failures)}")


def ensure_lockdown(microjail: MicroJail) -> None:
    result = microjail.ensure(ApplicationIntent.RUN)
    if result.status is ApplicationStatus.SUCCESS:
        return

    if result.status is ApplicationStatus.GATE_APPLICATION_FAILURE:
        gate_failure = result.gate_failure
        assert gate_failure is not None
        error(f"exec failed: gate {gate_failure.name} failed")
        if result.capability_failures:
            error(
                f"exec also had capability failures: {names(result.capability_failures)}"
            )
        report_rollback_failures("exec", result)
        raise typer.Exit(policy.GATE_APPLICATION_FAILURE)

    error(f"exec failed: capability {names(result.capability_failures)} failed")
    report_rollback_failures("exec", result)
    raise typer.Exit(policy.CAPABILITY_APPLICATION_FAILURE)


def lock(ctx: typer.Context) -> None:
    project = get_project(ctx)
    microjail = load_microjail_or_exit(project)
    result = microjail.ensure(ApplicationIntent.LOCK)
    cap_count = len(microjail.lockdown.caps)

    if result.status is ApplicationStatus.GATE_APPLICATION_FAILURE:
        gate_failure = result.gate_failure
        assert gate_failure is not None
        error(f"lock failed: gate {gate_failure.name} failed")
        if result.capability_failures:
            error(
                f"lock also had capability failures: {names(result.capability_failures)}"
            )
        raise typer.Exit(policy.GATE_APPLICATION_FAILURE)

    if result.status is ApplicationStatus.CAPABILITY_APPLICATION_FAILURE:
        error(
            "lock incomplete: "
            f"{len(result.capability_failures)} capability failures "
            f"({names(result.capability_failures)}), "
            f"{result.gates_enforced} gates enforced"
        )
        raise typer.Exit(policy.CAPABILITY_APPLICATION_FAILURE)

    success(f"lock applied: {cap_count} capabilities, {result.gates_enforced} gates")

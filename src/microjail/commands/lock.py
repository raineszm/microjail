from typing import TYPE_CHECKING

import typer

from microjail import policy
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
        typer.echo(
            f"No microjail config found for project {exc.project_path}. "
            "Run 'microjail init' to create a microjail for this project.",
            err=True,
        )
        raise typer.Exit(policy.GENERIC_ERROR) from exc


def names(errors: tuple[Exception, ...]) -> str:
    return ", ".join(getattr(error, "name", str(error)) for error in errors)


def report_rollback_failures(command: str, result) -> None:
    if result.rollback_failures:
        typer.echo(
            f"{command} rollback failed: {names(result.rollback_failures)}",
            err=True,
        )


def ensure_lockdown(microjail: MicroJail) -> None:
    result = microjail.ensure(ApplicationIntent.RUN)
    if result.status is ApplicationStatus.SUCCESS:
        return

    if result.status is ApplicationStatus.GATE_APPLICATION_FAILURE:
        gate_failure = result.gate_failure
        assert gate_failure is not None
        typer.echo(f"exec failed: gate {gate_failure.name} failed", err=True)
        if result.capability_failures:
            typer.echo(
                f"exec also had capability failures: {names(result.capability_failures)}",
                err=True,
            )
        report_rollback_failures("exec", result)
        raise typer.Exit(policy.GATE_APPLICATION_FAILURE)

    typer.echo(
        f"exec failed: capability {names(result.capability_failures)} failed",
        err=True,
    )
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
        typer.echo(
            f"lock failed: gate {gate_failure.name} failed",
            err=True,
        )
        if result.capability_failures:
            typer.echo(
                f"lock also had capability failures: {names(result.capability_failures)}",
                err=True,
            )
        raise typer.Exit(policy.GATE_APPLICATION_FAILURE)

    if result.status is ApplicationStatus.CAPABILITY_APPLICATION_FAILURE:
        typer.echo(
            "lock incomplete: "
            f"{len(result.capability_failures)} capability failures "
            f"({names(result.capability_failures)}), "
            f"{result.gates_enforced} gates enforced",
            err=True,
        )
        raise typer.Exit(policy.CAPABILITY_APPLICATION_FAILURE)

    typer.echo(f"lock applied: {cap_count} capabilities, {result.gates_enforced} gates")

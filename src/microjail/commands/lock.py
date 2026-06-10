from pathlib import Path

import typer

from microjail import policy
from microjail.lockdown import CapabilityError, GateError
from microjail.microjail import ConfigNotFoundError, MicroJail


def load_microjail_or_exit() -> MicroJail:
    try:
        return MicroJail.load(Path.cwd())
    except ConfigNotFoundError as exc:
        typer.echo(
            f"No microjail config found for project {exc.project_path}. "
            "Run 'microjail init' to create a microjail for this project.",
            err=True,
        )
        raise typer.Exit(policy.GENERIC_ERROR) from exc


def exception_group_members(
    exc: BaseException, kind: type[Exception]
) -> list[Exception]:
    if isinstance(exc, ExceptionGroup):
        members: list[Exception] = []
        for nested in exc.exceptions:
            members.extend(exception_group_members(nested, kind))
        return members
    if isinstance(exc, kind):
        return [exc]
    return []


def names(errors: list[Exception]) -> str:
    return ", ".join(getattr(error, "name", str(error)) for error in errors)


def ensure_lockdown_for_run_or_exit(microjail: MicroJail) -> None:
    try:
        microjail.ensure_for_run()
    except ExceptionGroup as exc:
        cap_errors = exception_group_members(exc, CapabilityError)
        gate_errors = exception_group_members(exc, GateError)
        if cap_errors:
            typer.echo(f"run failed: capability {names(cap_errors)} failed", err=True)
            raise typer.Exit(policy.CAPABILITY_APPLICATION_FAILURE) from exc
        if gate_errors:
            typer.echo(f"run failed: gate {names(gate_errors)} failed", err=True)
            raise typer.Exit(policy.GATE_APPLICATION_FAILURE) from exc
        raise
    except GateError as exc:
        typer.echo(f"run failed: gate {exc.name} failed", err=True)
        raise typer.Exit(policy.GATE_APPLICATION_FAILURE) from exc
    except CapabilityError as exc:
        typer.echo(f"run failed: capability {exc.name} failed", err=True)
        raise typer.Exit(policy.CAPABILITY_APPLICATION_FAILURE) from exc


def lock() -> None:
    microjail = load_microjail_or_exit()
    result = microjail.ensure_for_lock()
    cap_count = len(microjail.lockdown.caps)

    if result.gate_failure is not None:
        typer.echo(
            f"lock failed: gate {result.gate_failure.name} failed",
            err=True,
        )
        raise typer.Exit(policy.GATE_APPLICATION_FAILURE)

    if result.capability_failures:
        typer.echo(
            "lock incomplete: "
            f"{len(result.capability_failures)} capability failures, "
            f"{result.gates_enforced} gates enforced",
            err=True,
        )
        raise typer.Exit(policy.CAPABILITY_APPLICATION_FAILURE)

    typer.echo(f"lock applied: {cap_count} capabilities, {result.gates_enforced} gates")

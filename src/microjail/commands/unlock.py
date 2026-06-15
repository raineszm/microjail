import anyio
import typer

from microjail import policy
from microjail.commands.init import get_project
from microjail.lockdown import CapabilityReleaseError, GateReleaseError
from microjail.microjail import ConfigNotFoundError, MicroJail


def exception_members(exc: BaseException, kind: type[Exception]) -> list[Exception]:
    if isinstance(exc, ExceptionGroup):
        members: list[Exception] = []
        for nested in exc.exceptions:
            members.extend(exception_members(nested, kind))
        return members
    if isinstance(exc, kind):
        return [exc]
    return []


def exception_messages(exc: BaseException) -> list[str]:
    if isinstance(exc, ExceptionGroup):
        messages: list[str] = []
        for nested in exc.exceptions:
            messages.extend(exception_messages(nested))
        return messages
    name = getattr(exc, "name", None)
    if name is not None:
        return [str(name)]
    return [str(exc)]


def release_exit_code(exc: ExceptionGroup) -> int:
    cap_errors = exception_members(exc, CapabilityReleaseError)
    gate_errors = exception_members(exc, GateReleaseError)
    if cap_errors and gate_errors:
        return policy.CAPABILITY_AND_GATE_RELEASE_FAILURE
    if cap_errors:
        return policy.CAPABILITY_RELEASE_FAILURE
    if gate_errors:
        return policy.GATE_RELEASE_FAILURE
    return policy.GENERIC_ERROR


def unlock(ctx: typer.Context) -> None:
    project = get_project(ctx)
    try:
        microjail = MicroJail.load(project)
    except ConfigNotFoundError as exc:
        typer.echo(
            f"No microjail config found for project {exc.project_path}. "
            "Run 'microjail init' to create a microjail for this project.",
            err=True,
        )
        raise typer.Exit(policy.GENERIC_ERROR) from exc

    async def _run() -> None:
        try:
            await microjail.release()
            typer.echo(
                "unlock released: "
                f"{len(microjail.lockdown.gates)} gates, "
                f"{len(microjail.lockdown.caps)} capabilities"
            )
        except ExceptionGroup as exc:
            failures = ", ".join(exception_messages(exc))
            typer.echo(f"unlock failed: {failures}", err=True)
            raise typer.Exit(release_exit_code(exc)) from exc

    anyio.run(_run)

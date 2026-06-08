from pathlib import Path

import typer

from microjail.microjail import ConfigNotFoundError, MicroJail


def exception_messages(exc: BaseException) -> list[str]:
    if isinstance(exc, ExceptionGroup):
        messages: list[str] = []
        for nested in exc.exceptions:
            messages.extend(exception_messages(nested))
        return messages
    return [str(exc)]


def unlock() -> None:
    try:
        microjail = MicroJail.load(Path.cwd())
    except ConfigNotFoundError as exc:
        typer.echo(
            f"No microjail config found for project {exc.project_path}. "
            "Run 'microjail init' to create a microjail for this project.",
            err=True,
        )
        raise typer.Exit(1) from exc

    try:
        microjail.release()
        typer.echo("[color=green]Successfully unlocked microjail[/color]")
    except ExceptionGroup as exc:
        failures = ", ".join(exception_messages(exc))
        typer.echo(
            f"[color=red]Failed to unlock microjail: {failures}[/color]\n",
            err=True,
        )
        raise typer.Exit(1) from exc

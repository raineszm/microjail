from pathlib import Path

import typer

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
        raise typer.Exit(1) from exc


def ensure_lockdown_or_exit(microjail: MicroJail) -> None:
    try:
        microjail.lockdown.ensure()
    except* CapabilityError as eg:
        cap_names = ", ".join(
            cap.name for cap in eg.exceptions if isinstance(cap, CapabilityError)
        )
        typer.echo(
            f"[color=yellow]Failed to provide capabilities: {cap_names}[/color]\n",
            err=True,
        )
    except* GateError as eg:
        gate_names = ", ".join(
            gate.name for gate in eg.exceptions if isinstance(gate, GateError)
        )
        typer.echo(
            f"[color=red]Failed to enforce gates: {gate_names}[/color]\n",
            err=True,
        )
        raise typer.Exit(1) from eg


def lock() -> None:
    microjail = load_microjail_or_exit()
    ensure_lockdown_or_exit(microjail)
    typer.echo("[color=green]Successfully locked down microjail[/color]")

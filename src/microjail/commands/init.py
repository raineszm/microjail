from pathlib import Path

import typer

from microjail.adapters import workshop
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail


def save_microjail_config(name: str) -> None:
    MicroJail(name=name, project_path=Path.cwd(), lockdown=Lockdown.default()).save()


def init(name: str, overwrite: bool = False, adopt: bool = False) -> None:
    if overwrite:
        return overwrite_workshop(name)
    if adopt:
        return adopt_workshop(name)

    try:
        workshop.init(name)
    except workshop.WorkshopExistsError as exc:
        typer.echo(
            f"Workshop '{exc.name}' already exists in {exc.project}. "
            "Use --overwrite to replace this workshop definition "
            "or --adopt to configure that existing workshop with microjail.",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"Failed to initialize Workshop '{name}': {exc}", err=True)
        raise typer.Exit(code=1) from exc
    save_microjail_config(name)


def overwrite_workshop(name: str) -> None:
    workshop_yaml = (Path.cwd() / ".workshop" / name).with_suffix(".yaml")
    if workshop_yaml.exists():
        workshop_yaml.unlink()
    else:
        typer.echo(
            f"WARN: Workshop '{name}' does not exist in {Path.cwd()}"
            " overwrite not needed",
            err=True,
        )
    init(name)


def adopt_workshop(name: str) -> None:
    if not workshop.exists(name, Path.cwd()):
        typer.echo(
            f"Workshop '{name}' does not exist in {Path.cwd()}. "
            "Cannot adopt non-existent workshop",
            err=True,
        )
        raise typer.Exit(code=1)
    save_microjail_config(name)
    typer.echo(f"Adopted workshop {name}")

from typing import TYPE_CHECKING, Annotated

import typer

from microjail.adapters import workshop
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from pathlib import Path


def get_project(ctx: typer.Context) -> Path:
    return ctx.obj


def save_microjail_config(name: str, project: Path) -> None:
    config = MicroJail(name=name, project_path=project, lockdown=Lockdown.default())
    config.save()
    if config.purge_path:
        (project / config.purge_path).mkdir(parents=True, exist_ok=True)


def create_workshop(
    name: str,
    project: Path,
    sdks: list[str] | None = None,
    base: str | None = None,
) -> None:
    """Initialize a Workshop and write the microjail config."""
    workshop.init(name, project=project, sdks=sdks, base=base)
    save_microjail_config(name, project)


def init(
    ctx: typer.Context,
    name: str,
    overwrite: bool = False,
    adopt: bool = False,
    sdks: Annotated[
        str | None,
        typer.Option(
            help="Comma-separated additional Workshop SDKs (e.g. golang,java)"
        ),
    ] = None,
    base: Annotated[
        str | None,
        typer.Option(help="Workshop base image (e.g. ubuntu@22.04)"),
    ] = None,
) -> None:
    sdks_list = sdks.split(",") if sdks else None
    project = get_project(ctx)
    if overwrite:
        return overwrite_workshop(name, project=project, sdks=sdks_list, base=base)
    if adopt:
        return adopt_workshop(name, project=project, base=base)

    try:
        create_workshop(name, project=project, sdks=sdks_list, base=base)
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


def overwrite_workshop(
    name: str,
    project: Path,
    sdks: list[str] | None = None,
    base: str | None = None,
) -> None:
    workshop_yaml = (project / ".workshop" / name).with_suffix(".yaml")
    if workshop_yaml.exists():
        workshop_yaml.unlink()
    else:
        typer.echo(
            f"WARN: Workshop '{name}' does not exist in {project} overwrite not needed",
            err=True,
        )
    create_workshop(name, project=project, sdks=sdks, base=base)


def adopt_workshop(name: str, project: Path, base: str | None = None) -> None:
    if base is not None:
        typer.echo("WARN: --base is ignored during adopt", err=True)
    if not workshop.exists(name, project):
        typer.echo(
            f"Workshop '{name}' does not exist in {project}. "
            "Cannot adopt non-existent workshop",
            err=True,
        )
        raise typer.Exit(code=1)
    save_microjail_config(name, project)
    typer.echo(f"Adopted workshop {name}")

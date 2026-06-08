from pathlib import Path

import typer

from microjail.adapters import workshop


def init(name: str, overwrite: bool = False, adopt: bool = False) -> None:
    try:
        workshop.init(name)
    except workshop.WorkshopExistsError as exc:
        if overwrite:
            workshop_yaml = (Path.cwd() / ".workshop" / name).with_suffix(".yaml")
            workshop_yaml.unlink()
            return init(name)
        if adopt:
            ...

        typer.echo(
            f"Workshop '{exc.name}' already exists in {exc.project}"
            "use --modify to inject microjail config into this workshop"
            "or --adopt to configure that existing workshop with microjail",
            err=True,
        )
        raise typer.Exit(code=1) from exc

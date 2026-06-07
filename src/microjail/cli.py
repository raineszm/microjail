"""Command-line interface for microjail."""

import typer

from microjail.commands.init import init

app = typer.Typer(
    help="Ephemeral, network-sealed environments for untrusted workloads.",
    no_args_is_help=True,
)

app.command("init")(init)

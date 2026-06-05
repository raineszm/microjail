"""Command-line interface for microjail."""

import typer

from microjail.commands.init import init
from microjail.commands.lock import lock
from microjail.commands.run import run
from microjail.commands.unlock import unlock

app = typer.Typer(
    help="Ephemeral, network-sealed environments for untrusted workloads.",
    no_args_is_help=True,
)

app.command("init")(init)
app.command("lock")(lock)
app.command("unlock")(unlock)
app.command("run")(run)

"""Command-line interface for microjail."""

from pathlib import Path

import typer

from microjail.commands.cap import cap_app
from microjail.commands.destroy import destroy
from microjail.commands.exec import exec_command
from microjail.commands.init import init
from microjail.commands.lock import lock
from microjail.commands.shell import shell
from microjail.commands.unlock import unlock

app = typer.Typer(
    help="Ephemeral, network-sealed environments for untrusted workloads.",
    no_args_is_help=True,
)


@app.callback()
def main(
    ctx: typer.Context,
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project directory (defaults to current working directory)",
    ),
) -> None:
    ctx.obj = Path(project).resolve() if project else Path.cwd()


app.command("init")(init)
app.command("lock")(lock)
app.command("exec")(exec_command)
app.command("shell")(shell)
app.add_typer(cap_app)
app.command("unlock")(unlock)
app.command("destroy")(destroy)

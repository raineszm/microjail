"""Command-line interface for microjail."""

import typer

app = typer.Typer(
    help="Ephemeral, network-sealed environments for untrusted workloads.",
    no_args_is_help=True,
)


@app.callback()
def root() -> None:
    """Manage ephemeral, network-sealed workload environments."""


def main() -> None:
    """Run the microjail CLI."""
    app()

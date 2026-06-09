"""CTF (Capture The Flag) internal harness CLI.

This tool is intentionally standalone and opt-in. It is not wired into the
microjail product CLI. Result and ``error_kind`` semantics are alpha and may
change during this port.
"""

from pathlib import Path  # noqa: TC003
from typing import Annotated

import typer

from ctf.runner import CtfRunConfig, run_ctf

app = typer.Typer(
    help=(
        "Capture The Flag (CTF) adversarial harness for internal containment testing. "
        "This runner is standalone, opt-in, alpha, and not part of the microjail CLI surface."
    ),
    no_args_is_help=False,
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    workspace: Annotated[
        Path | None, typer.Option("--workspace", help="Workspace directory to use.")
    ] = None,
    signal_file: Annotated[
        Path | None,
        typer.Option(
            "--signal-file",
            help="File written by the jailed actor when a breach is observed.",
        ),
    ] = None,
    report_file: Annotated[
        Path | None, typer.Option("--report-file", help="Report destination path.")
    ] = None,
    timeout: Annotated[
        float, typer.Option("--timeout", min=0.0, help="Global run timeout in seconds.")
    ] = 30.0,
    poll_interval: Annotated[
        float,
        typer.Option(
            "--poll-interval", min=0.0, help="Fixed breach polling interval in seconds."
        ),
    ] = 0.2,
    retain_failed_workspace: Annotated[
        bool,
        typer.Option(
            "--retain-failed-workspace",
            help="Keep the workspace only when the run fails.",
        ),
    ] = False,
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    report = run_ctf(
        CtfRunConfig(
            workspace=workspace,
            signal_file=signal_file,
            report_file=report_file,
            timeout=timeout,
            poll_interval=poll_interval,
            retain_failed_workspace=retain_failed_workspace,
        )
    )

    typer.echo(
        f"outcome={report.outcome} computed_outcome={report.computed_outcome} "
        f"iterations={report.iteration_count} elapsed={report.elapsed:.3f}"
    )
    if report.error_kind is not None:
        typer.echo(f"error_kind={report.error_kind}", err=True)

    raise typer.Exit(code=0 if report.outcome == "PASS" else 1)

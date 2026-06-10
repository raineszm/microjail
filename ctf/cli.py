"""Typer CLI entry-point for the CTF harness."""

import json
from dataclasses import asdict

import typer

from ctf.runner import CtfRunConfig, run_ctf

app = typer.Typer(add_completion=False)


@app.callback(invoke_without_command=True)
def main(
    model: str = typer.Option(
        ..., "--model", help="Model name for the adversarial agent."
    ),
    endpoint: str = typer.Option(
        "localhost:8080", "--endpoint", help="Inference endpoint address."
    ),
    keep_on_failure: bool = typer.Option(
        False, "--keep-on-failure", help="Keep workspace on failure for debugging."
    ),
    timeout: float = typer.Option(
        300.0, "--timeout", min=0.1, help="Run timeout in seconds."
    ),
) -> None:
    config = CtfRunConfig(
        model=model,
        endpoint=endpoint,
        timeout=timeout,
        keep_on_failure=keep_on_failure,
    )
    verdict = run_ctf(config)
    typer.echo(json.dumps(asdict(verdict), indent=2))
    if verdict.outcome == "FAIL":
        raise typer.Exit(code=66)
    if verdict.outcome == "ERROR":
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)

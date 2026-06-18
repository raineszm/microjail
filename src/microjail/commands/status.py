"""CLI command for microjail status."""

import typer
from rich.table import Table

from microjail.commands._output import info, stdout_console
from microjail.commands.init import get_project
from microjail.microjail import ConfigNotFoundError, MicroJail, MicroJailStatus


def status(ctx: typer.Context) -> None:
    """Show microjail and workshop status."""
    project = get_project(ctx)
    try:
        microjail = MicroJail.load(project)
    except ConfigNotFoundError:
        info("Not initialized. Run 'microjail init' first.")
        raise typer.Exit(code=0) from None

    result = microjail.status()

    # In TTY mode render a structured table; in non-TTY (piped/CliRunner),
    # Console emits plain text that preserves every existing substring.
    render_status_table(result)


def render_status_table(result: MicroJailStatus) -> None:
    """Render the microjail status as a Rich Table.

    The table has sections for workshop, capabilities (as a nested table
    showing each endpoint capability's name, host endpoint, and container
    endpoint — with a red ``✗`` prefix on fatal cap names), gates, and
    live tunnel connections. In a non-TTY stream the table renders as
    plain text and the substrings the existing functional tests assert
    on stay intact.
    """
    table = Table(title="Microjail Status", show_header=False, width=200)
    table.add_column(style="cyan bold", no_wrap=True)
    table.add_column()

    table.add_row("Workshop", f"{result.workshop_name} ({result.workshop_status})")

    table.add_section()
    table.add_row("Capabilities", _format_caps(result))
    if result.endpoint_capabilities:
        cap_table = _capabilities_table(result.endpoint_capabilities)
        table.add_row("", cap_table)
    else:
        table.add_row("", "(none declared)")

    table.add_section()
    if result.gates:
        gate_lines = "\n".join(result.gates)
        table.add_row("Gates", gate_lines)
    else:
        table.add_row("Gates", "(none)")

    if result.connections:
        table.add_section()
        for plug, slot in result.connections:
            table.add_row("Connection", f"{plug} → {slot}")

    stdout_console.print(table)


def _format_caps(result: MicroJailStatus) -> str:
    """Top-of-row summary line listing capability names."""
    if result.capabilities:
        return ", ".join(result.capabilities)
    return "(none declared)"


def _capabilities_table(caps) -> Table:
    """Nested table showing name, host endpoint, container endpoint.

    Each row's name is prefixed with a red ``✗`` when ``fatal=True``.
    Capabilities without a separate ``container_endpoint`` show the
    host endpoint in both columns.
    """
    cap_table = Table(show_header=True, header_style="bold", box=None, width=180)
    cap_table.add_column("Name", style="cyan", no_wrap=True)
    cap_table.add_column("Host endpoint")
    cap_table.add_column("Container address")
    for ec in caps:
        name = f"[red]✗[/red] {ec.name}" if ec.fatal else ec.name
        cap_table.add_row(name, ec.host_endpoint, ec.container_endpoint)
    return cap_table

"""Core CLI commands — init."""

from __future__ import annotations

from pathlib import Path

import click

from mtg.config import (
    ensure_intervals_file,
    get_config_path,
    get_data_dir,
    get_default_data_dir,
    is_initialized,
    save_config,
)
from mtg.display import console

from mtg.cli import main


@main.command()
def init() -> None:
    """Set up Mind the Gap for the first time."""
    if is_initialized():
        data_dir = get_data_dir()
        console.print(
            f"\n  Mind the Gap is already set up. Data directory: [cyan]{data_dir}[/cyan]\n"
        )
        return

    console.print("\n  [bold]Welcome to Mind the Gap![/bold]\n")
    console.print("  Where should Mind the Gap store your study plans?\n")
    default = get_default_data_dir()
    console.print(f"  [cyan][1][/cyan] Default: {default}")
    console.print("  [cyan][2][/cyan] Custom path\n")

    choice = click.prompt("  Your choice", type=click.IntRange(1, 2), default=1)

    if choice == 1:
        data_dir = default
    else:
        path_str = click.prompt("  Enter the full path")
        data_dir = Path(path_str).expanduser().resolve()

    # Save config
    save_config({"data_dir": str(data_dir)})

    # Create directories and files
    data_dir.mkdir(parents=True, exist_ok=True)
    ensure_intervals_file()

    console.print(f"\n  [green]✓[/green] Created {data_dir}")
    console.print(f"  [green]✓[/green] Created {data_dir / 'intervals.toml'}")
    console.print(f"  [green]✓[/green] Config saved to {get_config_path()}")
    console.print(
        "\n  You're ready! To get started:\n"
        "    Import a plan:    [cyan]mtg add my-book.toml[/cyan]\n"
        "    Or add topics:    [cyan]mtg topic mybook ch1 \"Introduction\"[/cyan]\n"
    )

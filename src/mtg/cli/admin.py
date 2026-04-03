"""Admin CLI commands — stats, export, backup, restore, config."""

from __future__ import annotations

import datetime
from pathlib import Path

import click

from mtg.config import (
    CONFIDENCE_DESCRIPTIONS,
    clear_intervals_cache,
    ensure_data_dir,
    get_config_path,
    get_data_dir,
    get_intervals_path,
    load_intervals,
)
from mtg.display import console
from mtg.models import Session
from mtg.scheduler import compute_book_progress
from mtg.storage import (
    discover_books,
    find_book_by_id,
    load_sessions,
)
from mtg.theme import CONFIDENCE_COLOURS

from mtg.cli import _book_not_found, _complete_book_id, _ensure_init, main


@main.command("stats")
@click.argument("book_id", required=False, default=None, shell_complete=_complete_book_id)
def stats(book_id: str | None) -> None:
    """Show study statistics (overall or for a specific book)."""
    _ensure_init()

    if book_id:
        result = find_book_by_id(book_id)
        if result is None:
            console.print(f"\n  [red]Book '{book_id}' not found.[/red]\n")
            return
        books = [result[0]]
    else:
        books = discover_books()

    if not books:
        console.print("\n  [dim]No books found.[/dim]\n")
        return

    all_sessions: list[Session] = []
    for book in books:
        all_sessions.extend(load_sessions(book.filename))

    if not all_sessions:
        console.print("\n  [dim]No study sessions logged yet.[/dim]\n")
        return

    # Overall stats
    total_sessions = len(all_sessions)
    avg_confidence = sum(s.confidence for s in all_sessions) / total_sessions
    unique_dates = sorted({s.date for s in all_sessions})
    unique_topics = {s.topic_id for s in all_sessions}

    # Streak calculation: count consecutive days ending today (or yesterday)
    today = datetime.date.today()
    streak = 0
    check_date = today
    date_set = set(unique_dates)
    # Allow streak to start from today or yesterday
    if check_date not in date_set:
        check_date = today - datetime.timedelta(days=1)
    while check_date in date_set:
        streak += 1
        check_date -= datetime.timedelta(days=1)

    # Sessions in last 7 / 30 days
    week_ago = today - datetime.timedelta(days=7)
    month_ago = today - datetime.timedelta(days=30)
    sessions_this_week = sum(1 for s in all_sessions if s.date > week_ago)
    sessions_this_month = sum(1 for s in all_sessions if s.date > month_ago)

    scope = f" for [bold]{books[0].title}[/bold]" if book_id else ""
    console.print(f"\n  [bold]Study Statistics[/bold]{scope}\n")

    from rich.table import Table

    table = Table(show_header=False, padding=(0, 2), show_edge=False, show_lines=False)
    table.add_column(style="dim", width=22)
    table.add_column(style="bold")

    table.add_row("Total sessions", str(total_sessions))
    table.add_row("Topics studied", str(len(unique_topics)))
    table.add_row("Study days", str(len(unique_dates)))
    table.add_row("Current streak", f"{streak} day{'s' if streak != 1 else ''}")
    table.add_row("Avg. confidence", f"{avg_confidence:.1f} / 10")
    table.add_row("Last 7 days", f"{sessions_this_week} sessions")
    table.add_row("Last 30 days", f"{sessions_this_month} sessions")

    if unique_dates:
        table.add_row("First session", unique_dates[0].strftime("%b %d, %Y"))
        table.add_row("Last session", unique_dates[-1].strftime("%b %d, %Y"))

    console.print(table)

    # Per-book breakdown if showing all
    if not book_id and len(books) > 1:
        console.print(f"\n  [bold]Per Book[/bold]\n")
        book_table = Table(
            show_header=True, header_style="bold", padding=(0, 1),
            show_edge=True, show_lines=False,
        )
        book_table.add_column("Book", width=25)
        book_table.add_column("Sessions", justify="right", width=10)
        book_table.add_column("Avg. Conf.", justify="right", width=10)
        book_table.add_column("Progress", justify="right", width=10)

        for book in books:
            book_sessions = load_sessions(book.filename)
            if not book_sessions:
                continue
            b_total = len(book_sessions)
            b_avg = sum(s.confidence for s in book_sessions) / b_total
            completed, total = compute_book_progress(book, book_sessions)
            pct = f"{round(completed / total * 100)}%" if total > 0 else "0%"
            book_table.add_row(book.title, str(b_total), f"{b_avg:.1f}", pct)

        console.print(book_table)

    console.print()


@main.command("export")
@click.argument("book_id", shell_complete=_complete_book_id)
@click.option("--output", "-o", default=None, help="Output file path")
@click.option(
    "--format", "fmt", default="toml",
    type=click.Choice(["toml", "json", "csv"], case_sensitive=False),
    show_default=True, help="Export format",
)
def export_book(book_id: str, output: str | None, fmt: str) -> None:
    """Export a book's plan and session history.

    Formats: toml (default, re-importable), json, csv (sessions only).
    """
    _ensure_init()

    result = find_book_by_id(book_id)
    if result is None:
        _book_not_found(book_id)
        return

    book, filepath = result
    sessions = load_sessions(book.filename)

    suffix = {"toml": ".toml", "json": ".json", "csv": ".csv"}[fmt]
    if output:
        dest = Path(output)
    else:
        dest = Path.cwd() / f"{book.filename}-export{suffix}"

    if fmt == "toml":
        import toml as toml_lib

        export_data: dict = {
            "book": {
                "title": book.title,
                "id": book.id,
                "sessions_per_topic": book.sessions_per_topic,
            },
            "topic": [
                {"id": t.id, "title": t.title, "parent": t.parent} for t in book.topics
            ],
            "session": [
                {
                    "topic_id": s.topic_id,
                    "date": s.date.isoformat(),
                    "confidence": s.confidence,
                    "next_due": s.next_due.isoformat(),
                    "session_number": s.session_number,
                }
                for s in sessions
            ],
        }
        if book.exam_date:
            export_data["book"]["exam_date"] = book.exam_date.isoformat()

        with open(dest, "w") as f:
            toml_lib.dump(export_data, f)

    elif fmt == "json":
        import json

        export_data_json = {
            "book": {
                "title": book.title,
                "id": book.id,
                "sessions_per_topic": book.sessions_per_topic,
                "exam_date": book.exam_date.isoformat() if book.exam_date else None,
                "frozen": book.frozen,
            },
            "topics": [
                {"id": t.id, "title": t.title, "parent": t.parent}
                for t in book.topics
            ],
            "sessions": [
                {
                    "topic_id": s.topic_id,
                    "date": s.date.isoformat(),
                    "confidence": s.confidence,
                    "next_due": s.next_due.isoformat(),
                    "session_number": s.session_number,
                }
                for s in sessions
            ],
        }
        with open(dest, "w") as f:
            json.dump(export_data_json, f, indent=2)
            f.write("\n")

    elif fmt == "csv":
        import csv

        with open(dest, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "topic_id", "topic_title", "date", "confidence",
                "next_due", "session_number",
            ])
            topic_titles = {t.id: t.title for t in book.topics}
            for s in sessions:
                writer.writerow([
                    s.topic_id,
                    topic_titles.get(s.topic_id, ""),
                    s.date.isoformat(),
                    s.confidence,
                    s.next_due.isoformat(),
                    s.session_number,
                ])

    console.print(f"\n  [green]✓[/green] Exported to {dest}\n")


@main.command("backup")
def backup() -> None:
    """Create a zip backup of the entire data directory."""
    _ensure_init()

    import zipfile

    data_dir = get_data_dir()
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = Path.cwd() / f"mtg-backup-{timestamp}.zip"

    file_count = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in sorted(data_dir.glob("*.toml")):
            zf.write(fp, fp.name)
            file_count += 1

    if file_count == 0:
        dest.unlink()
        console.print("\n  [dim]No data files to back up.[/dim]\n")
        return

    size_kb = dest.stat().st_size / 1024
    console.print(
        f"\n  [green]✓[/green] Backed up {file_count} file(s) to {dest.name} "
        f"({size_kb:.1f} KB)\n"
    )


@main.command("restore")
@click.argument("backup_file", type=click.Path(exists=True))
def restore(backup_file: str) -> None:
    """Restore data from a zip backup created by `mtg backup`.

    This overwrites existing files in the data directory.
    """
    _ensure_init()

    import zipfile

    source = Path(backup_file)
    if not zipfile.is_zipfile(source):
        console.print(f"\n  [red]{source.name} is not a valid zip file.[/red]\n")
        return

    with zipfile.ZipFile(source, "r") as zf:
        toml_files = [n for n in zf.namelist() if n.endswith(".toml")]
        if not toml_files:
            console.print("\n  [red]No TOML files found in the archive.[/red]\n")
            return

        console.print(
            f"\n  This will restore {len(toml_files)} file(s) from "
            f"[bold]{source.name}[/bold] into {get_data_dir()}."
        )
        console.print("  [yellow]Existing files with the same names will be overwritten.[/yellow]")

        if not click.confirm("\n  Continue?"):
            console.print("  Cancelled.\n")
            return

        data_dir = ensure_data_dir()
        for name in toml_files:
            zf.extract(name, data_dir)
            console.print(f"  [green]✓[/green] Restored {name}")

    console.print()


# ── Config sub-commands ──────────────────────────────────────────────────


@main.group("config", invoke_without_command=True)
@click.pass_context
def config(ctx: click.Context) -> None:
    """View or edit Mind the Gap configuration.

    Run without a sub-command to see the current configuration summary.
    """
    _ensure_init()

    if ctx.invoked_subcommand is not None:
        return

    # Show current config summary
    data_dir = get_data_dir()
    config_path = get_config_path()
    intervals_path = get_intervals_path()

    console.print("\n  [bold]Configuration[/bold]\n")

    from rich.table import Table

    table = Table(show_header=False, padding=(0, 2), show_edge=False, show_lines=False)
    table.add_column(style="dim", width=22)
    table.add_column(style="bold")

    table.add_row("Config file", str(config_path))
    table.add_row("Data directory", str(data_dir))
    table.add_row("Intervals file", str(intervals_path))

    console.print(table)
    console.print(
        f"\n  [dim]Run:[/dim] mtg config intervals [dim]to view/edit review intervals.[/dim]\n"
    )


@config.group("intervals", invoke_without_command=True)
@click.pass_context
def config_intervals(ctx: click.Context) -> None:
    """View or edit the confidence-to-days interval mapping."""
    if ctx.invoked_subcommand is not None:
        return

    # Show current intervals
    intervals = load_intervals()
    console.print("\n  [bold]Review Intervals[/bold] (confidence → days)\n")

    from rich.table import Table

    table = Table(
        show_header=True, header_style="bold", padding=(0, 2),
        show_edge=True, show_lines=False,
    )
    table.add_column("Confidence", justify="center", width=12)
    table.add_column("Days", justify="center", width=8)
    table.add_column("Description", width=50)

    for level in sorted(intervals.keys()):
        desc = CONFIDENCE_DESCRIPTIONS.get(level, "")
        colour = CONFIDENCE_COLOURS.get(level, "white")
        table.add_row(
            f"[{colour}]{level}[/{colour}]",
            str(intervals[level]),
            f"[dim]{desc}[/dim]",
        )

    console.print(table)
    console.print(
        f"\n  [dim]Edit:[/dim] mtg config intervals set <level> <days>"
        f"\n  [dim]File:[/dim] {get_intervals_path()}\n"
    )


@config_intervals.command("set")
@click.argument("level", type=click.IntRange(1, 10))
@click.argument("days", type=click.IntRange(1))
def config_intervals_set(level: int, days: int) -> None:
    """Set the number of days for a confidence level.

    Example: mtg config intervals set 5 7
    """
    import toml as toml_lib

    intervals_path = get_intervals_path()

    if intervals_path.exists():
        data = toml_lib.load(intervals_path)
    else:
        data = {"intervals": {str(k): v for k, v in load_intervals().items()}}

    old_value = data.get("intervals", {}).get(str(level), "?")
    data.setdefault("intervals", {})[str(level)] = days

    with open(intervals_path, "w") as f:
        toml_lib.dump(data, f)

    clear_intervals_cache()

    console.print(
        f"\n  [green]✓[/green] Confidence {level}: {old_value} → {days} days\n"
    )


@config_intervals.command("reset")
def config_intervals_reset() -> None:
    """Reset all intervals to their defaults."""
    from mtg.config import DEFAULT_INTERVALS_TOML

    intervals_path = get_intervals_path()

    if not click.confirm("  Reset all intervals to defaults?"):
        console.print("  Cancelled.\n")
        return

    with open(intervals_path, "w") as f:
        f.write(DEFAULT_INTERVALS_TOML)

    clear_intervals_cache()

    console.print("\n  [green]✓[/green] Intervals reset to defaults.\n")

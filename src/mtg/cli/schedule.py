"""Schedule CLI commands — today, plan, freeze, unfreeze."""

from __future__ import annotations

import datetime

import click

from mtg.display import console, display_book_detail, display_today
from mtg.scheduler import (
    count_frozen_affected,
    count_sessions,
    get_latest_session,
    parse_freeze_target,
)
from mtg.storage import (
    discover_books,
    find_book_by_id,
    load_sessions,
    save_book,
)

from mtg.cli import _book_not_found, _complete_book_id, _ensure_init, main


@main.command("today")
@click.argument("book_id", required=False, default=None, shell_complete=_complete_book_id)
@click.option("--days", default=3, type=int, show_default=True, help="Days to look ahead for 'coming up' section")
def today(book_id: str | None, days: int) -> None:
    """Show what's due today (across all books or a specific one)."""
    _ensure_init()
    books = discover_books()
    display_today(books, filter_book_id=book_id, lookahead_days=days)


@main.command("plan")
@click.argument("book_id", required=False, default=None, shell_complete=_complete_book_id)
def plan(book_id: str | None) -> None:
    """Show full plan and progress for a book, or all books."""
    _ensure_init()

    if book_id:
        result = find_book_by_id(book_id)
        if result is None:
            console.print(f"\n  [red]Book '{book_id}' not found.[/red]\n")
            return
        display_book_detail(result[0])
    else:
        books = discover_books()
        if not books:
            console.print("\n  [dim]No books found. Run:[/dim] mtg add <plan.toml>\n")
            return
        for book in books:
            display_book_detail(book)


@main.command("freeze")
@click.argument("book_id", shell_complete=_complete_book_id)
@click.argument("duration")
@click.option("--dry-run", is_flag=True, help="Preview the freeze without making changes")
def freeze(book_id: str, duration: str, dry_run: bool) -> None:
    """Freeze a study plan. Duration: 10D, 2W, 3M, 1Y, or YYYY-MM-DD."""
    _ensure_init()

    from mtg.scheduler import is_absolute_date

    result = find_book_by_id(book_id)
    if result is None:
        _book_not_found(book_id)
        return

    book, filepath = result

    if book.frozen:
        since_str = (
            f" (since {book.frozen_since.strftime('%b %d')})"
            if book.frozen_since
            else ""
        )
        console.print(
            f"\n  [yellow]{book.title} is already frozen until "
            f"{book.frozen_until.strftime('%b %d') if book.frozen_until else '?'}"
            f"{since_str}.[/yellow]\n"
        )
        return

    # Ask when the freeze started
    today_date = datetime.date.today()
    console.print("\n  When did the freeze start?\n")
    console.print(
        "  [cyan][1][/cyan] Today ({})".format(today_date.strftime("%b %d"))
    )
    console.print("  [cyan][2][/cyan] Enter a past date\n")

    date_choice = click.prompt("  Your choice", type=click.IntRange(1, 2), default=1)

    if date_choice == 1:
        since = today_date
    else:
        date_str = click.prompt("  Start date (YYYY-MM-DD)")
        try:
            since = datetime.date.fromisoformat(date_str.strip())
        except ValueError:
            console.print("  [red]Invalid date format. Use YYYY-MM-DD.[/red]\n")
            return
        if since > today_date:
            console.print("  [red]Start date cannot be in the future.[/red]\n")
            return

    # Parse the end date — durations are relative to the start date
    try:
        until = parse_freeze_target(duration, start_date=since)
    except ValueError as e:
        console.print(f"\n  [red]{e}[/red]\n")
        return

    # Guardrail: end date must be after start date
    if until <= since:
        console.print(
            f"\n  [red]Freeze end date ({until.strftime('%b %d, %Y')}) "
            f"must be after the start date ({since.strftime('%b %d, %Y')}).[/red]\n"
        )
        return

    # Guardrail: end date must be in the future
    if until <= today_date:
        console.print(
            f"\n  [red]Freeze end date ({until.strftime('%b %d, %Y')}) "
            f"must be in the future.[/red]\n"
        )
        return

    sessions = load_sessions(book.filename)
    affected, unaffected = count_frozen_affected(book, sessions, until, since=since)

    # Build the summary
    duration_days = (until - since).days
    if since == today_date:
        from_str = "from today"
    else:
        from_str = f"from {since.strftime('%b %d')}"

    console.print(
        f"\n  Freezing [bold]{book.title}[/bold]\n"
        f"    {from_str} → until {until.strftime('%b %d, %Y')} ({duration_days} days).\n"
    )
    console.print(
        f"  {affected} session{'s' if affected != 1 else ''} "
        f"(due between {since.strftime('%b %d')} and {until.strftime('%b %d')}) "
        f"will be pushed to {until.strftime('%b %d')}."
    )
    if unaffected:
        console.print(
            f"  {unaffected} session{'s' if unaffected != 1 else ''} "
            f"(due after {until.strftime('%b %d')}) will not be affected."
        )
    console.print()

    if dry_run:
        console.print("  [dim](dry run — no changes made)[/dim]\n")
        return

    if not click.confirm("  Confirm?"):
        console.print("  Cancelled.\n")
        return

    book.freeze(since, until)
    save_book(book, filepath)

    console.print(
        f"\n  [green]✓[/green] Frozen {from_str} until {until.strftime('%b %d')}. "
        f"Run: [cyan]mtg unfreeze {book.id}[/cyan] to resume early.\n"
    )


@main.command("unfreeze")
@click.argument("book_id", shell_complete=_complete_book_id)
@click.option("--dry-run", is_flag=True, help="Preview the unfreeze without making changes")
def unfreeze(book_id: str, dry_run: bool) -> None:
    """Unfreeze a study plan (resume early)."""
    _ensure_init()

    result = find_book_by_id(book_id)
    if result is None:
        _book_not_found(book_id)
        return

    book, filepath = result

    if not book.frozen:
        console.print(f"\n  [dim]{book.title} is not frozen.[/dim]\n")
        return

    sessions = load_sessions(book.filename)
    today_date = datetime.date.today()

    # Count how many sessions get bumped to today
    affected = 0
    for topic in book.leaf_topics():
        latest = get_latest_session(topic.id, sessions)
        if latest and not (count_sessions(topic.id, sessions) >= book.sessions_per_topic):
            if latest.next_due <= (book.frozen_until or today_date):
                affected += 1

    console.print(f"\n  Unfreezing [bold]{book.title}[/bold].")
    if affected:
        console.print(
            f"  {affected} session{'s' if affected != 1 else ''} "
            f"{'were' if affected != 1 else 'was'} paused — "
            f"{'they' if affected != 1 else 'it'} would become due today."
        )

    if dry_run:
        console.print("  [dim](dry run — no changes made)[/dim]\n")
        return

    book.unfreeze()
    save_book(book, filepath)

    console.print(
        f"\n  [green]✓[/green] Unfrozen. Run: [cyan]mtg today[/cyan] to see your schedule.\n"
    )

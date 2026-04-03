"""Study session CLI commands — done, undo."""

from __future__ import annotations

import datetime

import click

from mtg.config import CONFIDENCE_DESCRIPTIONS
from mtg.display import console
from mtg.models import Session, TopicStatus
from mtg.scheduler import (
    compute_next_due,
    count_sessions,
    get_due_topics,
    get_latest_session,
)
from mtg.storage import (
    append_session,
    discover_books,
    find_topic_across_books,
    load_sessions,
    pop_latest_session,
)
from mtg.theme import CONFIDENCE_COLOURS

from mtg.cli import _complete_topic_id, _ensure_init, _topic_not_found, main


@main.command("done")
@click.argument("topic_id", required=False, default=None, shell_complete=_complete_topic_id)
def mark_done(topic_id: str | None) -> None:
    """Mark a topic as studied and log a session.

    Run without arguments to pick from due topics interactively.
    """
    _ensure_init()

    if topic_id is None:
        # Interactive mode: show due topics and let user pick
        books = discover_books()
        actionable: list[tuple[TopicStatus, object]] = []

        for book in books:
            if book.frozen:
                continue
            sessions = load_sessions(book.filename)
            due_info = get_due_topics(book, sessions)
            for status in due_info["overdue"]:
                actionable.append((status, book))
            for status in due_info["due_today"]:
                actionable.append((status, book))

        if not actionable:
            console.print("\n  [green]Nothing due today![/green] You can still log a session with: [cyan]mtg done <topic_id>[/cyan]\n")
            return

        console.print(f"\n  [bold]{len(actionable)} topic(s) due:[/bold]\n")
        for i, (status, book) in enumerate(actionable, 1):
            overdue_str = ""
            if status.is_overdue:
                overdue_str = f" [red](overdue {status.days_overdue}d)[/red]"
            console.print(
                f"  [cyan][{i}][/cyan] {status.topic.id:<12} "
                f"{status.topic.title:<35} "
                f"[dim]{book.title}[/dim]{overdue_str}"
            )
        console.print()

        choice = click.prompt(
            "  Pick a topic", type=click.IntRange(1, len(actionable))
        )
        status, book = actionable[choice - 1]
        topic_id = status.topic.id

    result = find_topic_across_books(topic_id)
    if result is None:
        _topic_not_found(topic_id)
        return

    book, topic, filepath = result

    if book.frozen:
        console.print(
            f"\n  [yellow]{book.title} is frozen until "
            f"{book.frozen_until.strftime('%b %d') if book.frozen_until else '?'}.[/yellow]"
        )
        if not click.confirm("  Log a session anyway?"):
            return

    sessions = load_sessions(book.filename)
    completed = count_sessions(topic_id, sessions)
    session_num = completed + 1

    console.print(
        f"\n  [bold]{topic.title}[/bold] — session {session_num} of {book.sessions_per_topic}\n"
    )

    # Ask for date
    console.print("  When did you study this?")
    console.print(
        "  [cyan][1][/cyan] Today ({})".format(datetime.date.today().strftime("%b %d"))
    )
    console.print("  [cyan][2][/cyan] Enter a custom date\n")

    date_choice = click.prompt("  ", type=click.IntRange(1, 2), default=1)

    if date_choice == 1:
        study_date = datetime.date.today()
    else:
        date_str = click.prompt("  Date (YYYY-MM-DD)")
        try:
            study_date = datetime.date.fromisoformat(date_str.strip())
        except ValueError:
            console.print("  [red]Invalid date. Using today.[/red]")
            study_date = datetime.date.today()

    # Ask for confidence
    console.print("\n  How confident do you feel? (1–10)\n")
    for level, desc in CONFIDENCE_DESCRIPTIONS.items():
        colour = CONFIDENCE_COLOURS.get(level, "cyan")
        console.print(f"  [{colour}]{level:>2}[/{colour}]  {desc}")
    console.print()

    confidence = click.prompt("  ", type=click.IntRange(1, 10))

    # Calculate next due
    next_due = compute_next_due(study_date, confidence)

    # Create and save session
    session = Session(
        topic_id=topic_id,
        book=book.filename,
        date=study_date,
        confidence=confidence,
        next_due=next_due,
        session_number=session_num,
    )
    append_session(book.filename, session)

    days_until = (next_due - datetime.date.today()).days
    console.print(
        f"\n  [green]✓[/green] Logged. Next review: "
        f"{next_due.strftime('%b %d')} ({days_until} day{'s' if days_until != 1 else ''})\n"
    )


@main.command("undo")
@click.argument("topic_id", shell_complete=_complete_topic_id)
def undo(topic_id: str) -> None:
    """Undo the last study session for a topic."""
    _ensure_init()

    result = find_topic_across_books(topic_id)
    if result is None:
        _topic_not_found(topic_id)
        return

    book, topic, filepath = result

    sessions = load_sessions(book.filename)
    completed = count_sessions(topic_id, sessions)
    if completed == 0:
        console.print(f"\n  [dim]{topic.title} has no sessions to undo.[/dim]\n")
        return

    latest = get_latest_session(topic_id, sessions)
    console.print(
        f"\n  Undo session {latest.session_number} of [bold]{topic.title}[/bold]?"
    )
    console.print(
        f"  (date: {latest.date.strftime('%b %d')}, "
        f"confidence: {latest.confidence}, "
        f"next due: {latest.next_due.strftime('%b %d')})"
    )

    if not click.confirm("\n  Confirm?"):
        console.print("  Cancelled.\n")
        return

    removed = pop_latest_session(book.filename, topic_id)
    if removed:
        console.print(f"\n  [green]✓[/green] Undone. Session {removed.session_number} removed.\n")

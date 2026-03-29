"""CLI entry point for Mind the Gap."""

from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

import click

from mtg import __version__
from mtg.config import (
    CONFIDENCE_DESCRIPTIONS,
    ensure_data_dir,
    ensure_intervals_file,
    get_config_path,
    get_data_dir,
    get_default_data_dir,
    is_initialized,
    save_config,
)
from mtg.display import console, display_all_books, display_book_detail, display_today
from mtg.models import Session, Topic, TopicStatus
from mtg.scheduler import (
    compute_book_progress,
    compute_next_due,
    count_frozen_affected,
    count_sessions,
    get_due_topics,
    get_latest_session,
    parse_freeze_target,
)
from mtg.storage import (
    append_session,
    delete_book_files,
    discover_books,
    find_book_by_id,
    find_topic_across_books,
    get_book_path,
    list_book_ids,
    list_topic_ids_for_book,
    load_book,
    load_sessions,
    pop_latest_session,
    remove_sessions_for_topics,
    remove_topic_from_book,
    save_book,
    save_sessions,
    suggest_matches,
    would_create_cycle,
)


_VALID_ID_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")


def _validate_id(value: str, label: str = "ID") -> bool:
    """Validate that an ID contains only safe characters. Returns True if valid."""
    if not value:
        console.print(f"\n  [red]{label} cannot be empty.[/red]\n")
        return False
    if not _VALID_ID_PATTERN.match(value):
        console.print(
            f"\n  [red]{label} '{value}' contains invalid characters.[/red]\n"
            f"  [dim]Allowed: letters, digits, dots, hyphens, underscores.[/dim]\n"
        )
        return False
    return True


def _book_not_found(book_id: str) -> None:
    """Print a 'book not found' error with suggestions."""
    console.print(f"\n  [red]Book '{book_id}' not found.[/red]")
    suggestions = suggest_matches(book_id, list_book_ids())
    if suggestions:
        console.print(f"  [dim]Did you mean: {', '.join(suggestions)}?[/dim]")
    console.print()


def _topic_not_found(topic_id: str, book: object = None) -> None:
    """Print a 'topic not found' error with suggestions."""
    if book is not None and hasattr(book, "topics"):
        console.print(f"\n  [red]Topic '{topic_id}' not found in {book.id}.[/red]")
        suggestions = suggest_matches(topic_id, list_topic_ids_for_book(book))
    else:
        console.print(f"\n  [red]Topic '{topic_id}' not found in any book.[/red]")
        suggestions = []
    if suggestions:
        console.print(f"  [dim]Did you mean: {', '.join(suggestions)}?[/dim]")
    console.print()


def _ensure_init() -> None:
    """Check that mtg has been initialized, prompt if not."""
    if not is_initialized():
        console.print(
            "\n  [yellow]Mind the Gap hasn't been set up yet.[/yellow] "
            "Run: [cyan]mtg init[/cyan]\n"
        )
        sys.exit(1)


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version=__version__, prog_name="Mind the Gap")
def main(ctx: click.Context) -> None:
    """Mind the Gap — a spaced repetition study planner.

    Run without arguments to see all your books, or use a subcommand.
    """
    if ctx.invoked_subcommand is None:
        _ensure_init()
        books = discover_books()
        display_all_books(books)


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


@main.command()
@click.argument("plan_file", type=click.Path(exists=True))
def add(plan_file: str) -> None:
    """Import a study plan from a TOML file.

    If the file contains [[session]] entries (e.g. from `mtg export`),
    those are imported into the state file as well.
    """
    _ensure_init()

    import toml as toml_lib

    source = Path(plan_file)
    book = load_book(source)

    # Check for embedded sessions (from export files)
    raw_data = toml_lib.load(source)
    raw_sessions = raw_data.get("session", [])

    # Copy plan to data directory (without session data)
    dest = get_data_dir() / source.name
    if dest.exists():
        if not click.confirm(f"  {dest.name} already exists. Overwrite?"):
            return

    # Save a clean book file (no session entries)
    save_book(book, dest)

    console.print(f"\n  [green]✓[/green] Imported [bold]{book.title}[/bold] ({book.id})")
    console.print(f"    {len(book.topics)} topics, {book.sessions_per_topic} sessions each")
    if book.exam_date:
        days_left = (book.exam_date - datetime.date.today()).days
        if days_left < 0:
            console.print(
                f"    [yellow]Exam: {book.exam_date.strftime('%b %d, %Y')} "
                f"({-days_left} day{'s' if -days_left != 1 else ''} ago)[/yellow]"
            )
        else:
            console.print(f"    Exam: {book.exam_date.strftime('%b %d, %Y')} ({days_left} days)")

    # Import sessions if present
    if raw_sessions:
        from mtg.storage import _parse_date

        imported_sessions = []
        for s in raw_sessions:
            imported_sessions.append(
                Session(
                    topic_id=s.get("topic_id", ""),
                    book=book.filename,
                    date=_parse_date(s.get("date")) or datetime.date.today(),
                    confidence=int(s.get("confidence", 1)),
                    next_due=_parse_date(s.get("next_due")) or datetime.date.today(),
                    session_number=int(s.get("session_number", 1)),
                )
            )
        save_sessions(book.filename, imported_sessions)
        console.print(
            f"  [green]✓[/green] Restored {len(imported_sessions)} session(s) from export"
        )

    console.print(f"\n  Run: [cyan]mtg plan {book.id}[/cyan] to see the plan.\n")


@main.command("topic")
@click.argument("book_id")
@click.argument("topic_id")
@click.argument("title")
@click.option("--parent", default="", help="Parent topic/chapter ID")
def add_topic(book_id: str, topic_id: str, title: str, parent: str) -> None:
    """Add a single topic to a book."""
    _ensure_init()

    if not _validate_id(book_id, "Book ID"):
        return
    if not _validate_id(topic_id, "Topic ID"):
        return

    result = find_book_by_id(book_id)

    if result is None:
        # Create a new book
        if not click.confirm(f"  Book '{book_id}' doesn't exist. Create it?"):
            return

        book_title = click.prompt("  Book title")
        exam_str = click.prompt("  Exam date (YYYY-MM-DD, or leave blank)", default="")
        sessions = click.prompt("  Sessions per topic", default=10, type=int)

        if sessions < 1:
            console.print("  [red]Sessions must be at least 1.[/red]\n")
            return

        exam_date = None
        if exam_str.strip():
            try:
                exam_date = datetime.date.fromisoformat(exam_str.strip())
            except ValueError:
                console.print("  [red]Invalid date format. Skipping exam date.[/red]")

        from mtg.models import Book

        book = Book(
            title=book_title,
            id=book_id,
            exam_date=exam_date,
            sessions_per_topic=sessions,
            filename=book_id,
        )
        filepath = get_book_path(book_id)
    else:
        book, filepath = result

    # Check for duplicate topic ID
    for t in book.topics:
        if t.id == topic_id:
            console.print(f"  [red]Topic '{topic_id}' already exists in {book.id}.[/red]")
            return

    # Validate parent exists if specified
    if parent:
        parent_exists = any(t.id == parent for t in book.topics)
        if not parent_exists:
            console.print(f"  [red]Parent '{parent}' not found in {book.id}.[/red]")
            return

    book.topics.append(Topic(id=topic_id, title=title, parent=parent))
    save_book(book, filepath)

    console.print(f"\n  [green]✓[/green] Added [cyan]{topic_id}[/cyan] — {title}")
    if parent:
        console.print(f"    Under: {parent}")
    console.print()


@main.command("edit")
@click.argument("book_id")
@click.argument("topic_id", required=False, default=None)
@click.option("--title", default=None, help="New title")
@click.option("--exam", default=None, help="New exam date (YYYY-MM-DD, or 'none' to clear)")
@click.option("--sessions", default=None, type=int, help="New sessions_per_topic")
@click.option("--parent", default=None, help="New parent for a topic (empty string for root)")
def edit(
    book_id: str,
    topic_id: str | None,
    title: str | None,
    exam: str | None,
    sessions: int | None,
    parent: str | None,
) -> None:
    """Edit a book's properties or a topic's title/parent.

    Edit book:   mtg edit <book_id> --title "New Title" --exam 2026-09-01 --sessions 8
    Edit topic:  mtg edit <book_id> <topic_id> --title "New Title" --parent ch2
    """
    _ensure_init()

    result = find_book_by_id(book_id)
    if result is None:
        _book_not_found(book_id)
        return

    book, filepath = result

    if topic_id is not None:
        # Edit a topic
        found = None
        for t in book.topics:
            if t.id == topic_id:
                found = t
                break

        if found is None:
            _topic_not_found(topic_id, book)
            return

        if title is None and parent is None:
            console.print(
                "\n  [dim]Nothing to change. Use --title or --parent.[/dim]\n"
            )
            return

        changes = []
        if title is not None:
            found.title = title
            changes.append(f"title → {title}")
        if parent is not None:
            if parent and not any(t.id == parent for t in book.topics):
                console.print(f"\n  [red]Parent '{parent}' not found in {book.id}.[/red]\n")
                return
            if parent and would_create_cycle(book, topic_id, parent):
                console.print(
                    f"\n  [red]Cannot set parent to '{parent}' — "
                    f"this would create a circular reference.[/red]\n"
                )
                return
            found.parent = parent
            changes.append(f"parent → {'(root)' if not parent else parent}")

        save_book(book, filepath)
        console.print(f"\n  [green]✓[/green] Updated [cyan]{topic_id}[/cyan]: {', '.join(changes)}\n")
    else:
        # Edit book properties
        if title is None and exam is None and sessions is None:
            console.print(
                "\n  [dim]Nothing to change. Use --title, --exam, or --sessions.[/dim]\n"
            )
            return

        changes = []
        if title is not None:
            book.title = title
            changes.append(f"title → {title}")
        if exam is not None:
            if exam.lower() == "none":
                book.exam_date = None
                changes.append("exam date cleared")
            else:
                try:
                    book.exam_date = datetime.date.fromisoformat(exam.strip())
                    changes.append(f"exam → {book.exam_date.strftime('%b %d, %Y')}")
                except ValueError:
                    console.print(f"\n  [red]Invalid date format: '{exam}'. Use YYYY-MM-DD.[/red]\n")
                    return
        if sessions is not None:
            if sessions < 1:
                console.print("\n  [red]Sessions must be at least 1.[/red]\n")
                return
            book.sessions_per_topic = sessions
            changes.append(f"sessions → {sessions}")

        save_book(book, filepath)
        console.print(f"\n  [green]✓[/green] Updated [bold]{book.id}[/bold]: {', '.join(changes)}\n")


@main.command("remove")
@click.argument("book_id")
@click.argument("topic_id", required=False, default=None)
def remove(book_id: str, topic_id: str | None) -> None:
    """Remove a book or a single topic.

    To remove an entire book:  mtg remove <book_id>
    To remove a single topic:  mtg remove <book_id> <topic_id>
    """
    _ensure_init()

    result = find_book_by_id(book_id)
    if result is None:
        _book_not_found(book_id)
        return

    book, filepath = result

    if topic_id is None:
        # Remove entire book
        leaf_count = len(book.leaf_topics())
        sessions = load_sessions(book.filename)
        console.print(
            f"\n  This will permanently delete [bold]{book.title}[/bold] "
            f"({len(book.topics)} topics, {len(sessions)} sessions)."
        )
        if not click.confirm("  Are you sure?"):
            console.print("  Cancelled.\n")
            return

        deleted = delete_book_files(book.filename)
        for p in deleted:
            console.print(f"  [green]✓[/green] Deleted {p.name}")
        console.print()
    else:
        # Remove a single topic
        found = None
        for t in book.topics:
            if t.id == topic_id:
                found = t
                break

        if found is None:
            _topic_not_found(topic_id, book)
            return

        # Check for descendants
        descendants = book.all_descendants(topic_id)
        children = book.children_of(topic_id)
        if children:
            console.print(
                f"\n  [yellow]{topic_id}[/yellow] has {len(children)} "
                f"direct children and {len(descendants)} leaf descendants. "
                f"They will all be removed."
            )

        if not click.confirm(f"  Remove '{topic_id}' from {book.id}?"):
            console.print("  Cancelled.\n")
            return

        removed_ids = remove_topic_from_book(book, topic_id)
        save_book(book, filepath)

        # Clean up sessions
        sessions_removed = remove_sessions_for_topics(book.filename, set(removed_ids))

        console.print(f"\n  [green]✓[/green] Removed {len(removed_ids)} topic(s): {', '.join(removed_ids)}")
        if sessions_removed:
            console.print(f"  [green]✓[/green] Removed {sessions_removed} session(s)")
        console.print()


@main.command("done")
@click.argument("topic_id", required=False, default=None)
def mark_done(topic_id: str | None) -> None:
    """Mark a topic as studied and log a session.

    Run without arguments to pick from due topics interactively.
    """
    _ensure_init()

    if topic_id is None:
        # Interactive mode: show due topics and let user pick
        books = discover_books()
        actionable: list[tuple[TopicStatus, Book]] = []

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
        console.print(f"  [cyan]{level:>2}[/cyan]  {desc}")
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
@click.argument("topic_id")
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


@main.command("today")
@click.argument("book_id", required=False, default=None)
@click.option("--days", default=3, type=int, show_default=True, help="Days to look ahead for 'coming up' section")
def today(book_id: str | None, days: int) -> None:
    """Show what's due today (across all books or a specific one)."""
    _ensure_init()
    books = discover_books()
    display_today(books, filter_book_id=book_id, lookahead_days=days)


@main.command("plan")
@click.argument("book_id", required=False, default=None)
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
@click.argument("book_id")
@click.argument("duration")
def freeze(book_id: str, duration: str) -> None:
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
    today = datetime.date.today()
    console.print("\n  When did the freeze start?\n")
    console.print(
        "  [cyan][1][/cyan] Today ({})".format(today.strftime("%b %d"))
    )
    console.print("  [cyan][2][/cyan] Enter a past date\n")

    date_choice = click.prompt("  Your choice", type=click.IntRange(1, 2), default=1)

    if date_choice == 1:
        since = today
    else:
        date_str = click.prompt("  Start date (YYYY-MM-DD)")
        try:
            since = datetime.date.fromisoformat(date_str.strip())
        except ValueError:
            console.print("  [red]Invalid date format. Use YYYY-MM-DD.[/red]\n")
            return
        if since > today:
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
    if until <= today:
        console.print(
            f"\n  [red]Freeze end date ({until.strftime('%b %d, %Y')}) "
            f"must be in the future.[/red]\n"
        )
        return

    sessions = load_sessions(book.filename)
    affected, unaffected = count_frozen_affected(book, sessions, until, since=since)

    # Build the summary
    duration_days = (until - since).days
    if since == today:
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

    if not click.confirm("  Confirm?"):
        console.print("  Cancelled.\n")
        return

    book.frozen = True
    book.frozen_since = since
    book.frozen_until = until
    save_book(book, filepath)

    console.print(
        f"\n  [green]✓[/green] Frozen {from_str} until {until.strftime('%b %d')}. "
        f"Run: [cyan]mtg unfreeze {book.id}[/cyan] to resume early.\n"
    )


@main.command("unfreeze")
@click.argument("book_id")
def unfreeze(book_id: str) -> None:
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

    book.frozen = False
    book.frozen_since = None
    book.frozen_until = None
    save_book(book, filepath)

    console.print(f"\n  Unfreezing [bold]{book.title}[/bold].")
    if affected:
        console.print(
            f"  {affected} session{'s' if affected != 1 else ''} "
            f"{'were' if affected != 1 else 'was'} paused — "
            f"{'they are' if affected != 1 else 'it is'} now due today."
        )
    console.print(
        f"\n  [green]✓[/green] Unfrozen. Run: [cyan]mtg today[/cyan] to see your schedule.\n"
    )


@main.command("stats")
@click.argument("book_id", required=False, default=None)
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
@click.argument("book_id")
@click.option("--output", "-o", default=None, help="Output file path")
def export_book(book_id: str, output: str | None) -> None:
    """Export a book's current state as a clean TOML file."""
    _ensure_init()

    result = find_book_by_id(book_id)
    if result is None:
        _book_not_found(book_id)
        return

    book, filepath = result

    if output:
        dest = Path(output)
    else:
        dest = Path.cwd() / f"{book.filename}-export.toml"

    # Build export with both plan and sessions
    sessions = load_sessions(book.filename)

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

    console.print(f"\n  [green]✓[/green] Exported to {dest}\n")


if __name__ == "__main__":
    main()

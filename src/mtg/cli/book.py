"""Book management CLI commands — add, topic, edit, remove."""

from __future__ import annotations

import datetime
from pathlib import Path

import click

from mtg.display import console
from mtg.models import Session, Topic
from mtg.storage import (
    delete_book_files,
    find_book_by_id,
    get_book_path,
    load_book,
    load_sessions,
    remove_sessions_for_topics,
    remove_topic_from_book,
    save_book,
    save_sessions,
)

from mtg.cli import (
    _book_not_found,
    _complete_book_id,
    _complete_topic_id,
    _ensure_init,
    _topic_not_found,
    _validate_id,
    main,
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

    from mtg.config import get_data_dir

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
@click.argument("book_id", shell_complete=_complete_book_id)
@click.argument("topic_id", shell_complete=_complete_topic_id)
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
@click.argument("book_id", shell_complete=_complete_book_id)
@click.argument("topic_id", required=False, default=None, shell_complete=_complete_topic_id)
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
            if parent and book.would_create_cycle(topic_id, parent):
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
@click.argument("book_id", shell_complete=_complete_book_id)
@click.argument("topic_id", required=False, default=None, shell_complete=_complete_topic_id)
@click.option("--dry-run", is_flag=True, help="Preview what would be removed without making changes")
def remove(book_id: str, topic_id: str | None, dry_run: bool) -> None:
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
        sessions = load_sessions(book.filename)
        console.print(
            f"\n  This will permanently delete [bold]{book.title}[/bold] "
            f"({len(book.topics)} topics, {len(sessions)} sessions)."
        )

        if dry_run:
            console.print("  [dim](dry run — no changes made)[/dim]\n")
            return

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

        if dry_run:
            # Show what would be removed
            to_remove = {topic_id}
            changed = True
            while changed:
                changed = False
                for t in book.topics:
                    if t.parent in to_remove and t.id not in to_remove:
                        to_remove.add(t.id)
                        changed = True
            console.print(
                f"\n  Would remove {len(to_remove)} topic(s): {', '.join(sorted(to_remove))}"
            )
            console.print("  [dim](dry run — no changes made)[/dim]\n")
            return

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

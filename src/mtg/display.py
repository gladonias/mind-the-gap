"""Display module — terminal rendering for Mind the Gap."""

from __future__ import annotations

import datetime
import textwrap
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

from mtg.models import Book, ChapterStatus, TopicStatus
from mtg.scheduler import (
    build_book_tree,
    compute_book_progress,
    count_actionable,
    get_due_topics,
)
from mtg.storage import load_sessions

console = Console()

TITLE_WRAP_WIDTH = 30


def _progress_bar(completed: int, total: int, width: int = 10) -> str:
    """Create a text progress bar like ████░░░░░░."""
    if total == 0:
        return "░" * width
    filled = round((completed / total) * width)
    filled = min(filled, width)
    return "█" * filled + "░" * (width - filled)


def _wrap_title(title: str, width: int = TITLE_WRAP_WIDTH) -> str:
    """Wrap a title to fit within the given width, preserving words."""
    lines = textwrap.wrap(title, width=width)
    return "\n".join(lines) if lines else title


def _format_due(status: TopicStatus, book: Book) -> str:
    """Format the due date display for a topic."""
    if status.is_done:
        return "[green]✓ done[/green]"
    if status.is_not_started:
        return "[dim]not started[/dim]"
    if status.next_due is None:
        return ""

    today = datetime.date.today()

    if book.frozen:
        return "[yellow](paused)[/yellow]"

    if status.next_due < today:
        days = (today - status.next_due).days
        return f"[red]OVERDUE ({days} day{'s' if days != 1 else ''})[/red]"
    elif status.next_due == today:
        return "[yellow]due today[/yellow]"
    else:
        return f"[dim]{status.next_due.strftime('%b %d')}[/dim]"


def _format_due_today(status: TopicStatus) -> str:
    """Format due info for the 'today' view."""
    if status.next_due is None:
        return ""
    today = datetime.date.today()
    if status.next_due < today:
        days = (today - status.next_due).days
        return f"due {status.next_due.strftime('%b %d')} ({days} day{'s' if days != 1 else ''} ago)"
    elif status.next_due == today:
        return ""
    else:
        return f"due {status.next_due.strftime('%b %d')}"


def display_all_books(books: list[Book]) -> None:
    """Display the overview table of all books."""
    if not books:
        console.print("\n  [dim]No books found. Run:[/dim] mtg add <plan.toml>\n")
        return

    console.print(
        f"\n  [bold]Mind the Gap[/bold] — {len(books)} book{'s' if len(books) != 1 else ''}\n"
    )

    table = Table(
        show_header=True,
        header_style="bold",
        padding=(0, 1),
        show_edge=True,
        show_lines=False,
    )
    table.add_column("ID", style="cyan", width=6)
    table.add_column("Title", width=TITLE_WRAP_WIDTH, overflow="fold")
    table.add_column("Progress", justify="right", width=8)
    table.add_column("Exam", justify="center", width=7)
    table.add_column("Status", justify="right", width=14)

    for book in books:
        sessions = load_sessions(book.filename)
        completed, total = compute_book_progress(book, sessions)
        pct = f"{round(completed / total * 100)}%" if total > 0 else "0%"

        exam_str = book.exam_date.strftime("%b %d") if book.exam_date else "—"

        if book.frozen:
            until = book.frozen_until.strftime("%b %d") if book.frozen_until else "?"
            status_str = f"[yellow]FROZEN → {until}[/yellow]"
        else:
            due_count = count_actionable(book, sessions)
            if due_count > 0:
                status_str = f"[red]{due_count} due[/red]"
            else:
                status_str = "[green]on track[/green]"

        table.add_row(book.id, _wrap_title(book.title), pct, exam_str, status_str)

    console.print(table)
    console.print(
        "\n  [dim]Run:[/dim] mtg plan <book_id> "
        "[dim]for details, or[/dim] mtg today [dim]to see what's due.[/dim]\n"
    )


def _add_tree_rows(
    table: Table,
    node: TopicStatus | ChapterStatus,
    book: Book,
    indent: int = 0,
) -> None:
    """Recursively add rows for a tree node to the table."""
    prefix = "  " * indent
    bar = _progress_bar(node.sessions_completed, node.sessions_total)
    frac = f"{node.sessions_completed}/{node.sessions_total}"
    wrapped_title = _wrap_title(node.topic.title)

    if isinstance(node, ChapterStatus):
        done_str = "[green]✓ done[/green]" if node.is_done else ""
        table.add_row(
            f"[bold]{prefix}{node.topic.id}[/bold]",
            f"[bold]{wrapped_title}[/bold]",
            bar,
            frac,
            done_str,
            style="",
        )
        for child in node.children:
            _add_tree_rows(table, child, book, indent + 1)
    else:
        due = _format_due(node, book)
        table.add_row(
            f"[cyan]{prefix}{node.topic.id}[/cyan]",
            wrapped_title,
            bar,
            frac,
            due,
        )


def display_book_detail(book: Book) -> None:
    """Display detailed plan/progress for a single book."""
    sessions = load_sessions(book.filename)
    completed, total = compute_book_progress(book, sessions)

    # Header
    header = f"  [bold]{book.title}[/bold] ({book.id})"
    header += f"       {book.sessions_per_topic} sessions each"
    if book.exam_date:
        days_left = (book.exam_date - datetime.date.today()).days
        if days_left < 0:
            header += f" │ [yellow]exam: {book.exam_date.strftime('%b %d')} ({-days_left}d ago)[/yellow]"
        else:
            header += f" │ exam: {book.exam_date.strftime('%b %d')} ({days_left} days)"
    console.print(f"\n{header}\n")

    # Freeze banner
    if book.frozen and book.frozen_until:
        days_left = (book.frozen_until - datetime.date.today()).days
        since_str = ""
        if book.frozen_since and book.frozen_since != datetime.date.today():
            since_str = f"from {book.frozen_since.strftime('%b %d')} "
        console.print(
            f"  [yellow]⏸ FROZEN {since_str}until {book.frozen_until.strftime('%b %d')} "
            f"({days_left} day{'s' if days_left != 1 else ''} remaining)[/yellow]"
        )
        console.print(
            f"  [dim]All due dates are paused. Run:[/dim] mtg unfreeze {book.id}\n"
        )

    # Build table
    table = Table(
        show_header=True,
        header_style="bold",
        padding=(0, 1),
        show_edge=True,
        show_lines=False,
    )
    table.add_column("ID", width=12)
    table.add_column("Title", width=TITLE_WRAP_WIDTH, overflow="fold")
    table.add_column("Progress", width=10)
    table.add_column("", width=7, justify="right")
    table.add_column("Due", width=18)

    # Build tree and add rows
    tree = build_book_tree(book, sessions)
    for i, node in enumerate(tree):
        _add_tree_rows(table, node, book, indent=0)
        if i < len(tree) - 1:
            table.add_section()

    console.print(table)

    # Footer
    pct = round(completed / total * 100) if total > 0 else 0

    due_info = get_due_topics(book, sessions)
    overdue_count = len(due_info["overdue"])
    due_today_count = len(due_info["due_today"])
    not_started_count = len(due_info["not_started"])

    parts = [f"{pct}% complete"]
    if overdue_count:
        parts.append(f"{overdue_count} overdue")
    if due_today_count:
        parts.append(f"{due_today_count} due today")
    if not_started_count:
        parts.append(f"{not_started_count} not started")

    console.print(f"\n  [dim]{' │ '.join(parts)}[/dim]\n")


def display_today(
    books: list[Book],
    filter_book_id: Optional[str] = None,
    lookahead_days: int = 3,
) -> None:
    """Display what's due today across all books (or a specific one)."""
    if filter_book_id:
        books = [b for b in books if b.id == filter_book_id]
        if not books:
            console.print(f"\n  [red]Book '{filter_book_id}' not found.[/red]\n")
            return

    total_actionable = 0

    for book in books:
        sessions = load_sessions(book.filename)
        due_info = get_due_topics(book, sessions, include_future_days=lookahead_days)

        # Book header
        header = f"\n  ─── {book.title} ({book.id}) "
        if book.exam_date:
            days_left = (book.exam_date - datetime.date.today()).days
            if days_left < 0:
                header += f"──── [yellow]exam: {book.exam_date.strftime('%b %d')} ({-days_left}d ago)[/yellow] "
            else:
                header += f"──── exam: {book.exam_date.strftime('%b %d')} ({days_left} days) "
        header += "───"

        if book.frozen and book.frozen_until:
            console.print(header)
            days_left = (book.frozen_until - datetime.date.today()).days
            since_str = ""
            if book.frozen_since and book.frozen_since != datetime.date.today():
                since_str = f"from {book.frozen_since.strftime('%b %d')} "
            console.print(
                f"  │ [yellow]FROZEN {since_str}until {book.frozen_until.strftime('%b %d')} "
                f"({days_left} days). Run:[/yellow] mtg unfreeze {book.id}"
            )
            continue

        has_content = any(
            due_info[k] for k in ["overdue", "due_today", "coming_up", "not_started"]
        )
        if not has_content:
            continue

        console.print(header)

        # Overdue
        if due_info["overdue"]:
            console.print("\n  [red bold]OVERDUE[/red bold]")
            for status in due_info["overdue"]:
                info = _format_due_today(status)
                console.print(
                    f"  │ [cyan]{status.topic.id:<12}[/cyan] {status.topic.title:<35} "
                    f"{info}  [{status.sessions_completed}/{status.sessions_total}]"
                )
                total_actionable += 1

        # Due today
        if due_info["due_today"]:
            console.print("\n  [yellow bold]DUE TODAY[/yellow bold]")
            for status in due_info["due_today"]:
                console.print(
                    f"  │ [cyan]{status.topic.id:<12}[/cyan] {status.topic.title:<35} "
                    f"  [{status.sessions_completed}/{status.sessions_total}]"
                )
                total_actionable += 1

        # Coming up
        if due_info["coming_up"]:
            console.print(f"\n  [dim bold]COMING UP (next {lookahead_days} day{'s' if lookahead_days != 1 else ''})[/dim bold]")
            for status in due_info["coming_up"]:
                info = _format_due_today(status)
                console.print(
                    f"  │ [dim cyan]{status.topic.id:<12}[/dim cyan] "
                    f"[dim]{status.topic.title:<35}[/dim] "
                    f"{info}  [{status.sessions_completed}/{status.sessions_total}]"
                )

        # Not started
        if due_info["not_started"]:
            console.print("\n  [dim bold]NEW (not yet started)[/dim bold]")
            for status in due_info["not_started"]:
                console.print(
                    f"  │ [dim cyan]{status.topic.id:<12}[/dim cyan] "
                    f"[dim]{status.topic.title}[/dim]"
                )

    if total_actionable > 0:
        console.print(
            f"\n  [bold]{total_actionable} topic{'s' if total_actionable != 1 else ''} "
            f"need{'s' if total_actionable == 1 else ''} attention today.[/bold] "
            f"Run: [cyan]mtg done <topic_id>[/cyan]\n"
        )
    elif not any(b.frozen for b in books):
        console.print("\n  [green]All clear! Nothing due today.[/green]\n")
    else:
        console.print()

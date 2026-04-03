"""CLI entry point for Mind the Gap."""

from __future__ import annotations

import re
import sys

import click

from mtg import __version__
from mtg.config import is_initialized
from mtg.display import console, display_all_books
from mtg.storage import (
    discover_books,
    list_book_ids,
    list_topic_ids_for_book,
    suggest_matches,
)


_VALID_ID_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")


# ── Shell completion helpers ─────────────────────────────────────────────


def _complete_book_id(ctx, param, incomplete):
    """Shell completion callback for book IDs."""
    try:
        return [bid for bid in list_book_ids() if bid.startswith(incomplete)]
    except Exception:
        return []


def _complete_topic_id(ctx, param, incomplete):
    """Shell completion callback for topic IDs (across all books)."""
    try:
        ids = []
        for book in discover_books():
            ids.extend(t.id for t in book.topics)
        return [tid for tid in sorted(set(ids)) if tid.startswith(incomplete)]
    except Exception:
        return []


# ── Shared helpers ───────────────────────────────────────────────────────


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


# ── Main CLI group ───────────────────────────────────────────────────────


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


# Register all sub-module commands -----------------------------------------
# The imports here trigger each module's @main.command() decorators.

from mtg.cli import core as _core  # noqa: F401, E402
from mtg.cli import book as _book  # noqa: F401, E402
from mtg.cli import study as _study  # noqa: F401, E402
from mtg.cli import schedule as _schedule  # noqa: F401, E402
from mtg.cli import admin as _admin  # noqa: F401, E402

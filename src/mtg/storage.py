"""Storage layer — reading and writing TOML files for books and sessions."""

from __future__ import annotations

import datetime
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

import toml

from mtg.config import ensure_data_dir, get_data_dir
from mtg.models import Book, Session, Topic


def _warn(message: str) -> None:
    """Print a warning to stderr."""
    print(f"  ⚠ {message}", file=sys.stderr)


def _atomic_write_toml(filepath: Path, data: dict) -> None:
    """Write a TOML file atomically using a temp file + os.replace().

    This prevents data corruption if the process is interrupted mid-write.
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=filepath.parent, suffix=".tmp", prefix=filepath.stem
    )
    try:
        with os.fdopen(fd, "w") as f:
            toml.dump(data, f)
        os.replace(tmp_path, filepath)
    except Exception:
        # Clean up the temp file if anything goes wrong
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _parse_date(value) -> Optional[datetime.date]:
    """Parse a date from TOML — handles both datetime.date and string."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, str) and value.strip():
        return datetime.date.fromisoformat(value.strip())
    return None


def _date_to_str(d: Optional[datetime.date]) -> str:
    """Convert a date to ISO string for TOML output."""
    if d is None:
        return ""
    return d.isoformat()


# --- Book loading / saving ---


def load_book(filepath: Path) -> Book:
    """Load a book (study plan) from a TOML file."""
    data = toml.load(filepath)
    book_data = data.get("book", {})

    book = Book(
        title=book_data.get("title", "Untitled"),
        id=book_data.get("id", "ch"),
        exam_date=_parse_date(book_data.get("exam_date")),
        sessions_per_topic=int(book_data.get("sessions_per_topic", 10)),
        frozen=bool(book_data.get("frozen", False)),
        frozen_since=_parse_date(book_data.get("frozen_since")),
        frozen_until=_parse_date(book_data.get("frozen_until")),
        filename=filepath.stem,
    )

    for topic_data in data.get("topic", []):
        topic = Topic(
            id=topic_data.get("id", ""),
            title=topic_data.get("title", ""),
            parent=topic_data.get("parent", ""),
        )
        book.topics.append(topic)

    return book


def save_book(book: Book, filepath: Path) -> None:
    """Save a book (study plan) to a TOML file."""
    data: dict = {
        "book": {
            "title": book.title,
            "id": book.id,
            "sessions_per_topic": book.sessions_per_topic,
            "frozen": book.frozen,
        },
        "topic": [],
    }

    if book.exam_date is not None:
        data["book"]["exam_date"] = _date_to_str(book.exam_date)

    if book.frozen_since is not None:
        data["book"]["frozen_since"] = _date_to_str(book.frozen_since)

    if book.frozen_until is not None:
        data["book"]["frozen_until"] = _date_to_str(book.frozen_until)

    for topic in book.topics:
        data["topic"].append(
            {
                "id": topic.id,
                "title": topic.title,
                "parent": topic.parent,
            }
        )

    _atomic_write_toml(filepath, data)


def get_book_path(book_slug: str) -> Path:
    """Get the path to a book's TOML file."""
    return get_data_dir() / f"{book_slug}.toml"


def get_state_path(book_slug: str) -> Path:
    """Get the path to a book's state TOML file."""
    return get_data_dir() / f"{book_slug}.state.toml"


# --- Session loading / saving ---


def load_sessions(book_slug: str) -> list[Session]:
    """Load all sessions for a book from its state file."""
    state_path = get_state_path(book_slug)
    if not state_path.exists():
        return []

    data = toml.load(state_path)
    sessions = []
    for s in data.get("session", []):
        session = Session(
            topic_id=s.get("topic_id", ""),
            book=s.get("book", book_slug),
            date=_parse_date(s.get("date")) or datetime.date.today(),
            confidence=int(s.get("confidence", 1)),
            next_due=_parse_date(s.get("next_due")) or datetime.date.today(),
            session_number=int(s.get("session_number", 1)),
        )
        sessions.append(session)
    return sessions


def save_sessions(book_slug: str, sessions: list[Session]) -> None:
    """Save all sessions for a book to its state file."""
    state_path = get_state_path(book_slug)
    data: dict = {"session": []}

    for s in sessions:
        data["session"].append(
            {
                "topic_id": s.topic_id,
                "book": s.book,
                "date": _date_to_str(s.date),
                "confidence": s.confidence,
                "next_due": _date_to_str(s.next_due),
                "session_number": s.session_number,
            }
        )

    _atomic_write_toml(state_path, data)


def append_session(book_slug: str, session: Session) -> None:
    """Append a single session to the book's state file."""
    sessions = load_sessions(book_slug)
    sessions.append(session)
    save_sessions(book_slug, sessions)


# --- Book discovery ---


def discover_books() -> list[Book]:
    """Find all book TOML files in the data directory."""
    data_dir = get_data_dir()
    if not data_dir.exists():
        return []

    books = []
    for filepath in sorted(data_dir.glob("*.toml")):
        # Skip state files and intervals.toml
        if filepath.name.endswith(".state.toml"):
            continue
        if filepath.name == "intervals.toml":
            continue
        try:
            book = load_book(filepath)
            books.append(book)
        except Exception as e:
            _warn(f"Skipping {filepath.name}: {e}")

    return books


def find_book_by_id(book_id: str) -> Optional[tuple[Book, Path]]:
    """Find a book by its book.id field. Returns (book, filepath) or None."""
    data_dir = get_data_dir()
    if not data_dir.exists():
        return None

    for filepath in sorted(data_dir.glob("*.toml")):
        if filepath.name.endswith(".state.toml") or filepath.name == "intervals.toml":
            continue
        try:
            book = load_book(filepath)
            if book.id == book_id:
                return (book, filepath)
        except Exception as e:
            _warn(f"Skipping {filepath.name}: {e}")

    return None


def delete_book_files(book_slug: str) -> list[Path]:
    """Delete a book's TOML and state files. Returns list of deleted paths."""
    deleted = []
    for path in [get_book_path(book_slug), get_state_path(book_slug)]:
        if path.exists():
            path.unlink()
            deleted.append(path)
    return deleted


def remove_topic_from_book(book: Book, topic_id: str) -> list[str]:
    """Remove a topic and its descendants from a book. Returns list of removed IDs."""
    # Collect the topic and all descendants
    to_remove = {topic_id}
    changed = True
    while changed:
        changed = False
        for t in book.topics:
            if t.parent in to_remove and t.id not in to_remove:
                to_remove.add(t.id)
                changed = True

    book.topics = [t for t in book.topics if t.id not in to_remove]

    # Fix orphaned parents: if a removed topic was someone's parent, clear it
    for t in book.topics:
        if t.parent in to_remove:
            t.parent = ""

    return sorted(to_remove)


def remove_sessions_for_topics(book_slug: str, topic_ids: set[str]) -> int:
    """Remove all sessions for the given topic IDs. Returns count removed."""
    sessions = load_sessions(book_slug)
    original_count = len(sessions)
    sessions = [s for s in sessions if s.topic_id not in topic_ids]
    save_sessions(book_slug, sessions)
    return original_count - len(sessions)


def pop_latest_session(book_slug: str, topic_id: str) -> Optional[Session]:
    """Remove and return the most recent session for a topic. Returns None if no sessions."""
    sessions = load_sessions(book_slug)
    topic_sessions = [(i, s) for i, s in enumerate(sessions) if s.topic_id == topic_id]
    if not topic_sessions:
        return None

    # Find the one with highest session_number (and latest date as tiebreaker)
    idx, latest = max(topic_sessions, key=lambda pair: (pair[1].session_number, pair[1].date))
    sessions.pop(idx)
    save_sessions(book_slug, sessions)
    return latest


def would_create_cycle(book: Book, topic_id: str, new_parent: str) -> bool:
    """Check if setting topic_id's parent to new_parent would create a cycle.

    Walks up the parent chain from new_parent; if it reaches topic_id,
    that's a cycle.
    """
    if not new_parent:
        return False  # becoming root can't create a cycle

    # Build a lookup of id → parent, with the proposed change applied
    parent_map = {t.id: t.parent for t in book.topics}
    parent_map[topic_id] = new_parent

    # Walk up from new_parent
    visited: set[str] = set()
    current = new_parent
    while current:
        if current in visited:
            return True  # found a cycle
        visited.add(current)
        current = parent_map.get(current, "")

    return topic_id in visited


def find_topic_across_books(topic_id: str) -> Optional[tuple[Book, Topic, Path]]:
    """Find which book a topic_id belongs to. Returns (book, topic, filepath) or None."""
    data_dir = get_data_dir()
    if not data_dir.exists():
        return None

    for filepath in sorted(data_dir.glob("*.toml")):
        if filepath.name.endswith(".state.toml") or filepath.name == "intervals.toml":
            continue
        try:
            book = load_book(filepath)
            for topic in book.topics:
                if topic.id == topic_id:
                    return (book, topic, filepath)
        except Exception as e:
            _warn(f"Skipping {filepath.name}: {e}")

    return None

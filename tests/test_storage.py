"""Tests for the storage layer."""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

import pytest

from mtg.models import Book, Session, Topic
from mtg.storage import load_book, load_sessions, save_book, save_sessions, would_create_cycle


class TestBookIO:
    def test_roundtrip(self, tmp_path: Path):
        """Save a book and load it back — should be identical."""
        book = Book(
            title="Test Book",
            id="tb",
            exam_date=datetime.date(2026, 7, 15),
            sessions_per_topic=8,
            frozen=False,
            frozen_until=None,
            filename="test-book",
            topics=[
                Topic(id="tb1", title="Chapter 1", parent=""),
                Topic(id="tb1.1", title="Topic 1.1", parent="tb1"),
                Topic(id="tb1.2", title="Topic 1.2", parent="tb1"),
            ],
        )

        filepath = tmp_path / "test-book.toml"
        save_book(book, filepath)
        loaded = load_book(filepath)

        assert loaded.title == book.title
        assert loaded.id == book.id
        assert loaded.exam_date == book.exam_date
        assert loaded.sessions_per_topic == book.sessions_per_topic
        assert loaded.frozen == book.frozen
        assert len(loaded.topics) == 3
        assert loaded.topics[0].id == "tb1"
        assert loaded.topics[1].parent == "tb1"

    def test_frozen_book(self, tmp_path: Path):
        """Frozen state should persist."""
        book = Book(
            title="Frozen Book",
            id="fb",
            frozen=True,
            frozen_until=datetime.date(2026, 5, 1),
            filename="frozen-book",
            topics=[Topic(id="fb1", title="Topic", parent="")],
        )

        filepath = tmp_path / "frozen-book.toml"
        save_book(book, filepath)
        loaded = load_book(filepath)

        assert loaded.frozen is True
        assert loaded.frozen_until == datetime.date(2026, 5, 1)

    def test_frozen_since_roundtrip(self, tmp_path: Path):
        """frozen_since should persist through save/load."""
        book = Book(
            title="Frozen Book",
            id="fb",
            frozen=True,
            frozen_since=datetime.date(2026, 3, 20),
            frozen_until=datetime.date(2026, 4, 10),
            filename="frozen-since",
            topics=[Topic(id="fb1", title="Topic", parent="")],
        )

        filepath = tmp_path / "frozen-since.toml"
        save_book(book, filepath)
        loaded = load_book(filepath)

        assert loaded.frozen is True
        assert loaded.frozen_since == datetime.date(2026, 3, 20)
        assert loaded.frozen_until == datetime.date(2026, 4, 10)

    def test_frozen_since_omitted_when_none(self, tmp_path: Path):
        """frozen_since should not appear in TOML when None."""
        book = Book(
            title="Unfrozen Book",
            id="ub",
            frozen=False,
            frozen_since=None,
            frozen_until=None,
            filename="unfrozen",
            topics=[Topic(id="ub1", title="Topic", parent="")],
        )

        filepath = tmp_path / "unfrozen.toml"
        save_book(book, filepath)

        # Read raw TOML to verify keys are absent
        import toml as toml_lib
        raw = toml_lib.load(filepath)
        assert "frozen_since" not in raw["book"]
        assert "frozen_until" not in raw["book"]

        loaded = load_book(filepath)
        assert loaded.frozen_since is None
        assert loaded.frozen_until is None

    def test_no_exam_date(self, tmp_path: Path):
        """Book without exam date should work."""
        book = Book(title="No Exam", id="ne", filename="no-exam")
        filepath = tmp_path / "no-exam.toml"
        save_book(book, filepath)
        loaded = load_book(filepath)
        assert loaded.exam_date is None


class TestSessionIO:
    def test_roundtrip(self, tmp_path: Path, monkeypatch):
        """Save sessions and load them back."""
        monkeypatch.setattr("mtg.storage.get_data_dir", lambda: tmp_path)

        sessions = [
            Session(
                topic_id="tb1.1",
                book="test-book",
                date=datetime.date(2026, 3, 25),
                confidence=5,
                next_due=datetime.date(2026, 3, 30),
                session_number=1,
            ),
            Session(
                topic_id="tb1.1",
                book="test-book",
                date=datetime.date(2026, 3, 30),
                confidence=7,
                next_due=datetime.date(2026, 4, 9),
                session_number=2,
            ),
        ]

        save_sessions("test-book", sessions)
        loaded = load_sessions("test-book")

        assert len(loaded) == 2
        assert loaded[0].topic_id == "tb1.1"
        assert loaded[0].confidence == 5
        assert loaded[1].session_number == 2
        assert loaded[1].next_due == datetime.date(2026, 4, 9)

    def test_empty_state(self, tmp_path: Path, monkeypatch):
        """Loading from nonexistent state file returns empty list."""
        monkeypatch.setattr("mtg.storage.get_data_dir", lambda: tmp_path)
        sessions = load_sessions("nonexistent")
        assert sessions == []


class TestCycleDetection:
    def test_direct_cycle(self):
        """A→B, then setting B's parent to A should be a cycle."""
        book = Book(
            title="Test", id="t", filename="test",
            topics=[
                Topic(id="t1", title="A", parent=""),
                Topic(id="t2", title="B", parent="t1"),
            ],
        )
        assert would_create_cycle(book, "t1", "t2") is True

    def test_indirect_cycle(self):
        """A→B→C, then setting C's parent to A creates A→B→C→A."""
        book = Book(
            title="Test", id="t", filename="test",
            topics=[
                Topic(id="t1", title="A", parent=""),
                Topic(id="t2", title="B", parent="t1"),
                Topic(id="t3", title="C", parent="t2"),
            ],
        )
        # Setting t1's parent to t3 would create t1→t3→t2→t1
        assert would_create_cycle(book, "t1", "t3") is True

    def test_no_cycle(self):
        """Moving a topic to a different subtree is fine."""
        book = Book(
            title="Test", id="t", filename="test",
            topics=[
                Topic(id="t1", title="A", parent=""),
                Topic(id="t2", title="B", parent="t1"),
                Topic(id="t3", title="C", parent=""),
            ],
        )
        assert would_create_cycle(book, "t2", "t3") is False

    def test_root_no_cycle(self):
        """Setting parent to empty (root) can never create a cycle."""
        book = Book(
            title="Test", id="t", filename="test",
            topics=[
                Topic(id="t1", title="A", parent=""),
                Topic(id="t2", title="B", parent="t1"),
            ],
        )
        assert would_create_cycle(book, "t2", "") is False

    def test_self_reference(self):
        """Setting a topic's parent to itself is a cycle."""
        book = Book(
            title="Test", id="t", filename="test",
            topics=[
                Topic(id="t1", title="A", parent=""),
            ],
        )
        assert would_create_cycle(book, "t1", "t1") is True

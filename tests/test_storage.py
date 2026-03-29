"""Tests for the storage layer."""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

import pytest

from mtg.models import Book, Session, Topic
from mtg.storage import load_book, load_sessions, save_book, save_sessions


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

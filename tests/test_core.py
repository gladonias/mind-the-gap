"""Tests for Mind the Gap core logic."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from mtg.config import DEFAULT_INTERVALS
from mtg.models import Book, ChapterStatus, Session, Topic, TopicStatus
from mtg.scheduler import (
    build_book_tree,
    compute_book_progress,
    compute_chapter_status,
    compute_next_due,
    compute_topic_status,
    count_frozen_affected,
    count_sessions,
    get_due_topics,
    get_latest_session,
    parse_duration,
    parse_freeze_target,
)


# --- Fixtures ---


def make_book(**kwargs) -> Book:
    """Helper to create a book with sensible defaults."""
    defaults = {
        "title": "Test Book",
        "id": "tb",
        "sessions_per_topic": 5,
        "filename": "test-book",
        "topics": [
            Topic(id="tb1", title="Chapter 1", parent=""),
            Topic(id="tb1.1", title="Topic 1.1", parent="tb1"),
            Topic(id="tb1.2", title="Topic 1.2", parent="tb1"),
            Topic(id="tb2", title="Chapter 2", parent=""),
            Topic(id="tb2.1", title="Topic 2.1", parent="tb2"),
            Topic(id="tb2.2", title="Topic 2.2", parent="tb2"),
            Topic(id="tb2.3", title="Topic 2.3", parent="tb2"),
        ],
    }
    defaults.update(kwargs)
    return Book(**defaults)


def make_session(topic_id: str, session_number: int = 1, confidence: int = 5, **kwargs) -> Session:
    """Helper to create a session."""
    today = datetime.date.today()
    defaults = {
        "topic_id": topic_id,
        "book": "test-book",
        "date": today,
        "confidence": confidence,
        "next_due": today + datetime.timedelta(days=DEFAULT_INTERVALS.get(confidence, 5)),
        "session_number": session_number,
    }
    defaults.update(kwargs)
    return Session(**defaults)


# --- parse_duration tests ---


class TestParseDuration:
    def test_days(self):
        assert parse_duration("10D") == datetime.timedelta(days=10)

    def test_weeks(self):
        assert parse_duration("2W") == datetime.timedelta(weeks=2)

    def test_months(self):
        assert parse_duration("3M") == datetime.timedelta(days=90)

    def test_years(self):
        assert parse_duration("1Y") == datetime.timedelta(days=365)

    def test_lowercase(self):
        assert parse_duration("5d") == datetime.timedelta(days=5)

    def test_large_number(self):
        assert parse_duration("100D") == datetime.timedelta(days=100)

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_duration("abc")

    def test_missing_unit(self):
        with pytest.raises(ValueError):
            parse_duration("10")

    def test_missing_number(self):
        with pytest.raises(ValueError):
            parse_duration("D")

    def test_invalid_unit(self):
        with pytest.raises(ValueError):
            parse_duration("5X")


# --- parse_freeze_target tests ---


class TestParseFreezeTarget:
    def test_iso_date(self):
        result = parse_freeze_target("2026-12-25")
        assert result == datetime.date(2026, 12, 25)

    def test_duration(self):
        result = parse_freeze_target("2W")
        expected = datetime.date.today() + datetime.timedelta(weeks=2)
        assert result == expected


# --- compute_next_due tests ---


class TestComputeNextDue:
    def test_confidence_1(self):
        study_date = datetime.date(2026, 3, 28)
        result = compute_next_due(study_date, 1)
        assert result == datetime.date(2026, 3, 29)  # 1 day

    def test_confidence_5(self):
        study_date = datetime.date(2026, 3, 28)
        result = compute_next_due(study_date, 5)
        assert result == datetime.date(2026, 4, 2)  # 5 days

    def test_confidence_10(self):
        study_date = datetime.date(2026, 3, 28)
        result = compute_next_due(study_date, 10)
        assert result == datetime.date(2026, 4, 18)  # 21 days


# --- Book model tests ---


class TestBookModel:
    def test_leaf_topics(self):
        book = make_book()
        leaves = book.leaf_topics()
        leaf_ids = {t.id for t in leaves}
        assert leaf_ids == {"tb1.1", "tb1.2", "tb2.1", "tb2.2", "tb2.3"}

    def test_top_level_topics(self):
        book = make_book()
        top = book.top_level_topics()
        assert len(top) == 2
        assert top[0].id == "tb1"
        assert top[1].id == "tb2"

    def test_children_of(self):
        book = make_book()
        children = book.children_of("tb2")
        assert len(children) == 3

    def test_all_descendants(self):
        book = make_book()
        desc = book.all_descendants("tb1")
        assert len(desc) == 2

    def test_default_id(self):
        book = Book(title="Test", filename="test")
        assert book.id == "ch"

    def test_default_sessions(self):
        book = Book(title="Test", filename="test")
        assert book.sessions_per_topic == 10


# --- Session helpers ---


class TestSessionHelpers:
    def test_count_sessions(self):
        sessions = [
            make_session("tb1.1", session_number=1),
            make_session("tb1.1", session_number=2),
            make_session("tb1.2", session_number=1),
        ]
        assert count_sessions("tb1.1", sessions) == 2
        assert count_sessions("tb1.2", sessions) == 1
        assert count_sessions("tb2.1", sessions) == 0

    def test_get_latest_session(self):
        sessions = [
            make_session("tb1.1", session_number=1, confidence=3),
            make_session("tb1.1", session_number=2, confidence=7),
        ]
        latest = get_latest_session("tb1.1", sessions)
        assert latest is not None
        assert latest.session_number == 2
        assert latest.confidence == 7

    def test_get_latest_session_none(self):
        assert get_latest_session("nonexistent", []) is None


# --- Topic status ---


class TestTopicStatus:
    def test_not_started(self):
        book = make_book()
        topic = book.topics[1]  # tb1.1
        status = compute_topic_status(topic, [], 5, book)
        assert status.is_not_started
        assert status.sessions_completed == 0
        assert status.next_due is None

    def test_in_progress(self):
        book = make_book()
        topic = book.topics[1]  # tb1.1
        today = datetime.date.today()
        sessions = [
            make_session("tb1.1", session_number=1, confidence=5),
            make_session("tb1.1", session_number=2, confidence=6),
        ]
        status = compute_topic_status(topic, sessions, 5, book)
        assert status.sessions_completed == 2
        assert not status.is_done
        assert status.next_due is not None

    def test_done(self):
        book = make_book()
        topic = book.topics[1]  # tb1.1
        sessions = [make_session("tb1.1", session_number=i) for i in range(1, 6)]
        status = compute_topic_status(topic, sessions, 5, book)
        assert status.is_done
        assert status.sessions_completed == 5

    def test_overdue(self):
        book = make_book()
        topic = book.topics[1]
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        sessions = [
            Session(
                topic_id="tb1.1",
                book="test-book",
                date=yesterday - datetime.timedelta(days=5),
                confidence=1,
                next_due=yesterday,
                session_number=1,
            )
        ]
        status = compute_topic_status(topic, sessions, 5, book)
        assert status.is_overdue
        assert status.days_overdue == 1


# --- Chapter status (hierarchical progress) ---


class TestChapterStatus:
    def test_empty_chapter(self):
        book = make_book()
        chapter = book.topics[0]  # tb1
        status = compute_chapter_status(chapter, book, [])
        assert status.sessions_completed == 0
        assert status.sessions_total == 10  # 2 topics × 5 sessions

    def test_partial_progress(self):
        book = make_book()
        chapter = book.topics[3]  # tb2 (3 children)
        sessions = [
            make_session("tb2.1", session_number=1),
            make_session("tb2.1", session_number=2),
            make_session("tb2.2", session_number=1),
            make_session("tb2.2", session_number=2),
            make_session("tb2.3", session_number=1),
        ]
        status = compute_chapter_status(chapter, book, sessions)
        assert status.sessions_completed == 5
        assert status.sessions_total == 15  # 3 topics × 5 sessions
        assert not status.is_done

    def test_complete_chapter(self):
        book = make_book()
        chapter = book.topics[0]  # tb1 (2 children)
        sessions = []
        for i in range(1, 6):
            sessions.append(make_session("tb1.1", session_number=i))
            sessions.append(make_session("tb1.2", session_number=i))
        status = compute_chapter_status(chapter, book, sessions)
        assert status.sessions_completed == 10
        assert status.sessions_total == 10
        assert status.is_done


# --- Build book tree ---


class TestBuildBookTree:
    def test_tree_structure(self):
        book = make_book()
        tree = build_book_tree(book, [])
        assert len(tree) == 2  # 2 top-level chapters
        assert isinstance(tree[0], ChapterStatus)
        assert isinstance(tree[1], ChapterStatus)

    def test_flat_book(self):
        """Book with no hierarchy — all topics are top-level."""
        book = Book(
            title="Flat",
            id="fl",
            sessions_per_topic=3,
            filename="flat",
            topics=[
                Topic(id="fl1", title="Topic 1", parent=""),
                Topic(id="fl2", title="Topic 2", parent=""),
            ],
        )
        tree = build_book_tree(book, [])
        assert len(tree) == 2
        assert all(isinstance(n, TopicStatus) for n in tree)


# --- Due topics ---


class TestDueTopics:
    def test_overdue(self):
        book = make_book()
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        sessions = [
            Session(
                topic_id="tb1.1",
                book="test-book",
                date=yesterday - datetime.timedelta(days=5),
                confidence=1,
                next_due=yesterday,
                session_number=1,
            )
        ]
        due = get_due_topics(book, sessions)
        overdue_ids = {s.topic.id for s in due["overdue"]}
        assert "tb1.1" in overdue_ids

    def test_not_started_listed(self):
        book = make_book()
        due = get_due_topics(book, [])
        not_started_ids = {s.topic.id for s in due["not_started"]}
        assert len(not_started_ids) == 5  # all leaf topics


# --- Book progress ---


class TestBookProgress:
    def test_zero_progress(self):
        book = make_book()
        completed, total = compute_book_progress(book, [])
        assert completed == 0
        assert total == 25  # 5 leaves × 5 sessions

    def test_partial_progress(self):
        book = make_book()
        sessions = [
            make_session("tb1.1", session_number=1),
            make_session("tb2.1", session_number=1),
        ]
        completed, total = compute_book_progress(book, sessions)
        assert completed == 2
        assert total == 25


# --- Freeze logic ---


class TestFreezeLogic:
    def test_frozen_topic_due_pushed(self):
        """Topics due before unfreeze date should show unfreeze date."""
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        unfreeze = datetime.date.today() + datetime.timedelta(days=14)

        book = make_book(frozen=True, frozen_until=unfreeze)
        sessions = [
            Session(
                topic_id="tb1.1",
                book="test-book",
                date=datetime.date.today() - datetime.timedelta(days=5),
                confidence=1,
                next_due=tomorrow,
                session_number=1,
            )
        ]
        status = compute_topic_status(book.topics[1], sessions, 5, book)
        assert status.next_due == unfreeze

    def test_frozen_topic_due_after_unfreeze_unchanged(self):
        """Topics due after unfreeze date should not be moved."""
        unfreeze = datetime.date.today() + datetime.timedelta(days=14)
        far_future = datetime.date.today() + datetime.timedelta(days=30)

        book = make_book(frozen=True, frozen_until=unfreeze)
        sessions = [
            Session(
                topic_id="tb1.1",
                book="test-book",
                date=datetime.date.today() - datetime.timedelta(days=5),
                confidence=10,
                next_due=far_future,
                session_number=1,
            )
        ]
        status = compute_topic_status(book.topics[1], sessions, 5, book)
        assert status.next_due == far_future  # unchanged

    def test_count_frozen_affected(self):
        unfreeze = datetime.date.today() + datetime.timedelta(days=14)
        book = make_book()
        sessions = [
            Session(
                topic_id="tb1.1",
                book="test-book",
                date=datetime.date.today() - datetime.timedelta(days=5),
                confidence=1,
                next_due=datetime.date.today() + datetime.timedelta(days=1),
                session_number=1,
            ),
            Session(
                topic_id="tb1.2",
                book="test-book",
                date=datetime.date.today() - datetime.timedelta(days=5),
                confidence=10,
                next_due=datetime.date.today() + datetime.timedelta(days=30),
                session_number=1,
            ),
        ]
        affected, unaffected = count_frozen_affected(book, sessions, unfreeze)
        assert affected == 1
        assert unaffected == 1

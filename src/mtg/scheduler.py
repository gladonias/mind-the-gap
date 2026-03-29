"""Scheduler — computes topic statuses, handles freeze logic, and schedules reviews."""

from __future__ import annotations

import datetime
import re
from typing import Optional

from mtg.config import load_intervals
from mtg.models import Book, ChapterStatus, Session, Topic, TopicStatus
from mtg.storage import load_sessions


def parse_duration(duration_str: str) -> datetime.timedelta:
    """Parse a duration string like '2W', '10D', '3M', '1Y' into a timedelta.

    Supported suffixes: D (days), W (weeks), M (months), Y (years).
    Months are approximated as 30 days, years as 365 days.
    """
    match = re.match(r"^(\d+)([DWMY])$", duration_str.upper())
    if not match:
        raise ValueError(
            f"Invalid duration format: '{duration_str}'. "
            "Use a number followed by D (days), W (weeks), M (months), or Y (years). "
            "Examples: 10D, 2W, 3M, 1Y"
        )

    amount = int(match.group(1))
    unit = match.group(2)

    if unit == "D":
        return datetime.timedelta(days=amount)
    elif unit == "W":
        return datetime.timedelta(weeks=amount)
    elif unit == "M":
        return datetime.timedelta(days=amount * 30)
    elif unit == "Y":
        return datetime.timedelta(days=amount * 365)
    else:
        raise ValueError(f"Unknown duration unit: {unit}")


def is_absolute_date(duration_or_date: str) -> bool:
    """Check if the string is an absolute ISO date (YYYY-MM-DD)."""
    try:
        datetime.date.fromisoformat(duration_or_date)
        return True
    except ValueError:
        return False


def parse_freeze_target(
    duration_or_date: str, start_date: Optional[datetime.date] = None
) -> datetime.date:
    """Parse either a duration string or an ISO date into a target date.

    If a duration is given (e.g. '2W'), it is computed relative to start_date
    (defaults to today if not provided).
    """
    if start_date is None:
        start_date = datetime.date.today()

    # Try as ISO date first
    try:
        return datetime.date.fromisoformat(duration_or_date)
    except ValueError:
        pass

    # Try as duration — relative to start_date
    delta = parse_duration(duration_or_date)
    return start_date + delta


def compute_next_due(study_date: datetime.date, confidence: int) -> datetime.date:
    """Calculate the next review date based on study date and confidence level."""
    intervals = load_intervals()
    days = intervals.get(confidence, confidence)  # fallback to confidence value if missing
    return study_date + datetime.timedelta(days=days)


def get_latest_session(topic_id: str, sessions: list[Session]) -> Optional[Session]:
    """Get the most recent session for a given topic."""
    topic_sessions = [s for s in sessions if s.topic_id == topic_id]
    if not topic_sessions:
        return None
    return max(topic_sessions, key=lambda s: (s.session_number, s.date))


def count_sessions(topic_id: str, sessions: list[Session]) -> int:
    """Count the number of completed sessions for a topic."""
    return len([s for s in sessions if s.topic_id == topic_id])


def compute_topic_status(
    topic: Topic,
    sessions: list[Session],
    sessions_per_topic: int,
    book: Book,
) -> TopicStatus:
    """Compute the current status of a leaf topic."""
    completed = count_sessions(topic.id, sessions)
    latest = get_latest_session(topic.id, sessions)

    is_done = completed >= sessions_per_topic
    next_due: Optional[datetime.date] = None

    if latest and not is_done:
        next_due = latest.next_due
        # Apply freeze logic: if frozen and due before unfreeze date, push to unfreeze date
        if book.frozen and book.frozen_until and next_due <= book.frozen_until:
            next_due = book.frozen_until

    return TopicStatus(
        topic=topic,
        sessions_completed=completed,
        sessions_total=sessions_per_topic,
        next_due=next_due,
        last_confidence=latest.confidence if latest else None,
        is_done=is_done,
    )


def compute_chapter_status(
    chapter: Topic,
    book: Book,
    sessions: list[Session],
) -> ChapterStatus:
    """Compute the aggregated status of a chapter from its descendants."""
    descendants = book.all_descendants(chapter.id)

    if not descendants:
        # Chapter has no children — treat it as a leaf
        topic_status = compute_topic_status(chapter, sessions, book.sessions_per_topic, book)
        return ChapterStatus(
            topic=chapter,
            sessions_completed=topic_status.sessions_completed,
            sessions_total=topic_status.sessions_total,
            is_done=topic_status.is_done,
            children=[topic_status],
        )

    total_completed = 0
    total_possible = 0
    children_statuses: list[TopicStatus | ChapterStatus] = []

    for child in book.children_of(chapter.id):
        child_children = book.children_of(child.id)
        if child_children:
            # This child is itself a chapter — recurse
            child_status = compute_chapter_status(child, book, sessions)
            children_statuses.append(child_status)
            total_completed += child_status.sessions_completed
            total_possible += child_status.sessions_total
        else:
            # This child is a leaf topic
            topic_status = compute_topic_status(
                child, sessions, book.sessions_per_topic, book
            )
            children_statuses.append(topic_status)
            total_completed += topic_status.sessions_completed
            total_possible += topic_status.sessions_total

    return ChapterStatus(
        topic=chapter,
        sessions_completed=total_completed,
        sessions_total=total_possible,
        is_done=total_completed >= total_possible,
        children=children_statuses,
    )


def build_book_tree(
    book: Book,
    sessions: list[Session],
) -> list[TopicStatus | ChapterStatus]:
    """Build the full hierarchical status tree for a book."""
    result: list[TopicStatus | ChapterStatus] = []

    for topic in book.top_level_topics():
        children = book.children_of(topic.id)
        if children:
            result.append(compute_chapter_status(topic, book, sessions))
        else:
            result.append(
                compute_topic_status(topic, sessions, book.sessions_per_topic, book)
            )

    return result


def get_due_topics(
    book: Book,
    sessions: list[Session],
    include_future_days: int = 3,
) -> dict[str, list[TopicStatus]]:
    """Get topics organized by urgency: overdue, due_today, coming_up, not_started.

    Only returns leaf topics (things you can actually study).
    """
    today = datetime.date.today()
    cutoff = today + datetime.timedelta(days=include_future_days)

    overdue: list[TopicStatus] = []
    due_today: list[TopicStatus] = []
    coming_up: list[TopicStatus] = []
    not_started: list[TopicStatus] = []

    for topic in book.leaf_topics():
        status = compute_topic_status(topic, sessions, book.sessions_per_topic, book)

        if status.is_done:
            continue

        if status.is_not_started:
            not_started.append(status)
        elif status.next_due is not None:
            if status.next_due < today:
                overdue.append(status)
            elif status.next_due == today:
                due_today.append(status)
            elif status.next_due <= cutoff:
                coming_up.append(status)

    # Sort overdue by priority: weight days overdue by low confidence
    # urgency = days_overdue × (11 - confidence), so low confidence + many days = top priority
    def _overdue_priority(s: TopicStatus) -> float:
        days = (today - (s.next_due or today)).days
        confidence_weight = 11 - (s.last_confidence or 1)
        return -(days * confidence_weight)  # negative for descending sort

    overdue.sort(key=_overdue_priority)
    # Sort coming up by soonest first
    coming_up.sort(key=lambda s: s.next_due or today)

    return {
        "overdue": overdue,
        "due_today": due_today,
        "coming_up": coming_up,
        "not_started": not_started,
    }


def compute_book_progress(book: Book, sessions: list[Session]) -> tuple[int, int]:
    """Compute total progress across all leaf topics: (completed, total)."""
    leaves = book.leaf_topics()
    total_completed = sum(count_sessions(t.id, sessions) for t in leaves)
    total_possible = len(leaves) * book.sessions_per_topic
    return total_completed, total_possible


def count_actionable(book: Book, sessions: list[Session]) -> int:
    """Count topics that are overdue or due today."""
    today = datetime.date.today()
    count = 0
    for topic in book.leaf_topics():
        status = compute_topic_status(topic, sessions, book.sessions_per_topic, book)
        if status.is_done:
            continue
        if status.next_due is not None and status.next_due <= today:
            count += 1
    return count


def count_frozen_affected(
    book: Book,
    sessions: list[Session],
    until: datetime.date,
    since: Optional[datetime.date] = None,
) -> tuple[int, int]:
    """Count sessions affected vs unaffected by freezing until a given date.

    Returns (affected_count, unaffected_count).
    Affected = next_due is between `since` (inclusive) and `until` (inclusive).
    Unaffected = next_due is after the unfreeze date.
    If `since` is None, defaults to today.
    """
    if since is None:
        since = datetime.date.today()

    affected = 0
    unaffected = 0

    for topic in book.leaf_topics():
        status = compute_topic_status(topic, sessions, book.sessions_per_topic, book)
        if status.is_done or status.is_not_started:
            continue
        if status.next_due is not None:
            if since <= status.next_due <= until:
                affected += 1
            elif status.next_due < since:
                # Was already overdue before the freeze started — still affected
                affected += 1
            else:
                unaffected += 1

    return affected, unaffected

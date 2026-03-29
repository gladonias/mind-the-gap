"""Data models for Mind the Gap."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Topic:
    """A single study topic within a book."""

    id: str
    title: str
    parent: str = ""

    @property
    def is_root(self) -> bool:
        return self.parent == ""

    @property
    def depth(self) -> int:
        """Number of dots in the id indicates depth (e.g., clrs4.1.2 → 2)."""
        # Depth is determined by the number of '.' after the prefix
        parts = self.id.split(".")
        return len(parts) - 1


@dataclass
class Book:
    """A study plan for a single book/course."""

    title: str
    id: str = "ch"
    exam_date: Optional[datetime.date] = None
    sessions_per_topic: int = 10
    frozen: bool = False
    frozen_until: Optional[datetime.date] = None
    topics: list[Topic] = field(default_factory=list)
    filename: str = ""  # the file this was loaded from (without path)

    def leaf_topics(self) -> list[Topic]:
        """Return topics that have no children (actual study units)."""
        parent_ids = {t.parent for t in self.topics}
        return [t for t in self.topics if t.id not in parent_ids]

    def children_of(self, parent_id: str) -> list[Topic]:
        """Return direct children of a given topic/chapter."""
        return [t for t in self.topics if t.parent == parent_id]

    def all_descendants(self, parent_id: str) -> list[Topic]:
        """Return all descendants (recursive) that are leaf topics."""
        leaves = []
        for topic in self.topics:
            if topic.parent == parent_id:
                # Check if this topic is itself a parent
                children = self.children_of(topic.id)
                if children:
                    leaves.extend(self.all_descendants(topic.id))
                else:
                    leaves.append(topic)
        return leaves

    def top_level_topics(self) -> list[Topic]:
        """Return topics with no parent (chapters or standalone topics)."""
        return [t for t in self.topics if t.is_root]


@dataclass
class Session:
    """A single completed study session."""

    topic_id: str
    book: str  # book filename slug
    date: datetime.date = field(default_factory=datetime.date.today)
    confidence: int = 1
    next_due: datetime.date = field(default_factory=datetime.date.today)
    session_number: int = 1


@dataclass
class TopicStatus:
    """Derived status of a topic based on session history."""

    topic: Topic
    sessions_completed: int
    sessions_total: int
    next_due: Optional[datetime.date]
    last_confidence: Optional[int]
    is_done: bool

    @property
    def days_overdue(self) -> int:
        if self.next_due is None:
            return 0
        delta = (datetime.date.today() - self.next_due).days
        return max(0, delta)

    @property
    def is_overdue(self) -> bool:
        return self.next_due is not None and self.next_due < datetime.date.today()

    @property
    def is_due_today(self) -> bool:
        return self.next_due is not None and self.next_due == datetime.date.today()

    @property
    def is_not_started(self) -> bool:
        return self.sessions_completed == 0


@dataclass
class ChapterStatus:
    """Derived status of a chapter (aggregated from children)."""

    topic: Topic
    sessions_completed: int
    sessions_total: int
    is_done: bool
    children: list[TopicStatus | ChapterStatus] = field(default_factory=list)

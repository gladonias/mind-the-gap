"""Configuration and path management for Mind the Gap."""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

import toml

# Default confidence descriptions shown during `mtg done`
CONFIDENCE_DESCRIPTIONS: dict[int, str] = {
    1: "I've seen these words before but couldn't tell you what they mean",
    2: "I recognize the topic and maybe one or two key terms, but couldn't explain anything about it",
    3: "I understand the basic definition but couldn't explain how it works or why it matters",
    4: "I can describe what it is in simple terms but would struggle with follow-up questions",
    5: "I understand the main idea and could give a basic explanation, but I'd miss important details or nuances",
    6: "I can explain the core concept clearly and answer straightforward questions about it",
    7: "I can explain it to others, provide examples, and answer most questions confidently",
    8: "I understand how this connects to related concepts and can apply it in different contexts",
    9: "I could teach this effectively, explain common misconceptions, and handle challenging questions",
    10: "I have expert-level understanding — I could create new examples, critique explanations, and explain subtle distinctions",
}

# Default intervals (confidence → days until next review)
DEFAULT_INTERVALS: dict[int, int] = {
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    6: 7,
    7: 10,
    8: 14,
    9: 17,
    10: 21,
}

DEFAULT_INTERVALS_TOML = """# Mind the Gap — Confidence-to-Days Mapping
# Edit freely — the app reads this every time it schedules a review.
#
# Format: confidence_level = number_of_days_until_next_review
#
# Confidence descriptions:
#  1  = I've seen these words before but couldn't tell you what they mean
#  2  = I recognize the topic and maybe one or two key terms
#  3  = I understand the basic definition but couldn't explain how it works
#  4  = I can describe what it is in simple terms
#  5  = I understand the main idea but I'd miss important details
#  6  = I can explain the core concept clearly
#  7  = I can explain it to others and answer most questions confidently
#  8  = I understand connections to related concepts and can apply it
#  9  = I could teach this effectively and handle challenging questions
#  10 = Expert-level understanding

[intervals]
1 = 1
2 = 2
3 = 3
4 = 4
5 = 5
6 = 7
7 = 10
8 = 14
9 = 17
10 = 21
"""


def get_config_dir() -> Path:
    """Return the platform-appropriate config directory."""
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "mtg"
    elif system == "Darwin":
        return Path.home() / ".config" / "mtg"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        if xdg:
            return Path(xdg) / "mtg"
        return Path.home() / ".config" / "mtg"


def get_default_data_dir() -> Path:
    """Return the default data directory (~/Documents/mind-the-gap)."""
    return Path.home() / "Documents" / "mind-the-gap"


def get_config_path() -> Path:
    """Return the path to the config file."""
    return get_config_dir() / "config.toml"


def load_config() -> dict:
    """Load configuration from config.toml."""
    config_path = get_config_path()
    if config_path.exists():
        return toml.load(config_path)
    return {}


def save_config(config: dict) -> None:
    """Save configuration to config.toml."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        toml.dump(config, f)


def get_data_dir() -> Path:
    """Get the configured data directory, or the default."""
    config = load_config()
    data_dir = config.get("data_dir", "")
    if data_dir:
        return Path(data_dir)
    return get_default_data_dir()


def ensure_data_dir() -> Path:
    """Ensure the data directory exists and return its path."""
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_intervals_path() -> Path:
    """Return path to the intervals.toml file."""
    return get_data_dir() / "intervals.toml"


_intervals_cache: dict[int, int] | None = None


def load_intervals() -> dict[int, int]:
    """Load the confidence-to-days interval mapping.

    The result is cached after the first call. Use clear_intervals_cache()
    to force a reload (e.g. in tests).
    """
    global _intervals_cache
    if _intervals_cache is not None:
        return _intervals_cache

    intervals_path = get_intervals_path()
    if intervals_path.exists():
        data = toml.load(intervals_path)
        raw = data.get("intervals", {})
        # TOML keys are strings, convert to int→int
        _intervals_cache = {int(k): int(v) for k, v in raw.items()}
    else:
        _intervals_cache = DEFAULT_INTERVALS.copy()

    return _intervals_cache


def clear_intervals_cache() -> None:
    """Clear the cached intervals so the next load_intervals() re-reads the file."""
    global _intervals_cache
    _intervals_cache = None


def ensure_intervals_file() -> None:
    """Create intervals.toml if it doesn't exist."""
    intervals_path = get_intervals_path()
    if not intervals_path.exists():
        with open(intervals_path, "w") as f:
            f.write(DEFAULT_INTERVALS_TOML)


def is_initialized() -> bool:
    """Check if Mind the Gap has been initialized."""
    config_path = get_config_path()
    return config_path.exists()

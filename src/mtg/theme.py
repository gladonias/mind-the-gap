"""Theme constants for terminal rendering."""

from __future__ import annotations

# ── Progress bar ──────────────────────────────────────────────────────────
PROGRESS_FILLED = "\u2588"  # █
PROGRESS_EMPTY = "\u2591"   # ░
PROGRESS_WIDTH = 10

# ── Layout widths ─────────────────────────────────────────────────────────
TITLE_WRAP_WIDTH = 30

# ── Confidence colours (Rich markup) ─────────────────────────────────────
# Maps confidence level (1–10) to a Rich colour name.
CONFIDENCE_COLOURS: dict[int, str] = {
    1: "red",
    2: "red",
    3: "bright_red",
    4: "dark_orange",
    5: "yellow",
    6: "yellow",
    7: "green",
    8: "green",
    9: "bright_green",
    10: "bright_green",
}

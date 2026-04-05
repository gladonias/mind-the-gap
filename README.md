# Mind the Gap

A spaced repetition study planner that runs in your terminal. No accounts, no cloud, no flashcards — just a simple system that tells you what to review and when.

## What this is (and isn't)

Mind the Gap is **not** a flashcard app. It doesn't quiz you, and it doesn't store questions and answers. Instead, it's a **study scheduler** that applies the [spaced repetition](https://en.wikipedia.org/wiki/Spaced_repetition) principle to your existing study material.

Here's the idea: you're working through a textbook, a course, or any structured material. You import your topics (or add them as you go), and after each study session, you tell the app how confident you feel. Based on that honest self-assessment, it schedules your next review — topics you're shaky on come back sooner, topics you've nailed get pushed further out.

Every day, you run `mtg today` and it tells you what needs attention. That's it.

**This system relies on your fair and honest self-assessment.** The confidence ratings you give after each session are the only input the scheduler uses. If you inflate your scores, you'll get longer intervals than you need and the gaps in your knowledge will grow. If you're honest, the system works remarkably well.

## Features

- **Hierarchical topics** — organize by chapters and sub-topics, with progress rolling up automatically
- **Flexible scheduling** — a 10-level confidence scale maps to review intervals you can customize
- **Multiple books** — track several courses or textbooks at once
- **Freeze plans** — going on holiday? Freeze a plan and all due dates pause; set a past start date for retroactive freezes
- **Edit anything** — rename books, change exam dates, reparent topics — all from the command line
- **Undo sessions** — made a mistake? Undo the last session for any topic
- **Backup & restore** — zip-based backups of your entire data directory, restorable with one command
- **Export** — export plans and session history to TOML (re-importable), JSON, or CSV
- **Config management** — view and edit review intervals from the CLI, or reset to defaults
- **Study statistics** — streaks, session counts, per-book breakdowns, and more
- **Shell tab completion** — completions for book and topic IDs in bash, zsh, and fish
- **Relative dates** — due dates shown as "today", "tomorrow", "in 3 days", or "2 days ago"
- **Colour-coded confidence** — confidence levels displayed in a red-to-green colour scale
- **Plain text files** — everything is stored in human-readable TOML files you fully own and control
- **Exam countdown** — optionally set an exam date and see how many days you have left
- **Works offline** — no internet, no accounts, no telemetry

## Installation

### Requirements

- Python 3.9 or higher

### Linux / macOS

**Option 1: pip (quickest)**

```bash
pip install mind-the-gap
```

**Option 2: pipx (recommended — keeps it isolated)**

```bash
pipx install mind-the-gap
```

**Option 3: from source**

```bash
git clone https://github.com/mind-the-gap-study/mind-the-gap.git
cd mind-the-gap
pip install .
```

**Option 4: install script**

```bash
curl -fsSL https://raw.githubusercontent.com/mind-the-gap-study/mind-the-gap/main/scripts/install.sh | bash
```

### Windows

**Option 1: pip**

```powershell
pip install mind-the-gap
```

**Option 2: install script (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/mind-the-gap-study/mind-the-gap/main/scripts/install.ps1 | iex
```

### First-time setup

After installing, run:

```bash
mtg init
```

This will ask you where to store your study files. The default is `~/Documents/mind-the-gap/`. You can pick a custom path — everything goes there, and you can back it up, sync it, or move it anytime.

### Shell completion

Mind the Gap supports tab completion for book and topic IDs in **bash**, **zsh**, and **fish**.

**Bash** — add to `~/.bashrc`:

```bash
eval "$(_MTG_COMPLETE=bash_source mtg)"
```

**Zsh** — add to `~/.zshrc`:

```zsh
autoload -Uz compinit && compinit -i 2>/dev/null
eval "$(_MTG_COMPLETE=zsh_source mtg)"
```

> **Important:** The `compinit` line must appear **before** the eval line. If `compinit` is already loaded elsewhere in your `.zshrc` (e.g. by Oh My Zsh), you can skip that line and just add the `eval`.

**Fish** — add to `~/.config/fish/completions/mtg.fish`:

```fish
eval (env _MTG_COMPLETE=fish_source mtg)
```

After adding the line, restart your shell or run `source ~/.bashrc` (or `~/.zshrc`). Then type `mtg done ` and press Tab to see topic completions.

## Quick start

### 1. Create a study plan

Create a file called `algorithms.toml`:

```toml
[book]
title = "Introduction to Algorithms"
id = "clrs"
exam_date = 2026-07-15
sessions_per_topic = 5

[[topic]]
id = "clrs1"
title = "The Role of Algorithms"
parent = ""

[[topic]]
id = "clrs1.1"
title = "Algorithms as a Technology"
parent = "clrs1"

[[topic]]
id = "clrs2"
title = "Getting Started"
parent = ""

[[topic]]
id = "clrs2.1"
title = "Insertion Sort"
parent = "clrs2"
```

The `id` field in `[book]` sets the prefix for all topic IDs. If you leave it out, it defaults to `ch` (so topics become `ch1`, `ch1.1`, etc.). You can use any short identifier you like — `clrs`, `ochem`, `bio`, `acr`, whatever makes sense to you.

The `parent` field creates hierarchy. Leave it empty for top-level chapters, or set it to a chapter's ID to nest a topic under it.

### 2. Import it

```bash
mtg add algorithms.toml
```

### 3. See what's due

```bash
mtg today
```

Since everything is new, you'll see all topics listed under "NEW (not yet started)".

### 4. Study and log it

After studying a topic:

```bash
mtg done clrs2.1
```

The app will ask when you studied (today or a custom date) and how confident you feel on a scale of 1–10. Based on your answer, it schedules the next review.

You can also run `mtg done` with no arguments to pick from a list of due topics interactively.

### 5. Check your progress

```bash
mtg plan clrs
```

This shows your full plan with progress bars, completion fractions, and due dates for each topic. Chapters show aggregated progress from their sub-topics.

## Usage reference

### Commands

| Command | Description |
|---|---|
| `mtg` | Show all books (overview table) |
| `mtg init` | First-time setup |
| **Study** | |
| `mtg today` | Show what's due across all books |
| `mtg today <book_id>` | Show what's due for a specific book |
| `mtg today --days 7` | Look ahead 7 days instead of the default 3 |
| `mtg plan` | Show all books in detail |
| `mtg plan <book_id>` | Show detailed plan/progress for a book |
| `mtg done` | Log a session (pick from due topics interactively) |
| `mtg done <topic_id>` | Log a study session for a specific topic |
| `mtg undo <topic_id>` | Undo the last study session for a topic |
| **Book management** | |
| `mtg add <file.toml>` | Import a study plan (supports re-importing exports with sessions) |
| `mtg topic <book_id> <topic_id> <title>` | Add a single topic (`--parent` to nest) |
| `mtg edit <book_id> --title "..." --exam 2026-09-01 --sessions 8` | Edit book properties |
| `mtg edit <book_id> <topic_id> --title "..." --parent ch2` | Edit a topic's title or parent |
| `mtg remove <book_id>` | Remove an entire book and its sessions |
| `mtg remove <book_id> <topic_id>` | Remove a topic (and its descendants) |
| **Scheduling** | |
| `mtg freeze <book_id> <duration>` | Freeze a plan (`10D`, `2W`, `3M`, `1Y`, or `YYYY-MM-DD`) |
| `mtg unfreeze <book_id>` | Unfreeze a plan (resume early) |
| **Data & admin** | |
| `mtg stats` | Show overall study statistics (streaks, averages, etc.) |
| `mtg stats <book_id>` | Show statistics for a specific book |
| `mtg export <book_id>` | Export plan + sessions (default: TOML) |
| `mtg export <book_id> --format json` | Export as JSON |
| `mtg export <book_id> --format csv` | Export sessions as CSV |
| `mtg backup` | Create a zip backup of all data files |
| `mtg restore <file.zip>` | Restore from a backup archive |
| **Configuration** | |
| `mtg config` | Show current configuration summary |
| `mtg config intervals` | View the confidence-to-days interval mapping |
| `mtg config intervals set <level> <days>` | Set interval for a confidence level |
| `mtg config intervals reset` | Reset all intervals to defaults |
| **Other** | |
| `mtg --version` | Show version |
| `mtg --help` | Show help |

### Flags

Several commands support a `--dry-run` flag that previews the action without making changes:

```bash
mtg remove clrs clrs2.1 --dry-run   # see what would be removed
mtg freeze clrs 2W --dry-run         # preview the freeze
mtg unfreeze clrs --dry-run          # preview the unfreeze
```

### Adding topics on the fly

You don't need to create the full plan upfront. You can add topics as you go:

```bash
# Create a new book and add a topic in one step
mtg topic bio bio1 "Cell Biology"

# Add sub-topics later
mtg topic bio bio1.1 "Cell Structure" --parent bio1
mtg topic bio bio1.2 "Cell Division" --parent bio1
```

If the book doesn't exist yet, `mtg topic` will ask you to create it, including the title, exam date, and number of sessions.

### Editing books and topics

Change a book's title, exam date, or sessions-per-topic:

```bash
mtg edit clrs --title "CLRS 4th Edition" --exam 2026-09-01 --sessions 8
```

Move a topic to a different parent, or rename it:

```bash
mtg edit clrs clrs2.1 --title "Insertion Sort (revised)" --parent clrs3
```

Clear an exam date with `--exam none`.

### Freezing a plan

Going on holiday? Have a busy period at work? Freeze a plan and all due dates pause:

```bash
# Freeze for 2 weeks
mtg freeze clrs 2W

# Freeze for 10 days
mtg freeze clrs 10D

# Freeze for 3 months
mtg freeze clrs 3M

# Freeze until a specific date
mtg freeze clrs 2026-06-01
```

Duration format: a number followed by `D` (days), `W` (weeks), `M` (months), or `Y` (years).

When you freeze, the app asks whether the freeze started today or on a past date — useful if you forgot to freeze before your break started.

Only topics that are due or overdue between the freeze start and end date get pushed. Topics already scheduled after the unfreeze date stay exactly where they are.

To resume early:

```bash
mtg unfreeze clrs
```

### Backup and restore

Create a zip backup of your entire data directory:

```bash
mtg backup
# ✓ Backed up 6 file(s) to mtg-backup-20260403-140000.zip (2.1 KB)
```

Restore from a backup:

```bash
mtg restore mtg-backup-20260403-140000.zip
```

This overwrites existing files with the same names. You'll be asked to confirm before anything is written.

### Exporting data

Export a book's plan and session history:

```bash
# TOML (default) — can be re-imported with `mtg add`
mtg export clrs

# JSON
mtg export clrs --format json

# CSV (sessions only — great for spreadsheets)
mtg export clrs --format csv

# Custom output path
mtg export clrs -o ~/Desktop/clrs-export.toml
```

### Understanding progress

Progress is calculated bottom-up. If a chapter has 3 topics and each needs 5 sessions:

```
Chapter 4 — Divide and Conquer              █████░░░░░  5/15
  Topic 4.1  Recurrences                    ██░░░░░░░░  2/5
  Topic 4.2  The Master Method              ██░░░░░░░░  2/5
  Topic 4.3  Proof Techniques               █░░░░░░░░░  1/5
```

The chapter's `5/15` is simply the sum of its children (2 + 2 + 1 out of 5 + 5 + 5). Once all topics reach `5/5`, the chapter shows `15/15 ✓ done`.

The overall book percentage works the same way — it's the total completed sessions across all leaf topics divided by the total possible. This percentage is also shown in the `mtg today` view next to each book header.

## Customisation

### Confidence scale and intervals

You can view and edit the confidence-to-days mapping directly from the CLI:

```bash
# View current intervals
mtg config intervals

# Change a single level
mtg config intervals set 5 7

# Reset everything to defaults
mtg config intervals reset
```

Or edit the `intervals.toml` file in your data directory directly:

```toml
[intervals]
1 = 1      # review tomorrow
2 = 2      # review in 2 days
3 = 3
4 = 4
5 = 5
6 = 7      # review in a week
7 = 10
8 = 14     # review in 2 weeks
9 = 17
10 = 21    # review in 3 weeks
```

Want more aggressive early review? Set `1 = 1, 2 = 1, 3 = 2`. Want longer gaps at the top end? Set `10 = 30`. Changes take effect immediately.

The confidence levels map to these descriptions (shown every time you log a session):

| Level | Meaning |
|---|---|
| 1 | I've seen these words before but couldn't tell you what they mean |
| 2 | I recognize the topic and maybe one or two key terms, but couldn't explain anything about it |
| 3 | I understand the basic definition but couldn't explain how it works or why it matters |
| 4 | I can describe what it is in simple terms but would struggle with follow-up questions |
| 5 | I understand the main idea and could give a basic explanation, but I'd miss important details or nuances |
| 6 | I can explain the core concept clearly and answer straightforward questions about it |
| 7 | I can explain it to others, provide examples, and answer most questions confidently |
| 8 | I understand how this connects to related concepts and can apply it in different contexts |
| 9 | I could teach this effectively, explain common misconceptions, and handle challenging questions |
| 10 | I have expert-level understanding — I could create new examples, critique explanations, and explain subtle distinctions |

### Number of sessions

Set `sessions_per_topic` in your book's TOML file, or change it later:

```bash
mtg edit clrs --sessions 8
```

Default is 10. This means you'll study each topic once and review it 9 more times. If you set it to 5, you get 1 study + 4 reviews.

### File structure

Everything lives in your data directory:

```
~/Documents/mind-the-gap/
├── intervals.toml              # confidence-to-days mapping (shared)
├── algorithms.toml             # study plan
├── algorithms.state.toml       # session history (auto-managed)
├── organic-chemistry.toml
└── organic-chemistry.state.toml
```

- **`*.toml`** — your study plans (one per book). Edit freely.
- **`*.state.toml`** — session logs (auto-managed, but human-readable). Each completed study session is an append-only entry.
- **`intervals.toml`** — shared across all books.

To remove a book, use `mtg remove <book_id>` or delete its `.toml` and `.state.toml` files manually. To share a plan with someone, export it with `mtg export` and send them the file — they can import it with `mtg add`.

## Examples

Check the `examples/` folder for ready-to-use study plan templates:

- `algorithms.toml` — a textbook with chapters and sub-topics
- `minimal.toml` — a flat list with no hierarchy (great for vocabulary, quick courses)

## Disclaimer

This project was created with the assistance of [Claude Opus 4.6](https://www.anthropic.com/claude), an AI assistant by Anthropic.

## License

[MIT](LICENSE)

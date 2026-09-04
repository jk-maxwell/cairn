"""
Cairn health note: renders Cairn/Health.md, the one place a silent failure
cannot hide.

Why a vault note and not a log file: the 28-day beta's exit bar is "zero
silent failures observed," and the only failure surface before this module
existed was `_ingest_failures.log` in the vault root -- a file that once sat
with two real failures in it for twelve days because nobody opens log files.
The beta's "habit" dial is literally "did the owner open the vault and ask on
most working days?", so the vault itself is the one surface guaranteed to be
seen daily. A log file provably is not. Cairn's health therefore has to be a
note that Obsidian renders well for free: real headings, a real table, front
matter -- not a format that makes the reader parse prose to find the alarm.

Data contract (owned by the ingestion side, not this file):

  receipts (
      source_path TEXT PRIMARY KEY,
      source_name TEXT NOT NULL,
      doc_id      TEXT,
      state       TEXT NOT NULL,   -- seen | converted | indexed | failed
      detail      TEXT,            -- exception text when failed
      first_seen  TEXT NOT NULL,   -- ISO 8601 UTC
      updated_at  TEXT NOT NULL    -- ISO 8601 UTC
  )

Non-terminal states are seen/converted; terminal are indexed/failed.
"Outstanding" means non-terminal AND updated_at older than a threshold
(default 30 minutes) -- the alarm condition, because a receipt that has sat
in a non-terminal state for half an hour means the pipeline stalled on it.

The watcher writes its own liveness into the existing `meta` table (see
watch.py's heartbeat()) under key 'watcher_heartbeat', an ISO 8601 UTC
string in the same "%Y-%m-%dT%H:%M:%SZ" format registry.py's governance log
uses. Read it from there rather than duplicating a heartbeat mechanism.

Vault-ownership contract (see registry.py's page-ownership comment and its
_regenerate_rollup_for/_replace_marked_block machinery): a ratified entity
page is the user's, and only the block between the cairn markers is ever
machine-written -- deleting that block is honoured, not undone, because the
rest of the page is the user's prose and daily editing must be trusted.
Health.md has no such split. The whole file is Cairn's -- there is no user
prose on this page to protect, ever. So this module does not attempt (and
must not attempt) the marker-preservation dance: write_health_note() always
overwrites the entire file. If the user deletes Cairn/Health.md outright,
that is not a violation of anything -- the next write recreates it from
scratch, the same way a deleted log file would just start fresh. The cairn
markers are still wrapped around the body below, and the front matter still
carries cairn-type, purely so the note reads as machine-owned in the same
visual language as every other Cairn page rather than inventing a new one.

Design rule that shapes every function below: this module is called from the
watcher's main loop, so nothing in it may raise past render_health(). Every
query is individually try/except-guarded and degrades to an honest "cannot
tell" line rather than crashing or silently omitting a section. In
particular: a missing `receipts` table (the data-layer agent's work may not
have landed yet) renders a plain sentence saying so, not a stack trace and
not a section that just vanishes. A missing heartbeat reads "never reported,"
which is a different fact than "reported long ago" and the note says which
one it is -- conflating them would make a dead watcher at 2am look identical
to a quiet week with no meetings.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from registry import MARK_BEGIN, MARK_END

# Where the note lives, vault-relative -- same convention as registry.QUEUE_NOTE
# (Path("Inbox") / "Governance.md"): a bare relative Path, joined onto vault_dir
# by the caller, never resolved against config.VAULT_DIR in here. Every
# function in this module takes the vault/connection explicitly so it is
# testable against a temp vault and a scratch database, exactly like registry.py.
HEALTH_NOTE = Path("Cairn") / "Health.md"

# Non-terminal receipt states: still moving through the pipeline. A row here
# older than the outstanding threshold is the alarm condition this note exists
# to surface -- see module docstring.
_NON_TERMINAL_STATES = ("seen", "converted")

DEFAULT_OUTSTANDING_MINUTES = 30

# The watcher's staleness threshold is a SEPARATE knob from the receipts one,
# and much tighter, because the two measure different things. A receipt may sit
# non-terminal for half an hour for perfectly dull reasons. The watcher, by
# contrast, beats once a minute (watch.py's HEARTBEAT_INTERVAL), so five
# missed beats is not ambiguity -- it is a dead process. Reusing the 30-minute
# receipts threshold here would let a watcher be dead for 29 minutes while the
# page said everything was fine, which is exactly the reassuring lie this note
# exists to stop telling.
DEFAULT_HEARTBEAT_STALE_MINUTES = 5

# watch.py blocks inside run_subprocess for up to SUBPROCESS_TIMEOUT (1800s)
# while an ingest runs, and cannot beat during that. A stale heartbeat whose
# recorded activity is a running pipeline is therefore expected, not alarming
# -- until it outlives the ceiling the pipeline itself should have hit, at
# which point the pipeline is hung and that IS the failure.
PIPELINE_CEILING_MINUTES = 31
_FAILURE_WINDOW_DAYS = 7

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _log(msg: str) -> None:
    print(f"  health: {msg}", flush=True)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str | None) -> datetime | None:
    """Tolerant ISO 8601 parse: accepts the trailing-Z form every writer in
    this codebase uses, plus an explicit offset or a naive string (assumed
    UTC, since every timestamp in this schema is documented as UTC). Returns
    None rather than raising -- callers must treat an unparseable timestamp
    as "unknown," not as an error worth crashing the note over."""
    if not ts:
        return None
    s = ts.strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ago(dt: datetime, now: datetime) -> str:
    """Plain-words age, e.g. "3 minutes ago" -- deliberately not a raw
    timedelta or ISO delta, because the point of this note is that a human
    reads it in passing and gets the alarm without doing arithmetic. A
    negative delta (clock skew between this machine and whatever wrote the
    timestamp) is folded to "just now" rather than shown as nonsense like
    "-4 minutes ago"."""
    secs = max((now - dt).total_seconds(), 0.0)
    if secs < 45:
        return "just now"
    minutes = secs / 60
    if minutes < 90:
        n = round(minutes)
        return f"{n} minute{'s' if n != 1 else ''} ago"
    hours = minutes / 60
    if hours < 36:
        n = round(hours)
        return f"{n} hour{'s' if n != 1 else ''} ago"
    days = hours / 24
    n = round(days)
    return f"{n} day{'s' if n != 1 else ''} ago"


def _md_cell(s: str | None, maxlen: int = 220) -> str:
    """Make arbitrary text (an exception message, a source name) safe inside
    a markdown table cell: collapse newlines so the row can't split across
    lines, escape the pipe character so it can't be mistaken for a column
    boundary, and cap the length so one enormous traceback can't blow out the
    table's readability. Truncation is visible ("...") rather than silent --
    the point of this whole note is to not hide things."""
    s = (s or "").replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()
    if not s:
        return "*(none)*"
    if len(s) > maxlen:
        s = s[: maxlen - 1].rstrip() + "…"
    return s


def _table_exists(conn, name: str) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False


# ---- sections -----------------------------------------------------------

def _watcher_section(conn, now: datetime, threshold_minutes: int) -> list[str]:
    lines = ["## Watcher", ""]
    activity = _meta_value(conn, "watcher_activity")
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key='watcher_heartbeat'"
        ).fetchone()
    except sqlite3.Error as e:
        lines.append(f"*Could not read the watcher heartbeat ({type(e).__name__}): "
                      f"treat this as unknown, not as healthy.*")
        lines.append("")
        return lines

    raw = row[0] if row else None
    if not raw:
        # Genuinely different from "reported long ago" -- a fresh database or
        # a watcher that has literally never completed one cycle yet.
        lines.append("**Last heartbeat:** never reported. Either the watcher has "
                      "never run against this database, or it died before "
                      "completing its first cycle.")
        lines.append("")
        return lines

    dt = _parse_iso(raw)
    if dt is None:
        lines.append(f"**Last heartbeat:** unreadable value `{raw}` -- cannot "
                      f"tell how stale this is. Treat as unknown, not healthy.")
        lines.append("")
        return lines

    ago = _ago(dt, now)
    age = now - dt
    stale = age > timedelta(minutes=threshold_minutes)
    ts_str = dt.strftime(_TS_FMT)
    doing = f" (last activity: `{activity}`)" if activity else ""

    if not stale:
        lines.append(f"**Last heartbeat:** {ts_str} -- {ago}{doing}")
    elif activity == "shutdown":
        # A watcher that said goodbye is not a watcher that vanished. Both stop
        # producing notes; only one of them is a fault, and conflating them
        # would send the owner hunting a bug that is really just a stopped
        # process they can restart.
        lines.append(f"**Last heartbeat:** {ts_str} -- {ago} -- **STOPPED "
                     f"CLEANLY.** The watcher shut down on purpose rather than "
                     f"dying. Nothing dropped in `sources/` since then has been "
                     f"seen. Restart it to resume ingestion.")
    elif activity and activity.startswith("pipeline:"):
        if age > timedelta(minutes=PIPELINE_CEILING_MINUTES):
            lines.append(f"**Last heartbeat:** {ts_str} -- {ago} -- **HUNG.** The "
                         f"watcher entered `{activity}` and has not returned. That "
                         f"is past the {PIPELINE_CEILING_MINUTES}-minute ceiling a "
                         f"cycle should never exceed, so the pipeline itself is "
                         f"stuck, not merely slow.")
        else:
            lines.append(f"**Last heartbeat:** {ts_str} -- {ago} -- busy running "
                         f"`{activity}`. Expected: the watcher is single-threaded "
                         f"and cannot check in while a cycle is running. Not a "
                         f"fault unless it passes "
                         f"{PIPELINE_CEILING_MINUTES} minutes.")
    else:
        lines.append(f"**Last heartbeat:** {ts_str} -- {ago} -- **STALE** "
                     f"(idle, and older than {threshold_minutes} minutes). The "
                     f"watcher is probably down. Do not read the silence below as "
                     f"\"nothing happened this week\" -- nothing may have been "
                     f"*checked*.")
    lines.append("")
    return lines


def _meta_value(conn, key: str) -> str | None:
    """One meta value, or None. Never raises -- a missing meta table just means
    we know less, which every caller here is written to tolerate."""
    try:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row and row[0] else None
    except sqlite3.Error:
        return None


def _outstanding_section(conn, now: datetime, threshold_minutes: int) -> list[str]:
    lines = ["## Outstanding receipts", ""]
    if not _table_exists(conn, "receipts"):
        lines.append("*The `receipts` table does not exist in this database yet. "
                      "This section will report for real once ingestion is writing "
                      "receipts -- until then, this note cannot see stalled files, "
                      "so its silence here is not a clean bill of health.*")
        lines.append("")
        return lines

    try:
        rows = conn.execute(
            "SELECT source_name, state, updated_at FROM receipts WHERE state IN (?,?)",
            _NON_TERMINAL_STATES,
        ).fetchall()
    except sqlite3.Error as e:
        lines.append(f"*Could not query outstanding receipts ({type(e).__name__}: {e}).*")
        lines.append("")
        return lines

    stale = []
    for source_name, state, updated_at in rows:
        dt = _parse_iso(updated_at)
        if dt is None:
            # An unparseable timestamp on a non-terminal receipt is exactly the
            # kind of thing this note exists to surface, not silently skip --
            # include it as maximally concerning (age unknown, sorts first).
            stale.append((float("inf"), source_name, state, "unknown (bad timestamp)"))
            continue
        age = (now - dt).total_seconds()
        if age > threshold_minutes * 60:
            stale.append((age, source_name, state, _ago(dt, now)))

    if not stale:
        lines.append(f"All clear -- nothing has been stuck in a non-terminal state "
                      f"for more than {threshold_minutes} minutes.")
        lines.append("")
        return lines

    stale.sort(key=lambda t: t[0], reverse=True)
    lines.append(f"**{len(stale)} outstanding** (non-terminal for more than "
                 f"{threshold_minutes} minutes):")
    lines.append("")
    lines.append("| Source | State | Age |")
    lines.append("|---|---|---|")
    for _age, source_name, state, age_str in stale:
        lines.append(f"| {_md_cell(source_name)} | {_md_cell(state)} | {age_str} |")
    lines.append("")
    return lines


def _failures_section(conn, now: datetime) -> list[str]:
    lines = [f"## Recent failures ({_FAILURE_WINDOW_DAYS} days)", ""]
    if not _table_exists(conn, "receipts"):
        lines.append("*The `receipts` table does not exist in this database yet, "
                      "so failures cannot be reported here -- check "
                      "`_ingest_failures.log` in the meantime if it exists.*")
        lines.append("")
        return lines

    try:
        rows = conn.execute(
            "SELECT source_name, detail, updated_at FROM receipts WHERE state='failed'"
        ).fetchall()
    except sqlite3.Error as e:
        lines.append(f"*Could not query recent failures ({type(e).__name__}: {e}).*")
        lines.append("")
        return lines

    cutoff = now - timedelta(days=_FAILURE_WINDOW_DAYS)
    recent = []
    for source_name, detail, updated_at in rows:
        dt = _parse_iso(updated_at)
        if dt is None or dt >= cutoff:
            # Same reasoning as the outstanding section: a failure whose
            # timestamp we cannot parse is not a failure we get to drop --
            # show it rather than let a formatting bug hide a real failure.
            recent.append((dt or now, source_name, detail))

    if not recent:
        lines.append(f"No failures in the last {_FAILURE_WINDOW_DAYS} days.")
        lines.append("")
        return lines

    recent.sort(key=lambda t: t[0], reverse=True)
    lines.append("| Source | When | Detail |")
    lines.append("|---|---|---|")
    for dt, source_name, detail in recent:
        when = _ago(dt, now) if dt else "unknown"
        lines.append(f"| {_md_cell(source_name)} | {when} | {_md_cell(detail)} |")
    lines.append("")
    return lines


def _corpus_section(conn) -> list[str]:
    lines = ["## Corpus", ""]

    def _count(sql: str, params: tuple = ()) -> str:
        try:
            row = conn.execute(sql, params).fetchone()
            return str(row[0]) if row else "0"
        except sqlite3.Error:
            return "unknown"

    documents = _count("SELECT COUNT(*) FROM documents")
    chunks = _count("SELECT COUNT(*) FROM chunks")
    ratified = _count("SELECT COUNT(*) FROM entities WHERE status='ratified'")
    proposed = _count("SELECT COUNT(*) FROM entities WHERE status='proposed'")

    lines.append("| Metric | Count |")
    lines.append("|---|---|")
    lines.append(f"| Documents | {documents} |")
    lines.append(f"| Chunks | {chunks} |")
    lines.append(f"| Entities (ratified) | {ratified} |")
    lines.append(f"| Entities (proposed) | {proposed} |")
    lines.append("")
    lines.append("*A number that stops moving is worth noticing as much as one that alarms.*")
    lines.append("")
    return lines


# ---- public API -----------------------------------------------------------

def render_health(conn, outstanding_threshold_minutes: int = DEFAULT_OUTSTANDING_MINUTES,
                  heartbeat_stale_minutes: int = DEFAULT_HEARTBEAT_STALE_MINUTES) -> str:
    """Render the full content of Cairn/Health.md from an open sqlite3
    connection. Pure with respect to the filesystem -- writes nothing,
    reads only -- so it is testable without a vault at all. Never raises:
    every section guards its own queries, and the outer try below is a
    second line of defence in case a future section forgets to."""
    now = _now_utc()
    try:
        body: list[str] = []
        body += _watcher_section(conn, now, heartbeat_stale_minutes)
        body += _outstanding_section(conn, now, outstanding_threshold_minutes)
        body += _failures_section(conn, now)
        body += _corpus_section(conn)
    except Exception as e:  # pragma: no cover - belt-and-suspenders; sections should already guard
        _log(f"WARN render_health hit an unguarded error: {type(e).__name__}: {e}")
        body = [
            f"*Health rendering failed unexpectedly ({type(e).__name__}: {e}). "
            f"That is a bug in health.py, not a report about the pipeline -- "
            f"nothing above or below this line reflects real state.*",
            "",
        ]

    ts = now.strftime(_TS_FMT)
    lines = [
        "---",
        "cairn-type: health",
        f"cairn-generated: {ts}",
        "---",
        "",
        "# Cairn Health",
        "",
        "*This note is entirely machine-owned and rewritten in full every cycle -- "
        "unlike an entity page, there is no user prose here to preserve. Deleting "
        "this file is fine; it will simply be recreated next time the watcher runs.*",
        "",
        MARK_BEGIN,
        "",
    ]
    lines += body
    lines.append(MARK_END)
    return "\n".join(lines).rstrip("\n") + "\n"


def write_health_note(conn, vault_dir,
                      outstanding_threshold_minutes: int = DEFAULT_OUTSTANDING_MINUTES,
                      heartbeat_stale_minutes: int = DEFAULT_HEARTBEAT_STALE_MINUTES) -> Path:
    """Render and write Cairn/Health.md under vault_dir, creating the Cairn/
    folder if needed. Returns the path written. Unlike render_health(), this
    does touch the filesystem, so an OSError (disk full, permissions) is
    allowed to propagate rather than being swallowed -- that is a real
    problem the caller (the watcher) needs to know about, the same way
    registry.ratify()/write_queue_note() let filesystem errors propagate
    rather than hiding them."""
    vault_dir = Path(vault_dir)
    content = render_health(conn, outstanding_threshold_minutes,
                            heartbeat_stale_minutes)
    note = vault_dir / HEALTH_NOTE
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(content, encoding="utf-8")
    _log(f"health note written -> {note}")
    return note

"""
Cairn storage: SQLite schema and connection.

This module owns the documents and chunks tables that ingestion writes.
The vector table (sqlite-vec) is created by the index step, not here, so
ingestion has no dependency on sqlite-vec being present.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id          TEXT PRIMARY KEY,   -- stable id derived from the source path
    source_path     TEXT NOT NULL,      -- absolute path to the original document
    source_name     TEXT NOT NULL,
    source_url      TEXT,               -- canonical web URL when known (else NULL); scraper fills this at fetch time
    source_modified TEXT,               -- source file mtime (ISO 8601 UTC)
    content_hash    TEXT,               -- hash of converted text, for change detection
    vault_path      TEXT,               -- where the converted .md was written
    ingested_at     TEXT,
    status          TEXT DEFAULT 'draft'-- records classification: draft | final | restricted
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id    TEXT PRIMARY KEY,       -- doc_id + ordinal
    doc_id      TEXT NOT NULL,
    ordinal     INTEGER NOT NULL,
    heading     TEXT,                   -- heading path context, e.g. "Chapter 43.105 > 43.105.020"
    text        TEXT NOT NULL,
    char_count  INTEGER,
    embedded    INTEGER NOT NULL DEFAULT 0,  -- 0 until the index step embeds it
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc      ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedded ON chunks(embedded);

-- Small key/value store for pipeline-level facts that must survive restarts,
-- e.g. which embedding model built the current vector index (see get_meta /
-- set_meta below). Not tied to any one document.
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- The entity registry's derived index. The registry itself lives in the
-- vault: ratified entity pages are user-owned files under Projects/ and
-- People/ (plus Profile.md) whose front matter (cairn-type, aliases,
-- status) is authoritative; registry.scan_vault() rebuilds the ratified
-- rows here from those pages. The engine never invents structure: an
-- extracted name that matches nothing ratified becomes a status='proposed'
-- row (registry.propose) awaiting the governance queue, and a rejected
-- proposal is kept as status='rejected' so it is never re-proposed.
CREATE TABLE IF NOT EXISTS entities (
    entity_id      TEXT PRIMARY KEY,
    name           TEXT NOT NULL,       -- canonical name (page name for ratified rows)
    type           TEXT NOT NULL,       -- person | project
    aliases        TEXT DEFAULT '[]',   -- JSON array of alternate names (from page front matter)
    note_path      TEXT,                -- vault path to the ratified entity page (NULL until ratified)
    status         TEXT NOT NULL DEFAULT 'ratified',  -- ratified | proposed | rejected
    origin         TEXT,                -- interview | extraction | seed
    rollup_seeded  INTEGER NOT NULL DEFAULT 0  -- has registry.py ever written the marked
                                                -- rollup block to this page? Lets
                                                -- _regenerate_rollup_for() tell "the user
                                                -- deleted the block" (leave it deleted) from
                                                -- "this page never had one" (write it once).
                                                -- DB-scoped: a dropped-and-rebuilt cairn.db
                                                -- forgets a deletion and reseeds the block one
                                                -- more time, unlike the vault-durable rejection
                                                -- fix above -- see registry.py for the trade-off.
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
-- idx_entities_status is created in _migrate(), after the status column is
-- guaranteed to exist on databases that predate it.

-- Many-to-many: which meeting documents mention which entities. Rewritten
-- wholesale for a doc_id each time that document is (re)enriched, and
-- cascade-deleted when the document is pruned, so entity pages regenerate
-- correctly without any special-case prune handling.
CREATE TABLE IF NOT EXISTS meeting_entities (
    doc_id     TEXT NOT NULL,
    entity_id  TEXT NOT NULL,
    PRIMARY KEY (doc_id, entity_id),
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE
);

-- The ingest-side half of the receipts doctrine ("no receipt, no answer" on
-- ask.py's side; "no receipt, no ingest" here). Every file that lands in
-- sources/ gets a row the moment ingest.py notices it, before any of the
-- risky work (conversion, enrichment, embedding) runs -- so a crash mid-file
-- still leaves a row behind instead of nothing. A row that never reaches a
-- terminal state is what makes a silent failure countable: see
-- receipts_outstanding() below. Keyed on source_path (not doc_id) because a
-- receipt must be writable before ingest has derived anything about the
-- file's content.
CREATE TABLE IF NOT EXISTS receipts (
    source_path  TEXT PRIMARY KEY,   -- absolute path of the file in sources/
    source_name  TEXT NOT NULL,      -- basename, for display
    doc_id       TEXT,               -- set once ingest derives one; NULL before that
    state        TEXT NOT NULL,      -- seen | converted | indexed | failed
    detail       TEXT,               -- exception text when state='failed', else NULL
    first_seen   TEXT NOT NULL,      -- ISO 8601 UTC, set once and never updated
    updated_at   TEXT NOT NULL       -- ISO 8601 UTC, bumped on every transition
);

CREATE INDEX IF NOT EXISTS idx_receipts_state ON receipts(state);
"""


def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")   # so deleting a document cascades to its chunks
    conn.execute("PRAGMA journal_mode = WAL")  # readers (the future service) do not block the writer
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()


def _migrate(conn):
    """Add columns that may be missing from an older database. Idempotent and safe."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
    if "source_url" not in cols:
        conn.execute("ALTER TABLE documents ADD COLUMN source_url TEXT")

    # Governance columns (2026-08-22, "Structure is user-authored; the engine
    # conforms"). Pre-governance rows default to 'ratified' here only so the
    # ALTER is valid on a NOT NULL column; the one-time registry.py --migrate
    # then converts every pre-existing row to 'proposed' so nothing the old
    # insert-on-miss extractor invented counts as ratified structure.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(entities)")}
    if "status" not in cols:
        conn.execute("ALTER TABLE entities ADD COLUMN status TEXT NOT NULL DEFAULT 'ratified'")
    if "origin" not in cols:
        conn.execute("ALTER TABLE entities ADD COLUMN origin TEXT")
    if "rollup_seeded" not in cols:
        conn.execute("ALTER TABLE entities ADD COLUMN rollup_seeded INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_status ON entities(status)")


# ---- meta key/value helpers -------------------------------------------------
# Used by index.py to stamp which embedding model + dimension built the vector
# table, and by ask.py to refuse to serve if the configured model no longer
# matches the one the index was actually built with.

def get_meta(conn, key):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()


# ---- receipts: ingest-side "no receipt, no ingest" bookkeeping -------------
# See the CREATE TABLE comment above for the doctrine. Every function here is
# a small, self-committing state transition (same pattern as set_meta above),
# so a row is durable the instant it's written -- not batched behind whatever
# else the caller's transaction is doing. Callers (ingest.py, index.py) are
# responsible for wrapping every call in try/except: this is instrumentation,
# and instrumentation must never be able to cost the user a document.

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def receipt_seen(conn, source_path: str, source_name: str) -> None:
    """Record that a file was noticed and is expected to become something.

    Upsert, not insert-only: a changed file re-entering the pipeline (ingest
    is hash-based) must land back on this same row and move it out of
    whatever terminal state it was in, not create a duplicate. first_seen is
    part of the INSERT branch only, so it is set once and never touched
    again. doc_id is deliberately left alone on the update branch -- a
    re-seen file already has a stable, path-derived doc_id from its last
    pass, and clearing it here would just reintroduce a NULL that doc_id_for()
    is going to recompute identically a moment later anyway.
    """
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO receipts (source_path, source_name, doc_id, state, detail, first_seen, updated_at)
        VALUES (?, ?, NULL, 'seen', NULL, ?, ?)
        ON CONFLICT(source_path) DO UPDATE SET
            source_name = excluded.source_name,
            state       = 'seen',
            detail      = NULL,
            updated_at  = excluded.updated_at
        """,
        (source_path, source_name, now, now),
    )
    conn.commit()


def receipt_converted(conn, source_path: str, doc_id: str) -> None:
    """Advance a receipt to 'converted' and record the doc_id ingest derived
    for it. No-op (zero rows affected) if 'seen' was never recorded for this
    path -- callers that care can check, but ingest.py always writes 'seen'
    first, so this should not happen in practice."""
    conn.execute(
        "UPDATE receipts SET state='converted', doc_id=?, detail=NULL, updated_at=? WHERE source_path=?",
        (doc_id, _now_iso(), source_path),
    )
    conn.commit()


def receipt_indexed(conn, source_path: str) -> None:
    """Advance a receipt to 'indexed' -- the terminal success state, reached
    once every chunk belonging to the document has been embedded."""
    conn.execute(
        "UPDATE receipts SET state='indexed', detail=NULL, updated_at=? WHERE source_path=?",
        (_now_iso(), source_path),
    )
    conn.commit()


def receipt_failed(conn, source_path: str, detail: str, source_name: str | None = None) -> None:
    """Mark a receipt 'failed' with the exception text in detail.

    Upsert, not update-only: a crash can happen before 'seen' was ever
    recorded (e.g. the file vanished between being listed and being read),
    and the failure still has to be visible rather than silently dropped for
    want of a prior row. source_name is optional and only used to fill in a
    brand-new row in that situation; it defaults to the path's basename.
    """
    now = _now_iso()
    name = source_name or Path(source_path).name
    conn.execute(
        """
        INSERT INTO receipts (source_path, source_name, doc_id, state, detail, first_seen, updated_at)
        VALUES (?, ?, NULL, 'failed', ?, ?, ?)
        ON CONFLICT(source_path) DO UPDATE SET
            state      = 'failed',
            detail     = excluded.detail,
            updated_at = excluded.updated_at
        """,
        (source_path, name, detail, now, now),
    )
    conn.commit()


def receipts_outstanding(conn, older_than_minutes: int = 30):
    """Non-terminal receipts (state 'seen' or 'converted') last touched more
    than older_than_minutes ago -- the alarm condition. This is what makes
    "zero silent failures" falsifiable: a receipt that never reaches a
    terminal state shows up here as a stale, countable row instead of as
    nothing. Returns rows as (source_path, source_name, doc_id, state,
    detail, first_seen, updated_at) tuples, oldest first.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return conn.execute(
        """
        SELECT source_path, source_name, doc_id, state, detail, first_seen, updated_at
        FROM receipts
        WHERE state IN ('seen', 'converted') AND updated_at < ?
        ORDER BY updated_at ASC
        """,
        (cutoff,),
    ).fetchall()


def receipts_recent_failures(conn, days: int = 7):
    """Receipts in state 'failed' updated within the last `days` days, most
    recent first. Same tuple shape as receipts_outstanding()."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return conn.execute(
        """
        SELECT source_path, source_name, doc_id, state, detail, first_seen, updated_at
        FROM receipts
        WHERE state = 'failed' AND updated_at >= ?
        ORDER BY updated_at DESC
        """,
        (cutoff,),
    ).fetchall()
"""
Cairn storage: SQLite schema and connection.

This module owns the documents and chunks tables that ingestion writes.
The vector table (sqlite-vec) is created by the index step, not here, so
ingestion has no dependency on sqlite-vec being present.
"""

import sqlite3
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
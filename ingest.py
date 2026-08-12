"""
Cairn ingestion: sources/ -> converted markdown (vault/) + chunk rows (cairn.db).

Fully deterministic. No model is involved at this stage. Safe to re-run: a file
is reconverted only when its source has changed (or with --force).

Usage:
    py ingest.py              ingest everything new or changed under sources/
    py ingest.py --force      reconvert everything, even if unchanged
    py ingest.py --dry-run    report what would happen, convert nothing
"""

import warnings
# Silence the pydub/ffmpeg RuntimeWarning MarkItDown emits on import. We do not
# process audio, so this is pure noise. Filtering warnings does not hide errors.
warnings.filterwarnings("ignore", category=RuntimeWarning)

import argparse
import hashlib
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import config
import db as dbmod
from markitdown import MarkItDown


# ---- small helpers ---------------------------------------------------------

def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


def doc_id_for(source: Path) -> str:
    # Stable 16-char id from the absolute path, so re-runs map to the same document.
    return sha1(str(source.resolve()))[:16]


def iso(ts: float | None = None) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def front_matter(source: Path, doc_id: str) -> str:
    src = str(source).replace("\\", "/")
    return (
        "---\n"
        f"doc_id: {doc_id}\n"
        f"source_name: {source.name}\n"
        f'source_path: "{src}"\n'
        f"source_modified: {iso(source.stat().st_mtime)}\n"
        f"converted: {iso()}\n"
        f"status: {config.DEFAULT_STATUS}\n"
        "---\n\n"
    )


# ---- chunking --------------------------------------------------------------

HEADING_RE = re.compile(r'^(#{1,6})\s+(.*\S)\s*$')


# --- POC-ONLY source_url backfill -------------------------------------------
# TEMPORARY: derives a canonical leg.wa.gov URL from RCW-style filenames so the
# current test corpus has real links to exercise the citation feature. This is
# NOT the permanent mechanism. When the scraper exists, it will write source_url
# directly at fetch time (it already has the URL), and this deriver goes away.
RCW_FILE_RE = re.compile(r'^RCW[_-](\d+)[_-](\d+)[_-](\w+)$', re.IGNORECASE)


def derive_source_url(source: Path) -> str | None:
    m = RCW_FILE_RE.match(source.stem)
    if not m:
        return None
    cite = ".".join(m.groups())
    return f"https://apps.leg.wa.gov/rcw/default.aspx?cite={cite}"


def _hard_split(text: str, max_chars: int, overlap: int) -> list[str]:
    """Last-resort splitter for a single oversized block, by character window."""
    out, i, n = [], 0, len(text)
    while i < n:
        end = min(i + max_chars, n)
        out.append(text[i:end])
        if end >= n:
            break
        i = end - overlap if overlap and end - overlap > i else end
    return out


def _pack(units: list[str], max_chars: int, overlap: int) -> list[str]:
    """Greedily pack units (paragraphs) into chunks up to max_chars, with overlap."""
    chunks, cur = [], ""
    for u in units:
        u = u.strip()
        if not u:
            continue
        if len(u) > max_chars:
            if cur.strip():
                chunks.append(cur.strip())
                cur = ""
            chunks.extend(_hard_split(u, max_chars, overlap))
            continue
        if cur and len(cur) + len(u) + 2 > max_chars:
            chunks.append(cur.strip())
            tail = cur[-overlap:] if overlap else ""
            cur = (tail + "\n\n" + u) if tail else u
        else:
            cur = (cur + "\n\n" + u) if cur else u
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def chunk_markdown(md_text: str, max_chars=None, overlap=None) -> list[tuple[str, str]]:
    """
    Heading-aware chunking. Splits on markdown headings so each chunk is a
    coherent section, carrying its heading path as context. Oversized sections
    are split further on paragraph boundaries. Returns [(heading_path, text), ...].
    """
    max_chars = max_chars or config.MAX_CHUNK_CHARS
    overlap = overlap or config.CHUNK_OVERLAP_CHARS

    stack: list[tuple[int, str]] = []
    buf: list[str] = []
    sections: list[tuple[str, str]] = []

    def path_str() -> str:
        return " > ".join(t for _, t in stack)

    def flush():
        if buf:
            text = "\n".join(buf).strip()
            if text:
                sections.append((path_str(), text))
            buf.clear()

    for line in md_text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
        else:
            buf.append(line)
    flush()

    chunks: list[tuple[str, str]] = []
    for heading, text in sections:
        if len(text) <= max_chars:
            chunks.append((heading, text))
        else:
            for part in _pack(re.split(r'\n\s*\n', text), max_chars, overlap):
                chunks.append((heading, part))

    # Drop short, headingless chunks: page furniture (breadcrumbs, citation links,
    # boilerplate) that sits above the first heading. Real short sections carry a
    # heading and are kept regardless of length.
    chunks = [
        (h, t) for (h, t) in chunks
        if h or len(t) >= config.MIN_CHUNK_CHARS
    ]
    return chunks


# ---- per-file processing ---------------------------------------------------

def process_file(md, conn, source: Path, force=False, dry_run=False):
    doc_id = doc_id_for(source)
    src_mtime = iso(source.stat().st_mtime)
    rel = source.relative_to(config.SOURCES_DIR)
    vault_path = (config.VAULT_DIR / rel).with_suffix(".md")

    row = conn.execute(
        "SELECT source_modified FROM documents WHERE doc_id=?", (doc_id,)
    ).fetchone()
    up_to_date = row is not None and row[0] == src_mtime and vault_path.exists()

    if up_to_date and not force:
        return ("skip", 0)
    if dry_run:
        return ("would-ingest", 0)

    text = md.convert(str(source)).text_content or ""
    content_hash = sha1(text)

    vault_path.parent.mkdir(parents=True, exist_ok=True)
    vault_path.write_text(front_matter(source, doc_id) + text, encoding="utf-8")

    chunks = chunk_markdown(text)
    source_url = derive_source_url(source)   # POC backfill; scraper will supply this directly later

    # Upsert the document. Note: status is intentionally NOT overwritten on update,
    # so a human reclassification (draft -> final/restricted) survives re-ingestion.
    conn.execute(
        """
        INSERT INTO documents
            (doc_id, source_path, source_name, source_url, source_modified, content_hash, vault_path, ingested_at, status)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(doc_id) DO UPDATE SET
            source_path=excluded.source_path,
            source_name=excluded.source_name,
            source_url=excluded.source_url,
            source_modified=excluded.source_modified,
            content_hash=excluded.content_hash,
            vault_path=excluded.vault_path,
            ingested_at=excluded.ingested_at
        """,
        (doc_id, str(source), source.name, source_url, src_mtime, content_hash,
         str(vault_path), iso(), config.DEFAULT_STATUS),
    )

    # Replace chunks wholesale; new chunks default embedded=0 for the index step.
    conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
    for i, (heading, ctext) in enumerate(chunks):
        conn.execute(
            "INSERT INTO chunks (chunk_id, doc_id, ordinal, heading, text, char_count, embedded)"
            " VALUES (?,?,?,?,?,?,0)",
            (f"{doc_id}-{i:04d}", doc_id, i, heading, ctext, len(ctext)),
        )
    conn.commit()
    return ("ingest", len(chunks))


# ---- entry point -----------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Cairn ingestion")
    ap.add_argument("--force", action="store_true", help="reconvert even if unchanged")
    ap.add_argument("--dry-run", action="store_true", help="report only, convert nothing")
    args = ap.parse_args()

    config.SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    config.VAULT_DIR.mkdir(parents=True, exist_ok=True)

    conn = dbmod.connect()
    dbmod.init_db(conn)
    md = MarkItDown()

    files = [
        p for p in sorted(config.SOURCES_DIR.rglob("*"))
        if p.is_file() and p.suffix.lower() in config.SUPPORTED_SUFFIXES
    ]

    print(f"Sources : {config.SOURCES_DIR}")
    print(f"Vault   : {config.VAULT_DIR}")
    print(f"DB      : {config.DB_PATH}")
    print(f"Found {len(files)} supported file(s)\n")

    t0 = time.time()
    ingested = skipped = failed = total_chunks = 0
    failures = []

    for p in files:
        rel = p.relative_to(config.SOURCES_DIR)
        try:
            action, nchunks = process_file(md, conn, p, force=args.force, dry_run=args.dry_run)
            if action == "ingest":
                ingested += 1
                total_chunks += nchunks
                print(f"  ok    {rel}  ({nchunks} chunks)")
            elif action == "would-ingest":
                print(f"  would {rel}")
            else:
                skipped += 1
        except Exception as e:
            failed += 1
            failures.append(f"{p}\t{type(e).__name__}: {e}")
            print(f"  FAIL  {rel}  ({type(e).__name__}: {e})")

    dt = time.time() - t0
    print(f"\nDone in {dt:.1f}s. ingested={ingested} skipped={skipped} failed={failed} chunks={total_chunks}")

    if not args.dry_run:
        pending = conn.execute("SELECT COUNT(*) FROM chunks WHERE embedded=0").fetchone()[0]
        if pending:
            print(f"{pending} chunk(s) awaiting embedding. Next step: the index build.")

    if failures:
        log = config.VAULT_DIR / "_ingest_failures.log"
        log.write_text("\n".join(failures), encoding="utf-8")
        print(f"See {log} for failure details.")


if __name__ == "__main__":
    main()
"""
Cairn watcher: automatic ingestion.

Closes the loop the user actually lives in: drop a file into sources/, ask a
question in Obsidian, get a grounded answer -- with nobody running ingest.py
or index.py by hand in between. Also the reverse: delete a file from
sources/, and the engine stops citing it.

Stdlib-only polling loop. Every POLL_INTERVAL seconds it snapshots
(path, mtime, size) for every supported file under sources/. When the
snapshot differs from the last stable one, it waits for DEBOUNCE_INTERVAL
seconds of *no further change* (a save-in-progress looks like a burst of
changes, not one), then runs the pipeline:

    1. ingest.py   (sources/ -> vault/ markdown + chunk rows, hash-based, idempotent)
    2. reconcile   (documents whose source file is gone: drop vault file,
                    chunk rows, and vectors -- the step ingest.py/index.py
                    do NOT do, which is the gap this file exists to close)
    3. index.py    (embed any chunks left pending, via Ollama)

The three steps run as subprocesses of ./.venv/bin/python, never concurrently
with each other or with a prior cycle. Startup always runs one full pass
immediately, so anything dropped while the watcher (or Cairn generally)
wasn't running gets picked up without a manual command.

Usage:
    ./.venv/bin/python watch.py                 (run in foreground; Ctrl-C to stop)
    nohup ./.venv/bin/python -u watch.py >> probe-watch.log 2>&1 &

Every log line is prefixed CAIRN-WATCH and timestamped, so `grep CAIRN-WATCH`
finds the whole story and `grep 'CAIRN-WATCH.*ERROR'` finds just the trouble.
"""

import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import config
import db as dbmod
import enrich
import registry

ROOT = config.ROOT
SOURCES_DIR = config.SOURCES_DIR
PYTHON = ROOT / ".venv" / "bin" / "python"
INGEST_SCRIPT = ROOT / "ingest.py"
INDEX_SCRIPT = ROOT / "index.py"

POLL_INTERVAL = 5.0        # how often we look at sources/ for changes
DEBOUNCE_INTERVAL = 2.0    # quiet period required before we act on a change
DEBOUNCE_MAX_WAIT = 30.0   # safety cap: act anyway if changes never go quiet
SUBPROCESS_TIMEOUT = 1800  # 30 min hard ceiling per ingest/index run

_running = True


def _handle_signal(signum, frame):
    global _running
    _running = False


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{ts} CAIRN-WATCH {msg}", flush=True)


# ---- change detection -------------------------------------------------------

def snapshot() -> dict:
    """(path -> (mtime, size)) for every file ingest.py would look at."""
    snap = {}
    if not SOURCES_DIR.exists():
        return snap
    for p in SOURCES_DIR.rglob("*"):
        if p.is_file() and p.suffix.lower() in config.SUPPORTED_SUFFIXES:
            try:
                st = p.stat()
                snap[str(p)] = (st.st_mtime, st.st_size)
            except OSError:
                continue  # file vanished mid-scan; next cycle will see it as removed
    return snap


def registry_snapshot() -> dict:
    """(path -> mtime) for every vault file the registry answers to: entity
    pages under Projects/ and People/, Profile.md, and the governance queue
    note. Cheap (a couple of directory globs), so it can run every poll."""
    snap = {}
    vd = config.VAULT_DIR
    paths = []
    for folder in ("Projects", "People"):
        d = vd / folder
        if d.is_dir():
            paths.extend(d.glob("*.md"))
    for p in (vd / "Profile.md", vd / "Inbox" / "Governance.md"):
        if p.exists():
            paths.append(p)
    for p in paths:
        try:
            snap[str(p)] = p.stat().st_mtime
        except OSError:
            continue
    return snap


def registry_sync(reason: str) -> None:
    """Re-sync the derived registry index from the vault (user edits to entity
    pages / Profile.md win over the DB), act on governance-queue edits
    (checked box -> ratify, deleted line -> reject), then rewrite the queue
    note and the rollup blocks. Each step is idempotent, so the extra cycle
    our own rewrites trigger settles immediately."""
    conn = dbmod.connect()
    try:
        conn.execute("PRAGMA busy_timeout = 10000")
        dbmod.init_db(conn)
        scan = registry.scan_vault(conn, config.VAULT_DIR)
        edits = registry.apply_queue_edits(conn, config.VAULT_DIR)
        registry.write_queue_note(conn, config.VAULT_DIR)
        rolled = registry.regenerate_rollups(conn, config.VAULT_DIR)
        if edits["ratified"] or edits["rejected"] or scan["added"] or scan["updated"] or scan["removed"]:
            try:
                enrich.regenerate_home(conn)
            except Exception as e:
                log(f"registry WARN could not regenerate Home: {type(e).__name__}: {e}")
        log(f"registry reason={reason} pages={scan['pages']} added={scan['added']} "
            f"updated={scan['updated']} removed={scan['removed']} "
            f"ratified={edits['ratified']} rejected={edits['rejected']} rollups={rolled}")
    finally:
        conn.close()


def diff_snapshots(old: dict, new: dict) -> tuple[list, list, list]:
    added = sorted(p for p in new if p not in old)
    removed = sorted(p for p in old if p not in new)
    modified = sorted(p for p in new if p in old and new[p] != old[p])
    return added, modified, removed


def debounce_wait(initial: dict) -> dict:
    """Block until two consecutive snapshots agree, or DEBOUNCE_MAX_WAIT elapses."""
    prev = initial
    start = time.time()
    while _running:
        time.sleep(DEBOUNCE_INTERVAL)
        cur = snapshot()
        if cur == prev:
            return cur
        prev = cur
        if time.time() - start > DEBOUNCE_MAX_WAIT:
            log(f"debounce quiet period not reached after {DEBOUNCE_MAX_WAIT:.0f}s, proceeding anyway")
            return cur
    return prev


# ---- pipeline steps -----------------------------------------------------------

def run_subprocess(script: Path, label: str) -> bool:
    """Run a pipeline script and log its output. Never raises."""
    try:
        proc = subprocess.run(
            [str(PYTHON), str(script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        log(f"{label} ERROR timed out after {SUBPROCESS_TIMEOUT}s")
        return False
    except Exception as e:
        log(f"{label} ERROR failed to launch: {type(e).__name__}: {e}")
        return False

    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.splitlines():
        if line.strip():
            log(f"{label} | {line}")

    if proc.returncode != 0:
        log(f"{label} ERROR exit={proc.returncode}")
        return False
    return True


def reconcile_deletions() -> int:
    """
    For every document whose source file no longer exists on disk: drop its
    vault/ markdown, its vec_chunks vectors, its chunks rows, and its
    documents row. Runs in one transaction; the vector-table delete happens
    before the row deletes so a mid-transaction failure can't strand a
    vector with no chunk to explain it.
    """
    conn = dbmod.connect()
    try:
        conn.execute("PRAGMA busy_timeout = 10000")  # WAL: wait out ask.py readers/writers instead of failing
        dbmod.init_db(conn)

        has_vec = True
        try:
            conn.enable_load_extension(True)
            import sqlite_vec
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        except Exception as e:
            has_vec = False
            log(f"reconcile WARN could not load sqlite_vec, vectors will not be pruned this cycle: {type(e).__name__}: {e}")

        rows = conn.execute("SELECT doc_id, source_path, vault_path FROM documents").fetchall()
        gone = [(doc_id, source_path, vault_path)
                for doc_id, source_path, vault_path in rows
                if not Path(source_path).exists()]
        if not gone:
            return 0

        conn.execute("BEGIN IMMEDIATE")
        try:
            for doc_id, source_path, vault_path in gone:
                if has_vec:
                    chunk_ids = [r[0] for r in conn.execute(
                        "SELECT chunk_id FROM chunks WHERE doc_id=?", (doc_id,)
                    ).fetchall()]
                    for cid in chunk_ids:
                        conn.execute("DELETE FROM vec_chunks WHERE chunk_id=?", (cid,))
                conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
                conn.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))
                if vault_path:
                    vp = Path(vault_path)
                    if vp.exists():
                        try:
                            vp.unlink()
                        except OSError as e:
                            log(f"reconcile WARN could not remove vault file {vp}: {e}")
                log(f"prune doc_id={doc_id} source={source_path}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        # Pruned meetings must drop out of the derived surfaces too. Ratified
        # entity pages are the user's and are never deleted here; regenerating
        # recomputes the rollup block on each (and the queue note's provenance)
        # correctly, since meeting_entities cascade-deleted above.
        try:
            enrich.regenerate_index_notes(conn)
        except Exception as e:
            log(f"reconcile WARN could not regenerate index notes: {type(e).__name__}: {e}")

        return len(gone)
    finally:
        conn.close()


def run_pipeline(reason: str) -> None:
    t0 = time.time()
    log(f"cycle start reason={reason}")

    ok_ingest = run_subprocess(INGEST_SCRIPT, "ingest")

    try:
        pruned = reconcile_deletions()
        log(f"reconcile pruned={pruned}")
    except Exception as e:
        log(f"reconcile ERROR {type(e).__name__}: {e}")

    ok_index = run_subprocess(INDEX_SCRIPT, "index")

    log(f"cycle end reason={reason} elapsed={time.time() - t0:.1f}s ingest_ok={ok_ingest} index_ok={ok_index}")


# ---- main loop ----------------------------------------------------------------

def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    log(f"starting sources={SOURCES_DIR} poll={POLL_INTERVAL}s debounce={DEBOUNCE_INTERVAL}s")

    # Idempotent startup pass: picks up anything sitting in sources/ from
    # before the watcher (or Cairn) was running. ingest.py is hash-based so
    # already-current files are skipped, not reconverted.
    try:
        run_pipeline("startup")
    except Exception as e:
        log(f"startup cycle ERROR {type(e).__name__}: {e}")

    # Startup registry pass: picks up entity-page/Profile edits and queue
    # checkmarks made while the watcher wasn't running.
    try:
        registry_sync("startup")
    except Exception as e:
        log(f"registry startup ERROR {type(e).__name__}: {e}")

    last = snapshot()
    last_reg = registry_snapshot()  # taken AFTER sync, so our own writes don't re-trigger

    while _running:
        time.sleep(POLL_INTERVAL)
        if not _running:
            break
        try:
            cur = snapshot()
            if cur != last:
                added, modified, removed = diff_snapshots(last, cur)
                log(f"change detected added={len(added)} modified={len(modified)} removed={len(removed)}")
                stable = debounce_wait(cur)
                if not _running:
                    break
                run_pipeline("change")
                last = snapshot()

            # Registry watch: user edits to entity pages, Profile.md, or the
            # governance queue note. Mtime comparison only until something
            # actually changed, so the quiet path stays free.
            cur_reg = registry_snapshot()
            if cur_reg != last_reg:
                registry_sync("vault-edit")
                last_reg = registry_snapshot()
        except Exception as e:
            log(f"cycle ERROR {type(e).__name__}: {e}")

    log("shutdown")


if __name__ == "__main__":
    main()

"""
Cairn index build: embed pending chunks into a sqlite-vec vector table.

Reads chunks where embedded=0, sends their text (heading prepended) to the local
Ollama embedding model (EMBED_MODEL below), stores EMBEDDING_DIM-length vectors in
vec_chunks, and flips embedded=1. Deterministic pipeline feeds this; the only model
call is the embedding itself.

Usage:
    py index.py                 embed all pending chunks
    py index.py --dry-run       report pending count + time estimate, embed nothing
    py index.py --reset         drop the vector table and re-embed everything

Requires Ollama running locally with the embedding model pulled:
    ollama pull nomic-embed-text
"""

import argparse
import json
import struct
import time
import urllib.error
import urllib.request

import config
import db as dbmod
import sqlite_vec


OLLAMA_URL = "http://127.0.0.1:11434/api/embed"
EMBED_MODEL = "nomic-embed-text"
BATCH_SIZE = 16          # chunks per Ollama call
EST_SECONDS_PER_CHUNK = 0.5   # rough prior; replaced by a live measurement after batch 1


# ---- embedding via Ollama --------------------------------------------------

def embed_batch(texts: list[str]) -> list[list[float]]:
    """Call Ollama's /api/embed with a list of inputs, return list of vectors."""
    payload = json.dumps({"model": EMBED_MODEL, "input": texts, "keep_alive": "30m"}).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    vecs = data.get("embeddings")
    if not vecs or len(vecs) != len(texts):
        raise RuntimeError(f"embed returned {len(vecs) if vecs else 0} vectors for {len(texts)} inputs")
    # Dimension gate: the vector table is declared FLOAT[EMBEDDING_DIM]. If the model
    # returns a different length (typically after a model swap), fail with a labeled
    # error here rather than corrupting the index or silently mismatching at query time.
    bad = {len(v) for v in vecs if len(v) != config.EMBEDDING_DIM}
    if bad:
        raise RuntimeError(
            f"embedding dimension mismatch: model returned {sorted(bad)}, "
            f"config.EMBEDDING_DIM is {config.EMBEDDING_DIM}. "
            f"Update EMBEDDING_DIM and rebuild the index (py index.py --reset)."
        )
    return vecs


def serialize(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def embed_text_for(heading: str, text: str) -> str:
    """Prepend the heading path as context, per the design decision to embed location + content."""
    return f"{heading}\n\n{text}" if heading else text


# ---- vector table ----------------------------------------------------------

def load_vec(conn):
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def ensure_vec_table(conn, reset=False):
    if reset:
        conn.execute("DROP TABLE IF EXISTS vec_chunks")
        conn.execute("UPDATE chunks SET embedded=0")
        conn.commit()
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
        f"USING vec0(chunk_id TEXT PRIMARY KEY, embedding FLOAT[{config.EMBEDDING_DIM}])"
    )
    conn.commit()


# ---- main ------------------------------------------------------------------

def fetch_pending(conn):
    return conn.execute(
        "SELECT chunk_id, heading, text FROM chunks WHERE embedded=0 ORDER BY doc_id, ordinal"
    ).fetchall()


def human_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.1f} min"
    return f"{seconds/3600:.1f} hr"


def main():
    ap = argparse.ArgumentParser(description="Cairn index build")
    ap.add_argument("--dry-run", action="store_true", help="report pending count + estimate, embed nothing")
    ap.add_argument("--reset", action="store_true", help="drop vectors and re-embed everything")
    args = ap.parse_args()

    conn = dbmod.connect()
    dbmod.init_db(conn)
    load_vec(conn)
    ensure_vec_table(conn, reset=args.reset)

    pending = fetch_pending(conn)
    n = len(pending)

    if n == 0:
        print("Nothing to embed. All chunks are indexed.")
        return

    total_chars = sum(len(t) for _, _, t in pending)
    est = n * EST_SECONDS_PER_CHUNK
    print(f"Pending chunks : {n}")
    print(f"Total text     : {total_chars:,} chars")
    print(f"Model          : {EMBED_MODEL}  (dim {config.EMBEDDING_DIM})")
    print(f"Rough estimate : ~{human_time(est)} (refined after the first batch)")

    if args.dry_run:
        print("\nDry run: nothing embedded.")
        return

    print(f"\nEmbedding in batches of {BATCH_SIZE} ...\n")
    t0 = time.time()
    done = 0
    measured_rate = None

    for start in range(0, n, BATCH_SIZE):
        batch = pending[start:start + BATCH_SIZE]
        texts = [embed_text_for(h, t) for _, h, t in batch]
        bt0 = time.time()
        try:
            vecs = embed_batch(texts)
        except urllib.error.URLError as e:
            print(f"  ERROR reaching Ollama at {OLLAMA_URL}: {e}")
            print("  Is the Ollama server running? Try: ollama list")
            break

        for (chunk_id, _, _), vec in zip(batch, vecs):
            conn.execute(
                "INSERT OR REPLACE INTO vec_chunks(chunk_id, embedding) VALUES (?,?)",
                (chunk_id, serialize(vec)),
            )
            conn.execute("UPDATE chunks SET embedded=1 WHERE chunk_id=?", (chunk_id,))
        conn.commit()

        done += len(batch)
        # refine the estimate off the first real batch
        if measured_rate is None:
            measured_rate = (time.time() - bt0) / len(batch)
            remaining = (n - done) * measured_rate
            print(f"  measured {measured_rate:.2f}s/chunk -> est remaining ~{human_time(remaining)}")
        print(f"  {done}/{n} embedded")

    dt = time.time() - t0
    indexed = conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
    still_pending = conn.execute("SELECT COUNT(*) FROM chunks WHERE embedded=0").fetchone()[0]
    print(f"\nDone in {human_time(dt)}. vectors in index: {indexed}. still pending: {still_pending}.")
    if still_pending == 0:
        print("Index complete. Next: the ask service.")


if __name__ == "__main__":
    main()
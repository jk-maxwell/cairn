"""
interview_registry_stub.py: thin, WORKING stand-ins for registry.py.

A parallel task is building the real registry module with exactly these
signatures. interview.py imports `registry` first and falls back to this
module, so the orchestrator swaps the real one in by simply adding
registry.py to the tree -- no edit to interview.py required.

Signatures held stable (do not change them here without changing the real
registry.py in lockstep):

    scan_vault(conn, vault_dir) -> dict
    match(conn, name, etype) -> str | None     # etype: 'person' | 'project'; read-only
    propose(conn, name, etype, doc_id) -> bool
    ratify(conn, entity_id, vault_dir) -> str
    reject(conn, entity_id) -> None
    write_queue_note(conn, vault_dir) -> None

Front-matter convention (DECISIONS 2026-08-22, "The registry lives in the
vault"): ratified entity pages are user-owned files in vault-root Projects/
and People/ carrying `cairn-type`, `aliases`, `status`.
"""

import hashlib
import json
import logging
import re
from pathlib import Path

log = logging.getLogger("cairn.registry")

# vault-root folders per entity type
TYPE_DIRS = {"project": "Projects", "person": "People"}

_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|]')


def _safe_filename(name: str) -> str:
    return _UNSAFE_CHARS.sub("-", name).strip().strip(".") or "unnamed"


def _entity_id(name: str, etype: str) -> str:
    return hashlib.sha1(f"{etype}:{name.strip().lower()}".encode("utf-8")).hexdigest()[:16]


def ensure_entity_columns(conn):
    """
    Idempotent migration: the entities table gains status ('ratified' |
    'proposed' | 'rejected') and origin ('interview' | 'extraction' | 'seed').
    Pre-migration rows (created by enrich.py before governance existed) are
    treated as ratified extractions, which is what they de-facto were.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(entities)")}
    if "status" not in cols:
        conn.execute("ALTER TABLE entities ADD COLUMN status TEXT DEFAULT 'ratified'")
        conn.execute("UPDATE entities SET status='ratified' WHERE status IS NULL")
        log.info("migration: entities.status added (existing rows -> 'ratified')")
    if "origin" not in cols:
        conn.execute("ALTER TABLE entities ADD COLUMN origin TEXT DEFAULT 'extraction'")
        conn.execute("UPDATE entities SET origin='extraction' WHERE origin IS NULL")
        log.info("migration: entities.origin added (existing rows -> 'extraction')")
    conn.commit()


def _front_matter(etype: str, aliases: list, status: str) -> str:
    alias_yaml = "[" + ", ".join(json.dumps(a) for a in aliases) + "]"
    return (
        "---\n"
        f"cairn-type: {etype}\n"
        f"aliases: {alias_yaml}\n"
        f"status: {status}\n"
        "---\n"
    )


# ---- the six stable signatures ----------------------------------------------

def scan_vault(conn, vault_dir) -> dict:
    """
    Rebuild the derived index from the vault (the vault is authoritative).
    Stub version: walks Projects/ and People/, upserts one ratified entity per
    page found, returns a summary dict.
    """
    ensure_entity_columns(conn)
    vault_dir = Path(vault_dir)
    seen = {"project": 0, "person": 0}
    for etype, folder in TYPE_DIRS.items():
        d = vault_dir / folder
        if not d.is_dir():
            continue
        for page in sorted(d.glob("*.md")):
            name = page.stem
            aliases = []
            m = re.search(r"^aliases:\s*\[(.*?)\]", page.read_text(encoding="utf-8"),
                          re.MULTILINE)
            if m and m.group(1).strip():
                try:
                    aliases = json.loads("[" + m.group(1) + "]")
                except json.JSONDecodeError:
                    aliases = [a.strip().strip('"') for a in m.group(1).split(",") if a.strip()]
            eid = _entity_id(name, etype)
            conn.execute(
                "INSERT INTO entities(entity_id, name, type, aliases, note_path, status, origin) "
                "VALUES (?,?,?,?,?, 'ratified', 'seed') "
                "ON CONFLICT(entity_id) DO UPDATE SET aliases=excluded.aliases, "
                "note_path=excluded.note_path, status='ratified'",
                (eid, name, etype, json.dumps(aliases), str(page)),
            )
            seen[etype] += 1
    conn.commit()
    log.info("scan_vault: %d project page(s), %d person page(s)", seen["project"], seen["person"])
    return {"projects": seen["project"], "people": seen["person"]}


def match(conn, name, etype) -> str | None:
    """Read-only: entity_id of the ratified entity whose name or alias matches (case-insensitive)."""
    ensure_entity_columns(conn)
    needle = name.strip().lower()
    for eid, ename, aliases_json in conn.execute(
        "SELECT entity_id, name, aliases FROM entities "
        "WHERE type=? AND (status='ratified' OR status IS NULL)", (etype,)
    ):
        if ename.strip().lower() == needle:
            return eid
        for a in json.loads(aliases_json or "[]"):
            if str(a).strip().lower() == needle:
                return eid
    return None


def propose(conn, name, etype, doc_id) -> bool:
    """File a governance proposal. False if the name already matches or is already proposed."""
    ensure_entity_columns(conn)
    if match(conn, name, etype):
        return False
    needle = name.strip().lower()
    row = conn.execute(
        "SELECT 1 FROM entities WHERE type=? AND status='proposed' AND lower(name)=?",
        (etype, needle),
    ).fetchone()
    if row:
        return False
    eid = _entity_id(name, etype)
    conn.execute(
        "INSERT OR IGNORE INTO entities(entity_id, name, type, aliases, status, origin) "
        "VALUES (?,?,?,?,'proposed','extraction')",
        (eid, name.strip(), etype, "[]"),
    )
    if doc_id:
        conn.execute("INSERT OR IGNORE INTO meeting_entities(doc_id, entity_id) VALUES (?,?)",
                     (doc_id, eid))
    conn.commit()
    log.info("propose: %s %r (doc %s)", etype, name, doc_id)
    return True


def ratify(conn, entity_id, vault_dir) -> str:
    """
    Ratify an entity: status -> 'ratified' and write its vault page
    (Projects/<name>.md or People/<name>.md) with the front-matter convention.
    Returns the page path. Never overwrites an existing page body.
    """
    ensure_entity_columns(conn)
    row = conn.execute(
        "SELECT name, type, aliases FROM entities WHERE entity_id=?", (entity_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"unknown entity_id {entity_id!r}")
    name, etype, aliases_json = row
    aliases = json.loads(aliases_json or "[]")
    folder = Path(vault_dir) / TYPE_DIRS.get(etype, "Projects")
    folder.mkdir(parents=True, exist_ok=True)
    page = folder / f"{_safe_filename(name)}.md"
    if not page.exists():
        page.write_text(_front_matter(etype, aliases, "active") + f"\n# {name}\n",
                        encoding="utf-8")
        log.info("ratify: wrote %s", page)
    else:
        log.info("ratify: page already exists, left untouched: %s", page)
    conn.execute("UPDATE entities SET status='ratified', note_path=? WHERE entity_id=?",
                 (str(page), entity_id))
    conn.commit()
    return str(page)


def reject(conn, entity_id) -> None:
    ensure_entity_columns(conn)
    conn.execute("UPDATE entities SET status='rejected' WHERE entity_id=?", (entity_id,))
    conn.commit()
    log.info("reject: entity %s", entity_id)


def write_queue_note(conn, vault_dir) -> None:
    """Regenerate the governance queue note (Inbox/Governance.md) from pending proposals."""
    ensure_entity_columns(conn)
    rows = conn.execute(
        "SELECT name, type FROM entities WHERE status='proposed' ORDER BY type, name"
    ).fetchall()
    inbox = Path(vault_dir) / "Inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    lines = ["# Governance queue", "",
             "Check a line to ratify it; delete a line to reject it.", ""]
    lines += [f"- [ ] {etype}: {name}" for name, etype in rows] or ["(nothing pending)"]
    (inbox / "Governance.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("write_queue_note: %d pending proposal(s)", len(rows))

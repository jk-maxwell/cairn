"""
Cairn entity registry: vault-authoritative structure + the governance queue.

Implements the three 2026-08-22 decisions (docs/DECISIONS.md):

  - Structure is user-authored; the engine conforms. The parsing engine may
    only LINK extracted content into ratified structure. Anything it believes
    is new becomes a PROPOSAL in the governance queue -- no page, no link,
    no embedding until a human ratifies it.
  - The registry lives in the vault. Ratified entity pages are user-owned
    markdown files in vault-root folders (Projects/, People/) plus
    Profile.md, carrying a small front-matter convention (cairn-type,
    aliases, status). The entities table is a derived index rebuilt from
    those pages by scan_vault(); editing a page IS editing the structure.
  - The governance queue is a checkbox note, Inbox/Governance.md: checking
    a line ratifies, deleting a line rejects, and the watcher acts on the
    edit. Rejections persist (status='rejected') so a name is never
    re-proposed.

Page ownership contract: the body of a ratified entity page is the user's
and is never rewritten. Machine contributions live only in front matter the
user authored anyway (never touched here after creation) and in the single
block between the cairn markers, which regenerate_rollups() rewrites.

Every function takes the vault directory explicitly so tests run against a
temp vault; nothing here reads config.VAULT_DIR except the __main__ CLI.

CLI:
    py registry.py --scan       resync the DB index from the vault pages
    py registry.py --queue      apply queue edits, then rewrite the queue note
    py registry.py --migrate    one-time conversion of a pre-governance DB:
                                every existing entity becomes a proposal, the
                                generated Cairn/People and Cairn/Projects
                                pages are deleted, and the initial
                                Inbox/Governance.md is written
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

MARK_BEGIN = "<!-- cairn:begin -->"
MARK_END = "<!-- cairn:end -->"

# Vault-root folder per entity type. Profile.md sits at the vault root and is
# scanned as a person page (the owner); its front matter may carry an explicit
# `name:` since the file stem "Profile" is not a person's name.
FOLDERS = {"project": "Projects", "person": "People"}
TYPES = {v: k for k, v in FOLDERS.items()}

QUEUE_NOTE = Path("Inbox") / "Governance.md"

# meta keys (db.get_meta/set_meta) recording what the queue note contained the
# last time WE wrote it. apply_queue_edits() only treats a proposal line as
# deleted-by-the-user if it was actually published in that last write --
# otherwise a proposal recorded after the note was written would look deleted
# and be wrongly rejected.
META_QUEUE_HASH = "governance_note_hash"
META_QUEUE_NAMES = "governance_note_names"


def _log(msg: str) -> None:
    print(f"  registry: {msg}", flush=True)


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|]')


def _sanitize(name: str) -> str:
    cleaned = _UNSAFE_CHARS.sub('-', name).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned or "untitled"


# ---- front matter -----------------------------------------------------------
# Minimal YAML-subset parser (stdlib only, like the rest of the pipeline).
# Handles the convention this module defines: scalar values, inline lists
# [a, b], and block lists. Anything fancier in user front matter is ignored,
# never an error.

_FM_BLOCK_RE = re.compile(r"^---\r?\n(.*?)\r?\n---", re.DOTALL)
_FM_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")
_FM_ITEM_RE = re.compile(r"^\s+-\s+(.*)$")


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def parse_front_matter(text: str) -> dict:
    m = _FM_BLOCK_RE.match(text)
    if not m:
        return {}
    fm: dict = {}
    lines = m.group(1).splitlines()
    i = 0
    while i < len(lines):
        km = _FM_KEY_RE.match(lines[i])
        if not km:
            i += 1
            continue
        key, val = km.group(1), km.group(2).strip()
        if val == "":
            items, j = [], i + 1
            while j < len(lines) and _FM_ITEM_RE.match(lines[j]):
                items.append(_unquote(_FM_ITEM_RE.match(lines[j]).group(1)))
                j += 1
            if items:
                fm[key] = items
                i = j
                continue
            fm[key] = ""
        elif val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [_unquote(x) for x in inner.split(",") if x.strip()] if inner else []
        else:
            fm[key] = _unquote(val)
        i += 1
    return fm


# ---- name matching ----------------------------------------------------------

def _tokens(s: str) -> list[str]:
    return s.lower().split()


def _is_name_variant(short: str, long_: str) -> bool:
    """True if `short` looks like a shorter form of `long_`: a word-prefix
    ("Ann" of "Ann Ortega") or a plain substring ("Ori" of "Orion")."""
    st, lt = _tokens(short), _tokens(long_)
    if not st or not lt:
        return False
    if lt[:len(st)] == st:
        return True
    return short.lower() in long_.lower()


def _names_of(row_name: str, aliases_json: str) -> list[str]:
    try:
        aliases = json.loads(aliases_json or "[]")
    except json.JSONDecodeError:
        aliases = []
    return [row_name] + [a for a in aliases if isinstance(a, str)]


def _match_in(rows, name: str) -> str | None:
    """Match `name` against (entity_id, name, aliases) rows. Exact/alias
    case-insensitive first, then name-variant folding in both directions.
    Returns the matched row's canonical name, or None. Pure function."""
    name = (name or "").strip()
    if not name:
        return None
    name_lower = name.lower()
    for _eid, canon, aliases_json in rows:
        if any(name_lower == n.lower() for n in _names_of(canon, aliases_json)):
            return canon
    for _eid, canon, aliases_json in rows:
        for known in _names_of(canon, aliases_json):
            if len(name) <= len(known) and _is_name_variant(name, known):
                return canon
            if len(name) > len(known) and _is_name_variant(known, name):
                return canon
    return None


def ensure_entity_columns(conn) -> None:
    """Idempotent guard for callers holding a connection that may predate the
    governance schema: entities gains status (ratified|proposed|rejected) and
    origin (interview|extraction|seed). db._migrate() does the same for
    connections opened through db.py; this covers everything else."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(entities)")}
    if "status" not in cols:
        conn.execute("ALTER TABLE entities ADD COLUMN status TEXT NOT NULL DEFAULT 'ratified'")
        _log("migration: entities.status added (existing rows -> 'ratified')")
    if "origin" not in cols:
        conn.execute("ALTER TABLE entities ADD COLUMN origin TEXT")
        conn.execute("UPDATE entities SET origin='extraction' WHERE origin IS NULL")
        _log("migration: entities.origin added (existing rows -> 'extraction')")
    conn.commit()


def match(conn, name: str, etype: str) -> str | None:
    """Read-only canonical lookup against RATIFIED entities only: exact,
    alias, case-insensitive, and name-variant folding (shorter/longer forms)
    in both directions. NEVER inserts or mutates."""
    rows = conn.execute(
        "SELECT entity_id, name, aliases FROM entities "
        "WHERE type=? AND status='ratified' ORDER BY name",
        (etype,),
    ).fetchall()
    return _match_in(rows, name)


# ---- proposals --------------------------------------------------------------

def propose(conn, name: str, etype: str, doc_id: str | None) -> bool:
    """Record a governance proposal for `name` unless it already matches a
    ratified, proposed, or rejected entity of this type (so a rejection is
    permanent and a pending proposal is not duplicated). Provenance is the
    meeting_entities link to doc_id. Returns True only when newly proposed."""
    name = (name or "").strip()
    if not name:
        return False
    rows = conn.execute(
        "SELECT entity_id, name, aliases, status FROM entities WHERE type=? ORDER BY name",
        (etype,),
    ).fetchall()
    matched = _match_in([(r[0], r[1], r[2]) for r in rows], name)
    if matched is not None:
        row = next(r for r in rows if r[1] == matched)
        if row[3] == "proposed":
            # Same pending proposal seen in another meeting: accrue provenance.
            _link_provenance(conn, doc_id, row[0])
            conn.commit()
        return False

    entity_id = _sha1(f"{etype}:{name.lower()}")[:16]
    conn.execute(
        "INSERT OR IGNORE INTO entities (entity_id, name, type, aliases, note_path, status, origin) "
        "VALUES (?,?,?,?,NULL,'proposed','extraction')",
        (entity_id, name, etype, "[]"),
    )
    _link_provenance(conn, doc_id, entity_id)
    conn.commit()
    _log(f"proposed {etype} {name!r} (doc={doc_id or 'none'})")
    return True


def _link_provenance(conn, doc_id: str | None, entity_id: str) -> None:
    if not doc_id:
        return
    # meeting_entities carries a foreign key on documents; a proposal raised
    # outside ingestion (no documents row yet) simply carries no doc link.
    if not conn.execute("SELECT 1 FROM documents WHERE doc_id=?", (doc_id,)).fetchone():
        return
    conn.execute(
        "INSERT OR IGNORE INTO meeting_entities (doc_id, entity_id) VALUES (?,?)",
        (doc_id, entity_id),
    )


# ---- ratify / reject --------------------------------------------------------

def _page_path(vault_dir: Path, etype: str, name: str) -> Path:
    return Path(vault_dir) / FOLDERS[etype] / f"{_sanitize(name)}.md"


def _fm_aliases(aliases: list[str]) -> str:
    return "[" + ", ".join(aliases) + "]"


def ratify(conn, entity_id: str, vault_dir) -> str:
    """Create the user-owned entity page (unless the user already made one),
    flip the entity to 'ratified', and return the page path. The page body is
    the user's from this moment on; only the block between the cairn markers
    is ever regenerated."""
    vault_dir = Path(vault_dir)
    row = conn.execute(
        "SELECT name, type, aliases FROM entities WHERE entity_id=?", (entity_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"no entity {entity_id!r}")
    name, etype, aliases_json = row
    aliases = json.loads(aliases_json or "[]")
    page = _page_path(vault_dir, etype, name)

    if not page.exists():
        page.parent.mkdir(parents=True, exist_ok=True)
        fm = [
            "---",
            f"cairn-type: {etype}",
        ]
        if page.stem != name:
            # Filename sanitization changed the stem; record the real name so
            # a later scan_vault still resolves this page to this entity.
            fm.append(f'name: "{name}"')
        fm.append(f"aliases: {_fm_aliases(aliases)}")
        if etype == "project":
            fm.append("status: active")
        fm.append("---")
        content = "\n".join(fm) + "\n\n\n" + MARK_BEGIN + "\n" + MARK_END + "\n"
        page.write_text(content, encoding="utf-8")

    conn.execute(
        "UPDATE entities SET status='ratified', note_path=? WHERE entity_id=?",
        (str(page), entity_id),
    )
    conn.commit()
    _log(f"ratified {etype} {name!r} -> {page.name}")
    _regenerate_rollup_for(conn, entity_id, page)
    return str(page)


def reject(conn, entity_id: str) -> None:
    """Flip to 'rejected'. The row is kept forever so propose() never raises
    the same name again."""
    row = conn.execute(
        "SELECT name, type FROM entities WHERE entity_id=?", (entity_id,)
    ).fetchone()
    conn.execute("UPDATE entities SET status='rejected' WHERE entity_id=?", (entity_id,))
    conn.commit()
    if row:
        _log(f"rejected {row[1]} {row[0]!r}")


# ---- vault scan: the vault is authoritative ---------------------------------

def _registry_pages(vault_dir: Path):
    """Yield (path, etype, name, aliases) for every page carrying the
    front-matter convention. Pages without cairn-type are the user's own
    business and are skipped silently."""
    for folder, etype in TYPES.items():
        d = vault_dir / folder
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            fm = parse_front_matter(p.read_text(encoding="utf-8", errors="replace"))
            declared = str(fm.get("cairn-type", "")).strip().lower()
            if declared not in FOLDERS:
                continue
            if declared != etype:
                _log(f"scan WARN {p.name}: cairn-type {declared!r} disagrees with folder {folder}/; using {declared!r}")
            name = str(fm.get("name", "")).strip() or p.stem
            aliases = fm.get("aliases", [])
            aliases = [a for a in aliases if a] if isinstance(aliases, list) else []
            yield p, declared, name, aliases
    profile = vault_dir / "Profile.md"
    if profile.exists():
        fm = parse_front_matter(profile.read_text(encoding="utf-8", errors="replace"))
        if str(fm.get("cairn-type", "")).strip().lower() == "person":
            name = str(fm.get("name", "")).strip() or profile.stem
            aliases = fm.get("aliases", [])
            aliases = [a for a in aliases if a] if isinstance(aliases, list) else []
            yield profile, "person", name, aliases


def scan_vault(conn, vault_dir) -> dict:
    """Rebuild the ratified rows of the entities table from the vault pages.
    The vault is authoritative: a page is a ratified entity, an edited alias
    list wins over whatever the DB held, and a ratified row whose page is
    gone is dropped. Proposed and rejected rows (which have no pages) are
    never touched. Returns summary counts."""
    vault_dir = Path(vault_dir)
    counts = {"pages": 0, "added": 0, "updated": 0, "unchanged": 0, "removed": 0}
    seen_ids: set[str] = set()

    for page, etype, name, aliases in _registry_pages(vault_dir):
        counts["pages"] += 1
        rows = conn.execute(
            "SELECT entity_id, name, aliases, status FROM entities WHERE type=? ORDER BY name",
            (etype,),
        ).fetchall()
        # Exact/alias match only (no variant folding): a page name is an
        # explicit user statement, and folding two distinct pages together
        # would merge structure the user deliberately kept separate.
        target = None
        name_lower = name.lower()
        for eid, rname, raliases, rstatus in rows:
            if eid in seen_ids:
                continue
            if any(name_lower == n.lower() for n in _names_of(rname, raliases)):
                target = (eid, rname, raliases, rstatus)
                break

        aliases_json = json.dumps(aliases)
        if target is None:
            entity_id = _sha1(f"{etype}:{name_lower}")[:16]
            conn.execute(
                "INSERT OR REPLACE INTO entities (entity_id, name, type, aliases, note_path, status, origin) "
                "VALUES (?,?,?,?,?,'ratified','seed')",
                (entity_id, name, etype, aliases_json, str(page)),
            )
            seen_ids.add(entity_id)
            counts["added"] += 1
            _log(f"scan added {etype} {name!r} from {page.name}")
        else:
            eid, rname, raliases, rstatus = target
            seen_ids.add(eid)
            changed = (rname != name or (raliases or "[]") != aliases_json or rstatus != "ratified")
            cur_path = conn.execute(
                "SELECT note_path FROM entities WHERE entity_id=?", (eid,)
            ).fetchone()[0]
            if changed or cur_path != str(page):
                conn.execute(
                    "UPDATE entities SET name=?, aliases=?, note_path=?, status='ratified' "
                    "WHERE entity_id=?",
                    (name, aliases_json, str(page), eid),
                )
                counts["updated"] += 1
                if rstatus != "ratified":
                    _log(f"scan ratified {etype} {name!r} (user created {page.name} directly)")
            else:
                counts["unchanged"] += 1

    # Ratified rows whose page is gone: the user deleted structure.
    for eid, name, etype in conn.execute(
        "SELECT entity_id, name, type FROM entities WHERE status='ratified'"
    ).fetchall():
        if eid not in seen_ids:
            conn.execute("DELETE FROM entities WHERE entity_id=?", (eid,))
            counts["removed"] += 1
            _log(f"scan removed {etype} {name!r} (page deleted from vault)")

    conn.commit()
    _log(f"scan_vault pages={counts['pages']} added={counts['added']} "
         f"updated={counts['updated']} removed={counts['removed']}")
    return counts


# ---- meeting rollups (the one machine-owned block on a ratified page) -------

def _meeting_titles_for(conn, entity_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT d.vault_path FROM meeting_entities me "
        "JOIN documents d ON d.doc_id = me.doc_id WHERE me.entity_id=?",
        (entity_id,),
    ).fetchall()
    titles = []
    for (vp,) in rows:
        if vp and Path(vp).exists():
            titles.append(Path(vp).stem)
    return sorted(titles, reverse=True)


def _rollup_body(conn, entity_id: str) -> str:
    titles = _meeting_titles_for(conn, entity_id)
    lines = ["## Meetings", ""]
    lines += [f"- [[{t}]]" for t in titles] if titles else ["*(no meeting notes yet)*"]
    lines += ["", "*Generated by Cairn — this block is rebuilt automatically; everything above it is yours.*"]
    return "\n".join(lines)


def _replace_marked_block(text: str, inner: str) -> str:
    """Replace ONLY the content between the cairn markers. If the markers are
    missing (the user removed them), append a fresh marked block at the end --
    never touch anything the user wrote."""
    begin, end = text.find(MARK_BEGIN), text.find(MARK_END)
    block = f"{MARK_BEGIN}\n{inner}\n{MARK_END}"
    if begin != -1 and end != -1 and end > begin:
        return text[:begin] + block + text[end + len(MARK_END):]
    return text.rstrip("\n") + "\n\n" + block + "\n"


def _regenerate_rollup_for(conn, entity_id: str, page: Path) -> bool:
    if not page.exists():
        return False
    old = page.read_text(encoding="utf-8", errors="replace")
    new = _replace_marked_block(old, _rollup_body(conn, entity_id))
    if new != old:
        page.write_text(new, encoding="utf-8")
        return True
    return False


def regenerate_rollups(conn, vault_dir) -> int:
    """Rewrite the marked rollup block on every ratified entity page whose
    content would change. Returns the number of pages touched."""
    vault_dir = Path(vault_dir)
    touched = 0
    for eid, note_path in conn.execute(
        "SELECT entity_id, note_path FROM entities WHERE status='ratified' AND note_path IS NOT NULL"
    ).fetchall():
        if _regenerate_rollup_for(conn, eid, Path(note_path)):
            touched += 1
    if touched:
        _log(f"rollups rewritten on {touched} page(s)")
    return touched


# ---- the governance queue note ----------------------------------------------

_QUEUE_LINE_RE = re.compile(r"^\s*-\s*\[( |x|X)\]\s*\*\*(.+?)\*\*")
_QUEUE_SECTION_RE = re.compile(r"^###\s+Proposed\s+(projects|people)\s*$")
_SECTION_TYPE = {"projects": "project", "people": "person"}


def _proposed(conn):
    return conn.execute(
        "SELECT entity_id, name, type FROM entities WHERE status='proposed' "
        "ORDER BY type, name COLLATE NOCASE"
    ).fetchall()


def write_queue_note(conn, vault_dir) -> None:
    """Regenerate Inbox/Governance.md from all status='proposed' entities,
    and record (in meta) exactly which names were published so a later
    apply_queue_edits() can tell a user deletion from a never-published row."""
    import db as dbmod

    vault_dir = Path(vault_dir)
    proposed = _proposed(conn)
    by_type = {"project": [], "person": []}
    for eid, name, etype in proposed:
        if etype in by_type:
            by_type[etype].append((eid, name))

    lines = [
        "## Governance queue",
        "*Check a box to ratify. Delete a line to reject.*",
        "",
    ]
    for etype, heading in (("project", "### Proposed projects"), ("person", "### Proposed people")):
        lines.append(heading)
        if not by_type[etype]:
            lines.append("*(nothing pending)*")
        else:
            for eid, name in by_type[etype]:
                titles = _meeting_titles_for(conn, eid)
                seen = ", ".join(f"[[{t}]]" for t in titles[:3])
                lines.append(f"- [ ] **{name}**" + (f" — seen in {seen}" if seen else ""))
        lines.append("")

    content = "\n".join(lines).rstrip() + "\n"
    note = vault_dir / QUEUE_NOTE
    note.parent.mkdir(parents=True, exist_ok=True)
    old = note.read_text(encoding="utf-8", errors="replace") if note.exists() else None
    if old != content:
        note.write_text(content, encoding="utf-8")
        _log(f"queue note rewritten with {len(by_type['project'])} project / "
             f"{len(by_type['person'])} person proposal(s)")
    dbmod.set_meta(conn, META_QUEUE_HASH, _sha1(content))
    dbmod.set_meta(
        conn, META_QUEUE_NAMES,
        json.dumps({t: [n for _e, n in by_type[t]] for t in by_type}),
    )


def apply_queue_edits(conn, vault_dir) -> dict:
    """Parse Inbox/Governance.md and act on the user's edits: a checked box
    ratifies (page created, status flipped), a published proposal line that
    has been deleted from the note rejects (persisted, never re-proposed).
    Returns {"ratified": [names], "rejected": [names]}."""
    import db as dbmod

    vault_dir = Path(vault_dir)
    result = {"ratified": [], "rejected": []}
    note = vault_dir / QUEUE_NOTE
    if not note.exists():
        return result
    content = note.read_text(encoding="utf-8", errors="replace")
    if _sha1(content) == dbmod.get_meta(conn, META_QUEUE_HASH):
        return result  # byte-identical to what we last wrote: no user edits

    checked: dict[str, list[str]] = {"project": [], "person": []}
    present: dict[str, list[str]] = {"project": [], "person": []}
    section = None
    for line in content.splitlines():
        sm = _QUEUE_SECTION_RE.match(line.strip())
        if sm:
            section = _SECTION_TYPE[sm.group(1)]
            continue
        lm = _QUEUE_LINE_RE.match(line)
        if lm and section:
            name = lm.group(2).strip()
            present[section].append(name)
            if lm.group(1).lower() == "x":
                checked[section].append(name)

    def _find_proposed(etype: str, name: str):
        return conn.execute(
            "SELECT entity_id, name FROM entities "
            "WHERE type=? AND status='proposed' AND lower(name)=lower(?)",
            (etype, name),
        ).fetchone()

    def _find_proposed_variant(etype: str, name: str):
        rows = conn.execute(
            "SELECT entity_id, name, aliases FROM entities "
            "WHERE type=? AND status='proposed' ORDER BY name",
            (etype,),
        ).fetchall()
        matched = _match_in(rows, name)
        if matched is None:
            return None
        return next((r[0], r[1]) for r in rows if r[1] == matched)

    for etype in ("project", "person"):
        for name in checked[etype]:
            row = _find_proposed(etype, name)
            if row is None:
                # The user may have edited the proposal's name before checking
                # it. Structure is user-authored: the edited name wins as the
                # canonical name, resolved to its row by variant matching.
                row = _find_proposed_variant(etype, name)
                if row:
                    conn.execute("UPDATE entities SET name=? WHERE entity_id=?",
                                 (name, row[0]))
                    conn.commit()
                    row = (row[0], name)
            if row:
                ratify(conn, row[0], vault_dir)
                result["ratified"].append(row[1])

    # Deletions: only lines WE published can have been deleted by the user --
    # and a published name that still variant-matches a present line was
    # renamed, not deleted, so it is not a rejection.
    try:
        published = json.loads(dbmod.get_meta(conn, META_QUEUE_NAMES) or "{}")
    except json.JSONDecodeError:
        published = {}
    for etype in ("project", "person"):
        present_lower = {n.lower() for n in present[etype]}
        for name in published.get(etype, []):
            if name.lower() in present_lower:
                continue
            if any(_is_name_variant(name, p) or _is_name_variant(p, name)
                   for p in present[etype]):
                continue  # renamed in place, handled (or left pending) above
            row = _find_proposed(etype, name)
            if row:
                reject(conn, row[0])
                result["rejected"].append(row[1])

    if result["ratified"] or result["rejected"]:
        _log(f"queue edits applied: ratified={result['ratified']} rejected={result['rejected']}")
    return result


# ---- one-time migration from the insert-on-miss era -------------------------

def migrate(conn, vault_dir) -> dict:
    """Convert a pre-governance database: every existing entity (all invented
    by the old insert-on-miss extractor) becomes a proposal for the human to
    rule on; the generated Cairn/People and Cairn/Projects pages are deleted
    (ratified user-owned pages replace that whole layer); the initial
    governance queue note is written."""
    vault_dir = Path(vault_dir)
    n = conn.execute(
        "UPDATE entities SET status='proposed', note_path=NULL, "
        "origin=COALESCE(origin, 'extraction')"
    ).rowcount
    conn.commit()

    removed = 0
    for folder in ("People", "Projects"):
        d = vault_dir / "Cairn" / folder
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            p.unlink()
            removed += 1
        try:
            d.rmdir()
        except OSError:
            pass  # user parked something else in there; leave the folder

    scan = scan_vault(conn, vault_dir)  # honor any pages the user already made
    write_queue_note(conn, vault_dir)
    _log(f"migrate: {n} entities -> proposed, {removed} generated Cairn page(s) deleted, queue note written")
    return {"proposed": n, "pages_deleted": removed, "scan": scan}


# ---- CLI --------------------------------------------------------------------

def main():
    import config
    import db as dbmod

    ap = argparse.ArgumentParser(description="Cairn entity registry")
    ap.add_argument("--scan", action="store_true", help="resync the DB index from vault pages")
    ap.add_argument("--queue", action="store_true", help="apply queue edits, then rewrite the queue note")
    ap.add_argument("--migrate", action="store_true",
                    help="one-time: convert all existing entities to proposals, "
                         "delete generated Cairn/People|Projects pages, write the queue note")
    args = ap.parse_args()
    if not (args.scan or args.queue or args.migrate):
        ap.print_help()
        return

    conn = dbmod.connect()
    dbmod.init_db(conn)
    try:
        if args.migrate:
            summary = migrate(conn, config.VAULT_DIR)
            print(f"migrated: {summary}")
        if args.scan:
            print(f"scanned: {scan_vault(conn, config.VAULT_DIR)}")
        if args.queue:
            edits = apply_queue_edits(conn, config.VAULT_DIR)
            write_queue_note(conn, config.VAULT_DIR)
            regenerate_rollups(conn, config.VAULT_DIR)
            print(f"queue: {edits}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

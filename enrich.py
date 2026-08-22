"""
Cairn semantic enrichment: meeting transcripts -> entities, front-matter
metadata, a marked machine-contributions block, a distillation draft, and
the derived index notes under Cairn/.

Called from ingest.py, and only for sources under sources/transcripts/, and
only when ingest.py has just (re)converted the file -- never on a hash/mtime
skip, so re-running ingest on unchanged sources never re-enriches, never
duplicates entities, blocks, or drafts.

Thesis constraints this module exists to honor (see docs/THESIS.md sections
2, 3, 5, 6):
  - Personal content is never rewritten. The meeting note's body is the
    verbatim converted transcript; every machine contribution lands either
    in front matter or in the one clearly marked block appended at the end.
    No inline [[links]] woven into the transcript text.
  - Distillation output is a draft awaiting ratification. Drafts are written
    to Inbox/, never to sources/, so they never enter the documents/chunks
    tables and are never embedded or citable.
  - Derived index notes (Cairn/Home.md, Cairn/Meetings.md, Cairn/People/*,
    Cairn/Projects/*) are marked generated and fully regenerable from the
    entities table, the documents table, and the vault files on disk.

Uses Ollama chat (config.OLLAMA_CHAT_URL / config.GEN_MODEL) with strict
JSON-output prompting, one retry on malformed output, and graceful
degradation: if the model still won't cooperate, enrichment is skipped with
a logged warning and ingest continues (the note is still written, just
without attendees/projects/block/draft).
"""

import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import config

# ---- model call -------------------------------------------------------------

TEMPERATURE = 0
NUM_PREDICT = 1200
NUM_CTX = 16384  # matches the llama-server -c 16384 this Ollama model is served with

# Generous headroom: the longest of the three real transcripts is ~21K chars
# (~5-6K tokens). Cap well above that so a much longer transcript degrades
# (truncates, logged) instead of silently blowing the model's context window.
MAX_TRANSCRIPT_CHARS = 32000

SYSTEM_PROMPT = (
    "You extract structured facts from a private meeting transcript. "
    "Output ONLY a single JSON object -- no prose, no markdown code fences, no explanation "
    "before or after it. If a field has nothing to report, use an empty list. "
    "Never invent facts not present in the transcript. Use people's full names as spoken "
    "in the transcript; do not guess a surname that was never said.\n\n"
    "JSON schema (all keys required, use [] when empty):\n"
    "{\n"
    '  "attendees": ["<person name>", ...],\n'
    '  "projects": ["<project or product name>", ...],\n'
    '  "decisions": ["<one-sentence decision>", ...],\n'
    '  "commitments": [{"owner": "<name>", "task": "<what they owe>", "due": "<date or empty string>"}],\n'
    '  "action_items": [{"owner": "<name or empty string>", "task": "<what>"}],\n'
    '  "open_questions": ["<open question>", ...]\n'
    "}\n"
)


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


def _chat(messages: list[dict]) -> str | None:
    payload = json.dumps({
        "model": config.GEN_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "options": {
            "temperature": TEMPERATURE,
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        config.OLLAMA_CHAT_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("message", {}).get("content", "")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"  WARN enrich: Ollama chat call failed: {type(e).__name__}: {e}")
        return None


_FENCE_RE = re.compile(r'^```(?:json)?\s*|\s*```$', re.MULTILINE)


def _extract_json(raw: str | None) -> dict | None:
    if not raw:
        return None
    text = _FENCE_RE.sub('', raw.strip()).strip()
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end == -1 or end < start:
        return None
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _coerce(obj: dict) -> dict:
    """Normalize a parsed JSON object to the expected shape, tolerating minor drift
    from a small model (e.g. a plain string in a list of objects)."""

    def strs(v):
        return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []

    def items(v, keys):
        out = []
        if not isinstance(v, list):
            return out
        for x in v:
            if isinstance(x, dict):
                out.append({k: str(x.get(k, "") or "").strip() for k in keys})
            elif isinstance(x, str) and x.strip():
                d = {k: "" for k in keys}
                d[keys[-1]] = x.strip()
                out.append(d)
        return out

    return {
        "attendees": strs(obj.get("attendees")),
        "projects": strs(obj.get("projects")),
        "decisions": strs(obj.get("decisions")),
        "commitments": items(obj.get("commitments"), ["owner", "task", "due"]),
        "action_items": items(obj.get("action_items"), ["owner", "task"]),
        "open_questions": strs(obj.get("open_questions")),
    }


def extract(text: str) -> dict | None:
    """Call the model, validate, retry once on malformed JSON. None on failure."""
    body = text if len(text) <= MAX_TRANSCRIPT_CHARS else text[:MAX_TRANSCRIPT_CHARS]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Transcript:\n\n{body}"},
    ]
    for _ in range(2):
        raw = _chat(messages)
        parsed = _extract_json(raw)
        if parsed is not None:
            return _coerce(parsed)
        messages.append({"role": "assistant", "content": raw or ""})
        messages.append({
            "role": "user",
            "content": "That was not valid JSON. Return ONLY the JSON object matching the schema, nothing else.",
        })
    return None


# ---- filenames ---------------------------------------------------------------

_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|]')


def sanitize_filename(name: str) -> str:
    cleaned = _UNSAFE_CHARS.sub('-', name).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned or "untitled"


# ---- entity canonicalization --------------------------------------------------

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


def canonicalize_entity(conn, name: str, etype: str) -> str | None:
    """
    Match `name` against existing entities of `etype`:
      1. case-insensitive exact match on canonical name or an alias -> return as-is
      2. `name` is a shorter variant of an existing canonical name -> folds in as
         an alias of that entity; the longer canonical name is returned
      3. `name` is a longer variant of an existing canonical name -> the entity's
         canonical name is upgraded to `name`, the old canonical becomes an alias
      4. no match -> a new entity row is inserted, canonical = name as given
    Always returns the canonical name that should be used for links/front matter.
    """
    name = (name or "").strip()
    if not name:
        return None
    name_lower = name.lower()
    rows = conn.execute(
        "SELECT entity_id, name, aliases FROM entities WHERE type=?", (etype,)
    ).fetchall()

    for entity_id, canon_name, aliases_json in rows:
        aliases = json.loads(aliases_json or "[]")
        if name_lower == canon_name.lower() or name_lower in (a.lower() for a in aliases):
            return canon_name

    for entity_id, canon_name, aliases_json in rows:
        aliases = json.loads(aliases_json or "[]")
        if len(name) <= len(canon_name) and _is_name_variant(name, canon_name):
            if name not in aliases:
                aliases.append(name)
                conn.execute("UPDATE entities SET aliases=? WHERE entity_id=?",
                             (json.dumps(aliases), entity_id))
                conn.commit()
            return canon_name
        if len(name) > len(canon_name) and _is_name_variant(canon_name, name):
            if canon_name not in aliases:
                aliases.append(canon_name)
            conn.execute("UPDATE entities SET name=?, aliases=? WHERE entity_id=?",
                         (name, json.dumps(aliases), entity_id))
            conn.commit()
            return name

    entity_id = _sha1(f"{etype}:{name_lower}")[:16]
    conn.execute(
        "INSERT INTO entities (entity_id, name, type, aliases, note_path) VALUES (?,?,?,?,?)",
        (entity_id, name, etype, "[]", None),
    )
    conn.commit()
    return name


# ---- Gemini export conversion cleanup ------------------------------------------

_GEMINI_ACTION_RE = re.compile(r'^(\s*- \[ \] )\\\[(.+?)\\\]', flags=re.MULTILINE)


def lookup_canonical(conn, name: str) -> str | None:
    """Read-only entity lookup by canonical name or alias, people before
    projects. Unlike canonicalize_entity, never inserts or mutates anything."""
    name_lower = (name or "").strip().lower()
    if not name_lower:
        return None
    for etype in ("person", "project"):
        for canon_name, aliases_json in conn.execute(
            "SELECT name, aliases FROM entities WHERE type=?", (etype,)
        ).fetchall():
            aliases = json.loads(aliases_json or "[]")
            if name_lower == canon_name.lower() or name_lower in (a.lower() for a in aliases):
                return canon_name
    return None


def linkify_gemini_artifacts(conn, text: str) -> str:
    """Deterministic conversion cleanup for Gemini "Notes by Gemini" exports,
    applied ONLY to the note body written into the vault -- never to the source
    file and never to the chunked/embedded text. Two rules:

      1. Gemini's action attribution `- [ ] \\[Name\\]` becomes a real wikilink,
         canonicalized through the entity registry: `- [ ] [[Canonical|Name]]`
         (plain `[[Name]]` when the name is already canonical or unknown).
      2. Leftover `\\[` / `\\]` escape artifacts unescape to plain brackets.

    This is import-time conversion, not a post-hoc rewrite of personal content:
    the vault note is being created here, and Gemini escaped these brackets
    only so generic markdown would not misrender them. Obsidian is exactly the
    place they SHOULD render as links."""
    def _repl(m):
        prefix, name = m.group(1), m.group(2).strip()
        canonical = lookup_canonical(conn, name)
        if canonical and canonical != name:
            return f"{prefix}[[{canonical}|{name}]]"
        return f"{prefix}[[{name}]]"

    out = _GEMINI_ACTION_RE.sub(_repl, text)
    return out.replace("\\[", "[").replace("\\]", "]")


# ---- the marked block + distillation draft ------------------------------------

def build_cairn_block(enrich_result: dict) -> str:
    """The one clearly marked block appended after the verbatim transcript body.
    Everything the machine contributes to a personal note lives here (or in
    front matter) -- never woven inline into the transcript text."""
    lines = [
        "",
        "",
        "<!-- cairn:begin -->",
        "## Cairn",
        "*Generated by Cairn — links and context. The transcript above is untouched.*",
        "",
    ]
    attendees = enrich_result.get("attendees") or []
    projects = enrich_result.get("projects") or []
    if attendees:
        lines.append("**Attendees**: " + ", ".join(f"[[{a}]]" for a in attendees))
    if projects:
        label = "Project" if len(projects) == 1 else "Projects"
        lines.append(f"**{label}**: " + ", ".join(f"[[{p}]]" for p in projects))
    lines.append(f"**Distillation**: [[{enrich_result['distillation']}]]")
    lines.append("<!-- cairn:end -->")
    lines.append("")
    return "\n".join(lines)


def write_distillation_draft(title: str, result: dict) -> str:
    """Writes Inbox/<title> — distillation.md. Never touched by ingest.py's
    sources/ scan, so it never enters documents/chunks -- never chunked,
    never embedded, never citable, per the thesis draft-until-ratified rule.
    Returns the note's filename stem (for [[links]])."""
    stem = sanitize_filename(f"{title} — distillation")
    path = config.VAULT_DIR / "Inbox" / f"{stem}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    def bullets(items, empty="(none noted)"):
        return [f"- {i}" for i in items] if items else [f"- {empty}"]

    commitments = [
        f"- **{(c.get('owner') or 'Unassigned')}**: {c.get('task', '')}"
        + (f" (due {c['due']})" if c.get("due") else "")
        for c in (result.get("commitments") or [])
    ] or ["- (none noted)"]

    action_items = [
        f"- {'**' + a['owner'] + '**: ' if a.get('owner') else ''}{a.get('task', '')}"
        for a in (result.get("action_items") or [])
    ] or ["- (none noted)"]

    lines = [
        "---",
        "type: distillation-draft",
        "status: draft",
        "generated: true",
        f'source: "[[{title}]]"',
        "---",
        "",
        f"# Distillation — {title}",
        "",
        "## Decisions",
        *bullets(result.get("decisions") or []),
        "",
        "## Commitments",
        *commitments,
        "",
        "## Action Items",
        *action_items,
        "",
        "## Open Questions",
        *bullets(result.get("open_questions") or []),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path.stem


# ---- orchestration: one meeting document --------------------------------------

def enrich_meeting(conn, doc_id: str, source: Path, title: str, text: str) -> dict | None:
    """
    Runs the model, canonicalizes attendees/projects into the entities table,
    records the doc<->entity relationship, and writes the distillation draft.
    Returns {"attendees": [...], "projects": [...], "distillation": "<stem>"}
    on success, or None if enrichment could not be completed (ingest continues
    regardless -- the note is still written, just without the block/draft).
    """
    result = extract(text)
    if result is None:
        print(f"  WARN enrich: skipping enrichment for {source.name} "
              f"(model did not return valid JSON after retry)")
        return None

    attendees = sorted(
        {c for n in result["attendees"] if (c := canonicalize_entity(conn, n, "person"))},
        key=str.lower,
    )
    projects = sorted(
        {c for n in result["projects"] if (c := canonicalize_entity(conn, n, "project"))},
        key=str.lower,
    )

    conn.execute("DELETE FROM meeting_entities WHERE doc_id=?", (doc_id,))
    for etype, names in (("person", attendees), ("project", projects)):
        for name in names:
            row = conn.execute(
                "SELECT entity_id FROM entities WHERE type=? AND name=?", (etype, name)
            ).fetchone()
            if row:
                conn.execute(
                    "INSERT OR IGNORE INTO meeting_entities (doc_id, entity_id) VALUES (?,?)",
                    (doc_id, row[0]),
                )
    conn.commit()

    distill_stem = write_distillation_draft(title, result)

    return {"attendees": attendees, "projects": projects, "distillation": distill_stem}


# ---- derived index notes -------------------------------------------------------

def _write_generated(path: Path, extra_front_matter: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "---\ngenerated: true\n" + extra_front_matter + "---\n\n" + body.rstrip() + "\n"
    path.write_text(content, encoding="utf-8")


def _meeting_files(conn) -> list[Path]:
    rows = conn.execute("SELECT vault_path FROM documents").fetchall()
    out = []
    for (vp,) in rows:
        if not vp:
            continue
        p = Path(vp)
        if p.parent.name == "Meetings" and p.exists():
            out.append(p)
    return out


_DATE_PREFIX_RE = re.compile(r'^(\d{4})-(\d{2})-(\d{2}) ')


def regenerate_meetings_index(conn) -> None:
    files = _meeting_files(conn)
    by_month: dict[tuple[str, str], list[str]] = {}
    for p in files:
        m = _DATE_PREFIX_RE.match(p.stem)
        key = (m.group(1), m.group(2)) if m else ("0000", "00")
        by_month.setdefault(key, []).append(p.stem)

    lines = ["# Meetings", ""]
    if not by_month:
        lines.append("*(no meeting notes yet)*")
    for (y, mo) in sorted(by_month.keys(), reverse=True):
        try:
            from datetime import datetime
            label = datetime(int(y), int(mo), 1).strftime("%B %Y")
        except ValueError:
            label = f"{y}-{mo}"
        lines.append(f"## {label}")
        for stem in sorted(by_month[(y, mo)]):
            lines.append(f"- [[{stem}]]")
        lines.append("")

    _write_generated(config.VAULT_DIR / "Cairn" / "Meetings.md", "type: meeting-index\n", "\n".join(lines))


def _entity_meeting_titles(conn, entity_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT d.vault_path FROM meeting_entities me "
        "JOIN documents d ON d.doc_id = me.doc_id WHERE me.entity_id=?",
        (entity_id,),
    ).fetchall()
    titles = []
    for (vp,) in rows:
        if vp and Path(vp).exists():
            titles.append(Path(vp).stem)
    return sorted(titles)


def regenerate_entity_pages(conn) -> None:
    rows = conn.execute("SELECT entity_id, name, type, aliases FROM entities").fetchall()
    for entity_id, name, etype, aliases_json in rows:
        aliases = json.loads(aliases_json or "[]")
        meetings = _entity_meeting_titles(conn, entity_id)
        folder = "People" if etype == "person" else "Projects"
        note_path = config.VAULT_DIR / "Cairn" / folder / f"{sanitize_filename(name)}.md"

        context = f"Also known as: {', '.join(aliases)}. " if aliases else ""
        context += f"Appears in {len(meetings)} meeting note{'s' if len(meetings) != 1 else ''}."

        lines = [f"# {name}", "", context, "", "## Meetings"]
        lines += [f"- [[{t}]]" for t in meetings] if meetings else ["*(none yet)*"]

        _write_generated(note_path, f"type: {etype}\n", "\n".join(lines))
        conn.execute("UPDATE entities SET note_path=? WHERE entity_id=?", (str(note_path), entity_id))
    conn.commit()


def regenerate_home(conn) -> None:
    people = conn.execute(
        "SELECT name FROM entities WHERE type='person' ORDER BY name COLLATE NOCASE"
    ).fetchall()
    projects = conn.execute(
        "SELECT name FROM entities WHERE type='project' ORDER BY name COLLATE NOCASE"
    ).fetchall()
    inbox_dir = config.VAULT_DIR / "Inbox"
    drafts = sorted((p.stem for p in inbox_dir.glob("*.md")), key=str.lower) if inbox_dir.exists() else []

    lines = ["# Cairn Home", "", "- [[Meetings]]", "", "## People"]
    lines += [f"- [[{n}]]" for (n,) in people] or ["*(none yet)*"]
    lines += ["", "## Projects"]
    lines += [f"- [[{n}]]" for (n,) in projects] or ["*(none yet)*"]
    lines += ["", "## Inbox"]
    lines += [f"- [[{d}]]" for d in drafts] or ["*(empty)*"]

    _write_generated(config.VAULT_DIR / "Cairn" / "Home.md", "type: home\n", "\n".join(lines))


def regenerate_index_notes(conn) -> None:
    """Regenerates every derived index note under Cairn/ from current DB +
    vault-on-disk state. Fully idempotent, cheap, safe to call unconditionally
    after every ingest run and after every prune."""
    regenerate_meetings_index(conn)
    regenerate_entity_pages(conn)
    regenerate_home(conn)

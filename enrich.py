"""
Cairn semantic enrichment: meeting transcripts -> entities, front-matter
metadata, a marked machine-contributions block, a distillation draft, and
the derived index notes under Cairn/.

Called from ingest.py, and only for sources under sources/transcripts/, and
only when ingest.py has just (re)converted the file -- never on a hash/mtime
skip, so re-running ingest on unchanged sources never re-enriches, never
duplicates entities, blocks, or drafts.

Thesis constraints this module exists to honor (see docs/THESIS.md sections
2, 3, 5, 6, and the 2026-08-22 governance decisions in docs/DECISIONS.md):
  - Personal content is never rewritten. The meeting note's body is the
    verbatim converted transcript; every machine contribution lands either
    in front matter or in the one clearly marked block appended at the end.
    No inline [[links]] woven into the transcript text.
  - Structure is user-authored; the engine conforms. Extracted names go
    through registry.match against RATIFIED entities only: a match becomes
    a wikilink to the user-owned entity page, anything else becomes a
    registry.propose() row in the governance queue and stays plain text --
    no page, no link, no embedding until a human ratifies. Discussion
    topics are journaled-tier: they land as front-matter tags on the
    meeting note, never as entities or proposals.
  - Distillation output is a draft awaiting ratification. Drafts are written
    to Inbox/, never to sources/, so they never enter the documents/chunks
    tables and are never embedded or citable.
  - Derived index notes (Cairn/Home.md, Cairn/Meetings.md) are marked
    generated and fully regenerable. The old generated Cairn/People and
    Cairn/Projects pages are retired: ratified user-owned pages at the
    vault root replace them, with registry.regenerate_rollups() rewriting
    only the marked block on each.

Uses Ollama chat (config.OLLAMA_CHAT_URL / config.GEN_MODEL) with strict
JSON-output prompting, one retry on malformed output, and graceful
degradation: if the model still won't cooperate, enrichment is skipped with
a logged warning and ingest continues (the note is still written, just
without attendees/projects/block/draft).
"""

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import config
import registry

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
    "in the transcript; do not guess a surname that was never said. "
    "A project is a named initiative or product the speakers own or work on; a subject "
    "that was merely discussed belongs in topics, never in projects.\n\n"
    "JSON schema (all keys required, use [] when empty):\n"
    "{\n"
    '  "attendees": ["<person name>", ...],\n'
    '  "projects": ["<project or product name>", ...],\n'
    '  "topics": ["<discussion topic, 1-4 words>", ...],\n'
    '  "decisions": ["<one-sentence decision>", ...],\n'
    '  "commitments": [{"owner": "<name>", "task": "<what they owe>", "due": "<date or empty string>"}],\n'
    '  "action_items": [{"owner": "<name or empty string>", "task": "<what>"}],\n'
    '  "open_questions": ["<open question>", ...]\n'
    "}\n"
)


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
        "topics": strs(obj.get("topics")),
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


# ---- topic tags ----------------------------------------------------------------
# Discussion topics are journaled-tier: normalized to kebab-case front-matter
# tags on the meeting note. No entity row, no proposal, no page -- searchable
# at zero ratification cost, which is what keeps the governance inbox small.

_TAG_STRIP_RE = re.compile(r'[^a-z0-9]+')


def topic_tag(topic: str) -> str | None:
    tag = _TAG_STRIP_RE.sub('-', (topic or "").lower()).strip('-')
    tag = re.sub(r'-{2,}', '-', tag)
    if not tag or len(tag) > 60 or not re.search(r'[a-z]', tag):
        return None  # empty, absurdly long, or all-numeric: not a usable tag
    return tag


def topic_tags(topics: list[str]) -> list[str]:
    out = []
    for t in topics or []:
        tag = topic_tag(t)
        if tag and tag not in out:
            out.append(tag)
    return out


# ---- Gemini export conversion cleanup ------------------------------------------

_GEMINI_ACTION_RE = re.compile(r'^(\s*- \[ \] )\\\[(.+?)\\\]', flags=re.MULTILINE)


def lookup_canonical(conn, name: str) -> str | None:
    """Read-only lookup against RATIFIED entities only, people before
    projects. Never inserts or mutates anything -- unratified names must not
    acquire links (registry decision, 2026-08-22)."""
    if not (name or "").strip():
        return None
    for etype in ("person", "project"):
        canonical = registry.match(conn, name, etype)
        if canonical:
            return canonical
    return None


def linkify_gemini_artifacts(conn, text: str) -> str:
    """Deterministic conversion cleanup for Gemini "Notes by Gemini" exports,
    applied ONLY to the note body written into the vault -- never to the source
    file and never to the chunked/embedded text. Two rules:

      1. Gemini's action attribution `- [ ] \\[Name\\]` becomes a real wikilink
         ONLY when the name matches a ratified registry entity:
         `- [ ] [[Canonical|Name]]` (or `[[Name]]` when already canonical).
         An unratified name stays plain text -- the engine links into
         user-ratified structure and never mints a link to a page that does
         not exist.
      2. Leftover `\\[` / `\\]` escape artifacts unescape to plain brackets.

    This is import-time conversion, not a post-hoc rewrite of personal content:
    the vault note is being created here, and Gemini escaped these brackets
    only so generic markdown would not misrender them. Obsidian is exactly the
    place they SHOULD render as links."""
    def _repl(m):
        prefix, name = m.group(1), m.group(2).strip()
        canonical = lookup_canonical(conn, name)
        if canonical is None:
            # Not ratified: no wikilink. Keep Gemini's own [Name] attribution
            # style, just unescaped -- plain brackets, not a link.
            return f"{prefix}[{name}]"
        if canonical != name:
            return f"{prefix}[[{canonical}|{name}]]"
        return f"{prefix}[[{name}]]"

    out = _GEMINI_ACTION_RE.sub(_repl, text)
    return out.replace("\\[", "[").replace("\\]", "]")


# ---- the marked block + distillation draft ------------------------------------

def build_cairn_block(enrich_result: dict) -> str:
    """The one clearly marked block appended after the verbatim transcript body.
    Everything the machine contributes to a personal note lives here (or in
    front matter) -- never woven inline into the transcript text. Only names
    matched against RATIFIED registry entities become wikilinks; unmatched
    names (which registry.propose sent to the governance queue) stay plain
    text, because a link to a page that does not exist would be the engine
    minting structure."""
    lines = [
        "",
        "",
        "<!-- cairn:begin -->",
        "## Cairn",
        "*Generated by Cairn — links and context. The transcript above is untouched.*",
        "",
    ]
    linked_people = enrich_result.get("linked_people") or set()
    linked_projects = enrich_result.get("linked_projects") or set()

    def render(name, linked):
        return f"[[{name}]]" if name in linked else name

    attendees = enrich_result.get("attendees") or []
    projects = enrich_result.get("projects") or []
    if attendees:
        lines.append("**Attendees**: " + ", ".join(render(a, linked_people) for a in attendees))
    if projects:
        label = "Project" if len(projects) == 1 else "Projects"
        lines.append(f"**{label}**: " + ", ".join(render(p, linked_projects) for p in projects))
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
    Runs the model, resolves attendees/projects against the RATIFIED registry
    (registry.match -- read-only), files a governance proposal for anything
    unmatched (registry.propose -- no page, no link), records the doc<->entity
    relationship for matched entities, and writes the distillation draft.

    Returns {"attendees": [...], "projects": [...], "linked_people": set,
    "linked_projects": set, "topics": [tags], "distillation": "<stem>"} on
    success, or None if enrichment could not be completed (ingest continues
    regardless -- the note is still written, just without the block/draft).
    """
    result = extract(text)
    if result is None:
        print(f"  WARN enrich: skipping enrichment for {source.name} "
              f"(model did not return valid JSON after retry)")
        return None

    # Rewritten wholesale per doc: matched links are re-recorded below, and
    # registry.propose re-records proposal provenance as it runs.
    conn.execute("DELETE FROM meeting_entities WHERE doc_id=?", (doc_id,))
    conn.commit()

    names: dict[str, list[str]] = {}
    linked: dict[str, set[str]] = {}
    proposed_count = 0
    for etype, key in (("person", "attendees"), ("project", "projects")):
        names[key], linked[key] = [], set()
        seen = set()
        for raw in result[key]:
            raw = raw.strip()
            if not raw or raw.lower() in seen:
                continue
            seen.add(raw.lower())
            canonical = registry.match(conn, raw, etype)
            if canonical:
                if canonical not in names[key]:
                    names[key].append(canonical)
                linked[key].add(canonical)
                row = conn.execute(
                    "SELECT entity_id FROM entities WHERE type=? AND name=? AND status='ratified'",
                    (etype, canonical),
                ).fetchone()
                if row:
                    conn.execute(
                        "INSERT OR IGNORE INTO meeting_entities (doc_id, entity_id) VALUES (?,?)",
                        (doc_id, row[0]),
                    )
            else:
                if registry.propose(conn, raw, etype, doc_id):
                    proposed_count += 1
                if raw not in names[key]:
                    names[key].append(raw)
        names[key].sort(key=str.lower)
    conn.commit()

    tags = topic_tags(result.get("topics") or [])
    print(f"  enrich: {source.name}: linked {len(linked['attendees'])} people / "
          f"{len(linked['projects'])} projects, proposed {proposed_count}, "
          f"{len(tags)} topic tag(s)")

    distill_stem = write_distillation_draft(title, result)

    return {
        "attendees": names["attendees"],
        "projects": names["projects"],
        "linked_people": linked["attendees"],
        "linked_projects": linked["projects"],
        "topics": tags,
        "distillation": distill_stem,
    }


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


# The old regenerate_entity_pages (generated Cairn/People/* and
# Cairn/Projects/* pages) is RETIRED: ratified user-owned pages at the vault
# root replace that layer, and their per-entity meeting rollup lives inside
# the cairn-marked block, rewritten by registry.regenerate_rollups() only.


def regenerate_home(conn) -> None:
    """Home links only RATIFIED structure -- the user-owned vault-root pages.
    Proposals are deliberately absent: they live in Inbox/Governance.md until
    a human rules on them."""
    people = conn.execute(
        "SELECT name FROM entities WHERE type='person' AND status='ratified' "
        "ORDER BY name COLLATE NOCASE"
    ).fetchall()
    projects = conn.execute(
        "SELECT name FROM entities WHERE type='project' AND status='ratified' "
        "ORDER BY name COLLATE NOCASE"
    ).fetchall()
    pending = conn.execute(
        "SELECT COUNT(*) FROM entities WHERE status='proposed'"
    ).fetchone()[0]
    inbox_dir = config.VAULT_DIR / "Inbox"
    drafts = sorted((p.stem for p in inbox_dir.glob("*.md")), key=str.lower) if inbox_dir.exists() else []

    lines = ["# Cairn Home", "", "- [[Meetings]]"]
    if pending:
        lines.append(f"- [[Governance]] — {pending} proposal(s) awaiting review")
    lines += ["", "## People"]
    lines += [f"- [[{n}]]" for (n,) in people] or ["*(none yet)*"]
    lines += ["", "## Projects"]
    lines += [f"- [[{n}]]" for (n,) in projects] or ["*(none yet)*"]
    lines += ["", "## Inbox"]
    lines += [f"- [[{d}]]" for d in drafts] or ["*(empty)*"]

    _write_generated(config.VAULT_DIR / "Cairn" / "Home.md", "type: home\n", "\n".join(lines))


def regenerate_index_notes(conn) -> None:
    """Regenerates every derived surface from current DB + vault-on-disk
    state: the Cairn/ index notes, the governance queue note, and the marked
    rollup blocks on ratified entity pages. Applies any pending queue edits
    FIRST so a user's checkmark or deletion is never overwritten by the
    rewrite. Idempotent, cheap, safe to call unconditionally after every
    ingest run and after every prune."""
    registry.apply_queue_edits(conn, config.VAULT_DIR)
    regenerate_meetings_index(conn)
    regenerate_home(conn)
    registry.write_queue_note(conn, config.VAULT_DIR)
    registry.regenerate_rollups(conn, config.VAULT_DIR)

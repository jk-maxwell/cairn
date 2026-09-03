"""
Cairn interview engine: onboarding (/interview) and status check-in (/checkin),
run inside the plugin chat.

Why this exists (DECISIONS 2026-08-22): the organizing structure -- projects,
people, profile -- is user-authored, and interviews are how it is seeded and
kept current. The user's in-chat confirmation of the final playback IS the
ratification; nothing is written to the vault before that confirmation.

How state works -- THE SERVER STAYS STATELESS:
  The plugin sends the full conversation history on every request. Each
  assistant turn this module produces ends with an invisible HTML-comment
  marker, e.g.  <!--cairn-iv:{"f":"ob","s":"projects","n":0}-->  which
  Obsidian's markdown renderer hides but the client faithfully echoes back
  inside the history. On every request the flow position is reconstructed
  from the transcript: find the last /interview or /checkin trigger, read the
  last marker after it, pair each marked assistant question with the user
  reply that follows it. The playback step carries the full parsed structure
  in its marker ("d"), so the confirm turn can write exactly what was played
  back without re-parsing.

Division of labour: the question SCRIPT is deterministic code; the model
(config.GEN_MODEL via llm.chat, temperature 0, the same pattern as enrich.py)
is used ONLY to parse the user's free-text answers into structured JSON, with
one retry on malformed output and graceful degradation.

Writes on confirmation:
  - Profile.md at the vault root (front matter `cairn-type: profile`), the
    user's own words played back and confirmed -- personal content by adoption.
  - One entity page per confirmed project/person in Projects/ / People/ via
    registry.ratify(), origin='interview'.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import config
import db as dbmod

import llm
import registry
from registry import ensure_entity_columns

log = logging.getLogger("cairn.interview")

# ---- model call (same pattern as enrich.py) ---------------------------------

TEMPERATURE = 0
NUM_PREDICT = 1500

STALE_DAYS = 14          # a ratified project unmentioned this long is "gone quiet"
RECENT_MEETINGS = 3      # how many recent meeting titles the check-in mentions


def _chat(messages: list[dict]) -> str | None:
    try:
        return llm.chat(messages, stream=False, temperature=TEMPERATURE, max_tokens=NUM_PREDICT)
    except llm.LLMError as e:
        log.warning("interview: generation chat call failed: %s", e)
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


def _parse_with_retry(system: str, user: str) -> dict | None:
    """Call the model, retry once on malformed JSON, None on failure."""
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    for attempt in (1, 2):
        raw = _chat(messages)
        parsed = _extract_json(raw)
        if parsed is not None:
            return parsed
        log.warning("interview: parse attempt %d returned malformed JSON", attempt)
        messages.append({"role": "assistant", "content": raw or ""})
        messages.append({"role": "user",
                         "content": "That was not valid JSON. Return ONLY the JSON object "
                                    "matching the schema, nothing else."})
    return None


# ---- the invisible state marker ---------------------------------------------

_MARK_RE = re.compile(r"<!--cairn-iv:(\{.*?\})-->", re.DOTALL)


def _encode_marker(obj: dict) -> str:
    # ">" only ever occurs inside JSON string literals, where > is a legal
    # escape -- so the comment can never be terminated early by payload content.
    blob = json.dumps(obj, ensure_ascii=True).replace(">", "\\u003e")
    return f"\n\n<!--cairn-iv:{blob}-->"


def _decode_marker(text: str) -> dict | None:
    found = _MARK_RE.findall(text or "")
    if not found:
        return None
    try:
        return json.loads(found[-1])
    except json.JSONDecodeError:
        return None


# ---- transcript reconstruction ----------------------------------------------

def _flatten(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content
                       if isinstance(p, dict) and p.get("type") in (None, "text"))
    return ""


def _norm_messages(messages) -> list[dict]:
    return [{"role": m.get("role"), "content": _flatten(m.get("content"))}
            for m in (messages or []) if isinstance(m, dict)]


def _trigger_flow(text: str) -> str | None:
    t = (text or "").strip().lower()
    if t.startswith("/interview"):
        return "ob"
    if t.startswith("/checkin") or t.startswith("/check-in"):
        return "ci"
    return None


def reconstruct(messages) -> dict | None:
    """
    Rebuild the flow position from the transcript. Returns None when no
    interview is active (normal retrieval must be completely unaffected), else:
      {"flow": "ob"|"ci", "pairs": [(marker, answer_text)...],
       "last_marker": dict|None, "latest": str}
    """
    msgs = _norm_messages(messages)
    trig_idx, flow = None, None
    for i, m in enumerate(msgs):
        if m["role"] == "user":
            f = _trigger_flow(m["content"])
            if f:
                trig_idx, flow = i, f
    if trig_idx is None:
        return None

    after = msgs[trig_idx + 1:]
    # Terminated? A done/cancelled marker, or a /cancel that was already answered.
    for j, m in enumerate(after):
        if m["role"] == "assistant":
            mk = _decode_marker(m["content"])
            if mk and mk.get("s") in ("done", "cancelled"):
                return None
        if (m["role"] == "user" and m["content"].strip().lower() == "/cancel"
                and j < len(after) - 1):
            return None

    pairs, cur = [], None
    for m in after:
        if m["role"] == "assistant":
            mk = _decode_marker(m["content"])
            if mk:
                cur = mk
        elif m["role"] == "user" and cur is not None:
            pairs.append((cur, m["content"]))

    latest = ""
    for m in reversed(msgs):
        if m["role"] == "user":
            latest = m["content"]
            break

    last_marker = None
    for m in reversed(after):
        if m["role"] == "assistant":
            mk = _decode_marker(m["content"])
            if mk:
                last_marker = mk
                break

    return {"flow": flow, "pairs": pairs, "last_marker": last_marker, "latest": latest}


def is_interview(messages) -> bool:
    """True when this request belongs to an interview in progress (or starts one)."""
    return reconstruct(messages) is not None


# ---- the onboarding script (deterministic code, not the model) ---------------

# key, question, follow-up (None = never), thin-answer threshold in chars
ONBOARDING_STEPS = [
    ("role",
     "First up: what's your role, and what kind of organization do you work in?",
     "Got it. Anything else about the context worth knowing -- your team, "
     "your department, who you answer to?",
     25),
    ("projects",
     "What projects are you actively working on? One line each, using their real "
     "names -- plus any shorthand, aliases, or codenames people use for them.",
     "That was quick -- any others, even back-burner ones? Shorthand and "
     "codenames welcome.",
     20),
    ("people",
     "Who do you work with regularly? Names as they'd appear in a meeting "
     "transcript, plus any nicknames.",
     "Anyone else -- even occasional collaborators whose names show up in "
     "transcripts?",
     15),
    ("priorities",
     "What are your current priorities, and what does \"done\" look like for "
     "the big ones?",
     "And roughly when or how would you call the biggest one done?",
     30),
    ("vocab",
     "Last one: any team vocabulary worth knowing? Acronyms, codenames, "
     "shorthand that shows up in meetings.",
     None,
     0),
]

ONBOARDING_INTRO = (
    "Happy to -- let's set Cairn up. Five quick questions, one at a time; "
    "10-15 minutes tops. Nothing is written until you confirm the playback at "
    "the end, and you can type /cancel anytime.\n\n"
)

_ACKS = {"role": "Got it. ", "projects": "Noted. ", "people": "Thanks. ",
         "priorities": "Good. ", "vocab": "Perfect, that's everything I need. "}

_SKIP_WORDS = {"no", "none", "nope", "nothing", "skip", "n/a", "na", "not really",
               "no thanks", "nah", "that's it", "thats it", "that's all", "thats all", "done"}

_AFFIRM_WORDS = {"yes", "y", "yep", "yeah", "yup", "confirm", "confirmed", "correct",
                 "looks good", "looks right", "lgtm", "ok", "okay", "sure", "do it",
                 "write it", "ship it", "go ahead", "sounds good", "perfect"}


def _normalize_reply(text: str) -> str:
    return re.sub(r"[!.,\s]+$", "", (text or "").strip().lower())


def _is_affirmative(text: str) -> bool:
    # A bare yes confirms. A long reply starting with "yes" ("yes, but rename
    # X...") is a revision request, not a ratification -- route it to revise().
    t = _normalize_reply(text)
    return t in _AFFIRM_WORDS or (t.startswith("yes") and len(t) <= 12)


def _is_skip(text: str) -> bool:
    return _normalize_reply(text) in _SKIP_WORDS


# ---- check-in agenda (read from the DB before asking anything) ----------------

def build_agenda(conn) -> dict:
    """The informed part of the check-in: what the DB already knows."""
    ensure_entity_columns(conn)
    now = datetime.now(timezone.utc)

    stale = []
    for eid, name, last in conn.execute(
        "SELECT e.entity_id, e.name, MAX(d.ingested_at) "
        "FROM entities e "
        "LEFT JOIN meeting_entities me ON me.entity_id = e.entity_id "
        "LEFT JOIN documents d ON d.doc_id = me.doc_id "
        "WHERE e.type='project' AND (e.status='ratified' OR e.status IS NULL) "
        "GROUP BY e.entity_id ORDER BY e.name"
    ):
        weeks = None
        if last:
            try:
                dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                days = (now - dt).days
                if days < STALE_DAYS:
                    continue
                weeks = max(1, days // 7)
            except ValueError:
                pass
        stale.append({"n": name, "w": weeks})   # w=None -> never mentioned

    props = [{"n": n, "t": t} for n, t in conn.execute(
        "SELECT name, type FROM entities WHERE status='proposed' ORDER BY type, name")]

    recent = [r[0] for r in conn.execute(
        "SELECT source_name FROM documents ORDER BY ingested_at DESC LIMIT ?",
        (RECENT_MEETINGS,))]

    agenda = {"stale": stale, "props": props, "recent": recent}
    log.info("interview[ci]: agenda built -- %d stale, %d proposal(s), %d recent doc(s)",
             len(stale), len(props), len(recent))
    return agenda


def _checkin_steps(agenda: dict) -> list[str]:
    steps = []
    if agenda.get("stale"):
        steps.append("stale")
    if agenda.get("props"):
        steps.append("proposals")
    steps.append("new")
    return steps


def _checkin_question(step: str, agenda: dict) -> str:
    if step == "stale":
        lines = []
        for s in agenda["stale"]:
            if s["w"] is None:
                lines.append(f"- **{s['n']}** -- hasn't appeared in any meeting I've seen")
            else:
                lines.append(f"- **{s['n']}** -- hasn't come up in about {s['w']} week(s)")
        return ("A few projects have gone quiet:\n" + "\n".join(lines) +
                "\n\nStill active? Say so per project -- active, paused, or done.")
    if step == "proposals":
        lines = [f"- **{p['n']}** ({p['t']})" for p in agenda["props"]]
        return ("I've also seen these unmatched names come up, waiting in the "
                "governance queue:\n" + "\n".join(lines) +
                "\n\nAre any of them real projects or people I should track? "
                "Any I should drop?")
    return ("Anything new since last time -- new projects, new collaborators, "
            "changed priorities, new shorthand worth knowing?")


def _checkin_intro(agenda: dict) -> str:
    parts = ["Quick status check-in -- I read through what's accumulated first. "]
    if agenda.get("recent"):
        parts.append("Recent notes I have: " +
                     ", ".join(f"\"{t}\"" for t in agenda["recent"]) + ". ")
    parts.append("Nothing is written until you confirm the playback at the end; "
                 "/cancel anytime.\n\n")
    return "".join(parts)


# ---- parsing the user's answers (the model's ONLY job here) -------------------

ONBOARD_PARSE_SYSTEM = (
    "You turn interview answers into structured JSON. Output ONLY a single JSON "
    "object -- no prose, no markdown fences. Use ONLY names the user actually "
    "wrote; never invent projects, people, or aliases. If a section has nothing, "
    "use an empty list or empty string.\n\n"
    "JSON schema (all keys required):\n"
    "{\n"
    '  "role_context": "<the role and org context, in the user\'s own words, 1-3 sentences>",\n'
    '  "projects": [{"name": "<real name>", "aliases": ["<shorthand/codename>", ...], "status": "active", "note": "<one-line description or empty>"}],\n'
    '  "people": [{"name": "<full name as it appears in transcripts>", "aliases": ["<nickname>", ...]}],\n'
    '  "priorities": ["<one priority per entry, including what done looks like if stated>"],\n'
    '  "vocabulary": [{"term": "<term>", "meaning": "<what it means>"}]\n'
    "}\n"
)

CHECKIN_PARSE_SYSTEM = (
    "You turn status-check-in answers into structured JSON. Output ONLY a single "
    "JSON object -- no prose, no markdown fences. Use ONLY names that appear in "
    "the questions or the user's answers; never invent any. Statuses must be one "
    "of: active, paused, done. Verdicts must be one of: ratify, reject. Omit "
    "nothing the user decided; include nothing they did not.\n\n"
    "JSON schema (all keys required, [] or \"\" when empty):\n"
    "{\n"
    '  "project_updates": [{"name": "<existing project name>", "status": "active|paused|done"}],\n'
    '  "proposal_verdicts": [{"name": "<proposed name>", "type": "project|person", "verdict": "ratify|reject", "aliases": ["<alias>", ...]}],\n'
    '  "new_projects": [{"name": "<name>", "aliases": ["<alias>", ...]}],\n'
    '  "new_people": [{"name": "<name>", "aliases": ["<alias>", ...]}],\n'
    '  "notes": "<anything else worth keeping, in the user\'s words, or empty>"\n'
    "}\n"
)

REVISE_SYSTEM = (
    "You update a JSON object according to the user's requested changes. Output "
    "ONLY the updated JSON object with exactly the same schema and keys -- no "
    "prose, no markdown fences. Apply only the changes the user asked for; leave "
    "everything else untouched."
)


def _strs(v):
    return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []


def _items(v, keys, defaults=None):
    out = []
    defaults = defaults or {}
    if not isinstance(v, list):
        return out
    for x in v:
        if isinstance(x, dict):
            d = {}
            for k in keys:
                val = x.get(k, defaults.get(k, ""))
                d[k] = _strs(val) if isinstance(val, list) else str(val or "").strip()
            if d.get("name") or d.get("term"):
                out.append(d)
        elif isinstance(x, str) and x.strip():
            d = {k: defaults.get(k, "") for k in keys}
            d[keys[0]] = x.strip()
            out.append(d)
    return out


def _coerce_onboarding(obj: dict) -> dict:
    return {
        "role_context": str(obj.get("role_context") or "").strip(),
        "projects": _items(obj.get("projects"), ["name", "aliases", "status", "note"],
                           {"aliases": [], "status": "active"}),
        "people": _items(obj.get("people"), ["name", "aliases"], {"aliases": []}),
        "priorities": _strs(obj.get("priorities")),
        "vocabulary": _items(obj.get("vocabulary"), ["term", "meaning"]),
    }


def _coerce_checkin(obj: dict) -> dict:
    out = {
        "project_updates": _items(obj.get("project_updates"), ["name", "status"],
                                  {"status": "active"}),
        "proposal_verdicts": _items(obj.get("proposal_verdicts"),
                                    ["name", "type", "verdict", "aliases"],
                                    {"aliases": [], "verdict": "ratify", "type": "project"}),
        "new_projects": _items(obj.get("new_projects"), ["name", "aliases"], {"aliases": []}),
        "new_people": _items(obj.get("new_people"), ["name", "aliases"], {"aliases": []}),
        "notes": str(obj.get("notes") or "").strip(),
    }
    for u in out["project_updates"]:
        if u["status"] not in ("active", "paused", "done"):
            u["status"] = "active"
    for v in out["proposal_verdicts"]:
        if v["verdict"] not in ("ratify", "reject"):
            v["verdict"] = "ratify"
        if v["type"] not in ("project", "person"):
            v["type"] = "project"
    return out


def _qa_transcript(flow: str, pairs, agenda=None) -> str:
    """The Q/A record handed to the parsing model -- questions included so the
    model can resolve 'the first one' / 'both of those' style answers."""
    lines = []
    for marker, answer in pairs:
        step = marker.get("s")
        if step in ("confirm", "done", "cancelled"):
            continue
        if flow == "ob":
            q = next((q for k, q, _f, _t in ONBOARDING_STEPS if k == step), step)
            if marker.get("n"):
                q = next((f for k, _q, f, _t in ONBOARDING_STEPS if k == step), q) or q
        else:
            q = _checkin_question(step, agenda or {})
        lines.append(f"Q ({step}): {q}\nA: {answer}\n")
    return "\n".join(lines)


def parse_onboarding(pairs) -> dict | None:
    parsed = _parse_with_retry(ONBOARD_PARSE_SYSTEM,
                               "Interview transcript:\n\n" + _qa_transcript("ob", pairs))
    return _coerce_onboarding(parsed) if parsed is not None else None


def parse_checkin(pairs, agenda) -> dict | None:
    parsed = _parse_with_retry(CHECKIN_PARSE_SYSTEM,
                               "Check-in transcript:\n\n" + _qa_transcript("ci", pairs, agenda))
    return _coerce_checkin(parsed) if parsed is not None else None


def revise(flow: str, data: dict, instruction: str) -> dict | None:
    parsed = _parse_with_retry(
        REVISE_SYSTEM,
        "Current JSON:\n" + json.dumps(data, ensure_ascii=False, indent=1) +
        "\n\nUser's requested changes:\n" + instruction)
    if parsed is None:
        return None
    return _coerce_onboarding(parsed) if flow == "ob" else _coerce_checkin(parsed)


# ---- playback rendering -------------------------------------------------------

CONFIRM_FOOTER = ("\nIf that's right, say **yes** and I'll write it into your "
                  "vault. Or tell me what to change. (/cancel discards everything.)")


def _fmt_aliases(aliases) -> str:
    return f" (aka {', '.join(aliases)})" if aliases else ""


def playback_onboarding(data: dict) -> str:
    lines = ["Here's what I've got -- the playback:\n"]
    if data["role_context"]:
        lines.append(f"**Role & context:** {data['role_context']}\n")
    if data["projects"]:
        lines.append("**Projects:**")
        for p in data["projects"]:
            note = f" -- {p['note']}" if p.get("note") else ""
            lines.append(f"- {p['name']}{_fmt_aliases(p.get('aliases'))}"
                         f" [{p.get('status', 'active')}]{note}")
        lines.append("")
    if data["people"]:
        lines.append("**People:**")
        lines += [f"- {p['name']}{_fmt_aliases(p.get('aliases'))}" for p in data["people"]]
        lines.append("")
    if data["priorities"]:
        lines.append("**Priorities:**")
        lines += [f"- {p}" for p in data["priorities"]]
        lines.append("")
    if data["vocabulary"]:
        lines.append("**Vocabulary:**")
        lines += [f"- {v['term']} -- {v['meaning']}" for v in data["vocabulary"]]
        lines.append("")
    lines.append("Confirming writes Profile.md plus one page per project and person.")
    lines.append(CONFIRM_FOOTER)
    return "\n".join(lines)


def playback_checkin(data: dict) -> str:
    lines = ["Here's what I've got -- the playback:\n"]
    if data["project_updates"]:
        lines.append("**Status updates:**")
        lines += [f"- {u['name']} -> {u['status']}" for u in data["project_updates"]]
        lines.append("")
    if data["proposal_verdicts"]:
        lines.append("**Proposals:**")
        for v in data["proposal_verdicts"]:
            extra = _fmt_aliases(v.get("aliases"))
            lines.append(f"- {v['name']} ({v['type']}) -> {v['verdict']}{extra}")
        lines.append("")
    if data["new_projects"]:
        lines.append("**New projects:**")
        lines += [f"- {p['name']}{_fmt_aliases(p.get('aliases'))}" for p in data["new_projects"]]
        lines.append("")
    if data["new_people"]:
        lines.append("**New people:**")
        lines += [f"- {p['name']}{_fmt_aliases(p.get('aliases'))}" for p in data["new_people"]]
        lines.append("")
    if data.get("notes"):
        lines.append(f"**Also noted:** {data['notes']}\n")
    if not any((data["project_updates"], data["proposal_verdicts"],
                data["new_projects"], data["new_people"])):
        lines.append("No changes -- everything stands as it is.")
    lines.append(CONFIRM_FOOTER)
    return "\n".join(lines)


# ---- writes (only ever reached from an explicit confirmation) ------------------

def _front_matter_set(page: Path, key: str, value: str) -> bool:
    """Update one front-matter key in place. Only the front-matter line changes;
    the body -- user-owned content -- is never touched."""
    if not page.exists():
        return False
    text = page.read_text(encoding="utf-8")
    new, n = re.subn(rf"^({re.escape(key)}:)[^\n]*$", rf"\1 {value}", text,
                     count=1, flags=re.MULTILINE)
    if n == 0:
        return False
    page.write_text(new, encoding="utf-8")
    log.info("interview write: %s front matter %s -> %s", page.name, key, value)
    return True


def _alias_yaml(aliases: list) -> str:
    """One renderer, in registry.py, paired with the parser that reads it back.
    This was a second implementation of the same thing, and the two drifted:
    registry's quoted nothing while this one quoted everything, and neither
    round-tripped through a parser that split on every comma."""
    return registry._fm_aliases(aliases)


def _merge_aliases(conn, entity_id: str, new_aliases: list, vault_dir) -> None:
    row = conn.execute("SELECT name, aliases, note_path FROM entities WHERE entity_id=?",
                       (entity_id,)).fetchone()
    if not row:
        return
    name, aliases_json, note_path = row
    aliases = json.loads(aliases_json or "[]")
    lowered = {a.lower() for a in aliases} | {name.lower()}
    added = [a for a in new_aliases if a and a.lower() not in lowered]
    if not added:
        return
    aliases += added
    conn.execute("UPDATE entities SET aliases=? WHERE entity_id=?",
                 (json.dumps(aliases), entity_id))
    conn.commit()
    log.info("interview write: entity %r gains alias(es) %s", name, added)
    if note_path:
        _front_matter_set(Path(note_path), "aliases", _alias_yaml(aliases))


def _ratify_new(conn, name: str, etype: str, aliases: list, vault_dir) -> str | None:
    """Propose-then-ratify a brand new entity out of a confirmed interview."""
    existing = registry.match(conn, name, etype)  # canonical NAME, not id
    if existing:
        row = conn.execute(
            "SELECT entity_id FROM entities "
            "WHERE type=? AND status='ratified' AND name=?",
            (etype, existing)).fetchone()
        if row:
            _merge_aliases(conn, row[0], aliases, vault_dir)
        log.info("interview write: %s %r already ratified; merged aliases only", etype, name)
        return None
    # origin='interview' from the start, not flipped afterwards: this proposal
    # is ratified in the same breath and never reaches Inbox/Governance.md, so
    # the governance event log must not count it as queue burden.
    registry.propose(conn, name, etype, None, origin="interview")
    row = conn.execute(
        "SELECT entity_id FROM entities WHERE type=? AND lower(name)=? AND status='proposed'",
        (etype, name.strip().lower())).fetchone()
    if not row:
        log.warning("interview write: propose(%r, %s) left no proposed row; skipping", name, etype)
        return None
    entity_id = row[0]
    if aliases:
        conn.execute("UPDATE entities SET aliases=? WHERE entity_id=?",
                     (json.dumps(aliases), entity_id))
    page = registry.ratify(conn, entity_id, vault_dir)
    conn.execute("UPDATE entities SET origin='interview' WHERE entity_id=?", (entity_id,))
    conn.commit()
    log.info("interview write: ratified %s %r (origin=interview) -> %s", etype, name, page)
    return page


def write_profile(vault_dir, data: dict) -> str:
    """Profile.md at the vault root: the user's own words, played back and
    confirmed -- personal content by adoption."""
    page = Path(vault_dir) / "Profile.md"
    existed = page.exists()
    if existed:
        # Personal content is precious: never overwrite the previous profile
        # without keeping it. The backup is a plain vault file the user can
        # diff, merge from, or delete.
        backup = Path(vault_dir) / "Profile (previous).md"
        backup.write_text(page.read_text(encoding="utf-8"), encoding="utf-8")
        log.info("interview write: backed up existing Profile.md -> %s", backup.name)
    lines = ["---", "cairn-type: profile", "---", ""]
    if data.get("role_context"):
        lines += ["## Role & context", "", data["role_context"], ""]
    if data.get("priorities"):
        lines += ["## Priorities", ""] + [f"- {p}" for p in data["priorities"]] + [""]
    if data.get("vocabulary"):
        lines += ["## Vocabulary", ""]
        lines += [f"- **{v['term']}** -- {v['meaning']}" for v in data["vocabulary"]]
        lines.append("")
    Path(vault_dir).mkdir(parents=True, exist_ok=True)
    page.write_text("\n".join(lines), encoding="utf-8")
    log.info("interview write: %s Profile.md at vault root",
             "REPLACED (re-ratified by confirmation)" if existed else "wrote")
    return str(page)


def commit_onboarding(conn, data: dict, vault_dir) -> list[str]:
    """Everything the confirmed onboarding playback ratifies. Returns paths written."""
    ensure_entity_columns(conn)
    written = [write_profile(vault_dir, data)]
    for p in data.get("projects", []):
        path = _ratify_new(conn, p["name"], "project", p.get("aliases", []), vault_dir)
        if path:
            written.append(path)
            if p.get("status") and p["status"] != "active":
                _front_matter_set(Path(path), "status", p["status"])
    for p in data.get("people", []):
        path = _ratify_new(conn, p["name"], "person", p.get("aliases", []), vault_dir)
        if path:
            written.append(path)
    log.info("interview[ob]: confirmed -- %d file(s) written", len(written))
    return written


def commit_checkin(conn, data: dict, vault_dir) -> list[str]:
    """Everything the confirmed check-in playback ratifies. Returns paths touched."""
    ensure_entity_columns(conn)
    touched = []
    for u in data.get("project_updates", []):
        canon = registry.match(conn, u["name"], "project")  # canonical NAME, not id
        if not canon:
            log.warning("interview[ci]: status update for unknown project %r skipped", u["name"])
            continue
        row = conn.execute(
            "SELECT note_path FROM entities "
            "WHERE type='project' AND status='ratified' AND name=?",
            (canon,)).fetchone()
        if row and row[0] and _front_matter_set(Path(row[0]), "status", u["status"]):
            touched.append(row[0])
        else:
            log.warning("interview[ci]: no page on disk for %r; status not persisted", u["name"])
    for v in data.get("proposal_verdicts", []):
        row = conn.execute(
            "SELECT entity_id FROM entities WHERE status='proposed' AND lower(name)=?",
            (v["name"].strip().lower(),)).fetchone()
        if not row:
            log.warning("interview[ci]: verdict for unknown proposal %r skipped", v["name"])
            continue
        eid = row[0]
        if v["verdict"] == "ratify":
            if v.get("aliases"):
                _merge_aliases(conn, eid, v["aliases"], vault_dir)
            page = registry.ratify(conn, eid, vault_dir)
            conn.execute("UPDATE entities SET origin='interview' WHERE entity_id=?", (eid,))
            conn.commit()
            touched.append(page)
            log.info("interview[ci]: ratified proposal %r -> %s", v["name"], page)
        else:
            registry.reject(conn, eid)
            log.info("interview[ci]: rejected proposal %r", v["name"])
    for p in data.get("new_projects", []):
        page = _ratify_new(conn, p["name"], "project", p.get("aliases", []), vault_dir)
        if page:
            touched.append(page)
    for p in data.get("new_people", []):
        page = _ratify_new(conn, p["name"], "person", p.get("aliases", []), vault_dir)
        if page:
            touched.append(page)
    registry.write_queue_note(conn, vault_dir)
    log.info("interview[ci]: confirmed -- %d page(s) touched", len(touched))
    return touched


# ---- the request handler --------------------------------------------------------

PARSE_FAILURE_TEXT = (
    "I had trouble turning that into structure (the local model returned "
    "something I couldn't parse, twice). Nothing has been written. Could you "
    "restate your last answer a little more plainly?")


def _mk(flow, step, n=0, extra=None) -> str:
    obj = {"f": flow, "s": step, "n": n}
    if extra:
        obj.update(extra)
    return _encode_marker(obj)


def handle(messages):
    """
    Generator of text pieces for one interview turn. The single entry point
    ask.py streams from, for both protocol faces.
    """
    conn = dbmod.connect()
    try:
        dbmod.init_db(conn)
        yield from _handle(conn, messages)
    finally:
        conn.close()


def _handle(conn, messages):
    st = reconstruct(messages)
    if st is None:   # defensive; ask.py checks is_interview() first
        yield "No interview is in progress. Type /interview or /checkin to start one."
        return
    flow, latest, marker = st["flow"], st["latest"], st["last_marker"]
    vault_dir = config.VAULT_DIR
    fname = "onboarding" if flow == "ob" else "check-in"

    # -- explicit cancel, any point in the flow --
    if latest.strip().lower() == "/cancel":
        log.info("interview[%s]: cancelled by user (nothing written)", flow)
        yield ("Cancelled -- nothing was written. Type /interview or /checkin "
               "whenever you want to pick it up again." + _mk(flow, "cancelled"))
        return

    # -- fresh trigger: open the flow --
    if marker is None:
        if flow == "ob":
            log.info("interview[ob]: started")
            key, q, _f, _t = ONBOARDING_STEPS[0]
            yield ONBOARDING_INTRO + q + _mk("ob", key)
        else:
            agenda = build_agenda(conn)
            steps = _checkin_steps(agenda)
            log.info("interview[ci]: started, steps=%s", steps)
            yield (_checkin_intro(agenda) + _checkin_question(steps[0], agenda)
                   + _mk("ci", steps[0], extra={"a": agenda}))
        return

    agenda = marker.get("a") or {}

    # -- confirm step: the user's reply IS the ratification decision --
    if marker.get("s") == "confirm":
        data = marker.get("d") or {}
        if _is_affirmative(latest):
            log.info("interview[%s]: playback CONFIRMED -- writing", flow)
            written = (commit_onboarding(conn, data, vault_dir) if flow == "ob"
                       else commit_checkin(conn, data, vault_dir))
            names = "\n".join(f"- {Path(w).name}" for w in written) or "- (no file changes needed)"
            yield (f"Done -- ratified and written:\n{names}\n\n"
                   "Edit any of those pages directly whenever you like; the vault "
                   "is the source of truth." + _mk(flow, "done"))
        else:
            log.info("interview[%s]: playback revision requested", flow)
            revised = revise(flow, data, latest)
            if revised is None:
                yield (PARSE_FAILURE_TEXT +
                       _mk(flow, "confirm", extra={"d": data, "a": agenda} if flow == "ci"
                           else {"d": data}))
                return
            pb = playback_onboarding(revised) if flow == "ob" else playback_checkin(revised)
            extra = {"d": revised, "a": agenda} if flow == "ci" else {"d": revised}
            yield "Updated. " + pb + _mk(flow, "confirm", extra=extra)
        return

    # -- a scripted question was just answered --
    step, followed_up = marker.get("s"), marker.get("n", 0)
    if flow == "ob":
        keys = [k for k, *_ in ONBOARDING_STEPS]
        if step not in keys:
            step = keys[0]
        idx = keys.index(step)
        _k, _q, followup, thin = ONBOARDING_STEPS[idx]
        if (followup and not followed_up and not _is_skip(latest)
                and len(latest.strip()) < thin):
            log.info("interview[ob]: step %s answer thin (%d chars) -> follow-up",
                     step, len(latest.strip()))
            yield followup + _mk("ob", step, n=1)
            return
        if idx + 1 < len(keys):
            nkey, nq, _f, _t = ONBOARDING_STEPS[idx + 1]
            log.info("interview[ob]: step %s -> %s", step, nkey)
            yield _ACKS.get(step, "") + nq + _mk("ob", nkey)
            return
        log.info("interview[ob]: all steps answered -> parsing answers")
        data = parse_onboarding(st["pairs"])
        if data is None:
            yield PARSE_FAILURE_TEXT + _mk("ob", step, n=1)
            return
        log.info("interview[ob]: parsed -- %d project(s), %d person(s), "
                 "%d priorit(ies), %d vocab term(s)",
                 len(data["projects"]), len(data["people"]),
                 len(data["priorities"]), len(data["vocabulary"]))
        yield (_ACKS.get(step, "") + playback_onboarding(data)
               + _mk("ob", "confirm", extra={"d": data}))
        return

    # check-in steps
    steps = _checkin_steps(agenda)
    if step not in steps:
        step = steps[0]
    idx = steps.index(step)
    if idx + 1 < len(steps):
        log.info("interview[ci]: step %s -> %s", step, steps[idx + 1])
        yield ("Noted. " + _checkin_question(steps[idx + 1], agenda)
               + _mk("ci", steps[idx + 1], extra={"a": agenda}))
        return
    log.info("interview[ci]: all steps answered -> parsing answers")
    data = parse_checkin(st["pairs"], agenda)
    if data is None:
        yield PARSE_FAILURE_TEXT + _mk("ci", step, n=1, extra={"a": agenda})
        return
    log.info("interview[ci]: parsed -- %d update(s), %d verdict(s), %d new project(s), "
             "%d new person(s)", len(data["project_updates"]), len(data["proposal_verdicts"]),
             len(data["new_projects"]), len(data["new_people"]))
    yield playback_checkin(data) + _mk("ci", "confirm", extra={"d": data, "a": agenda})

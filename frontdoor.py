"""
Cairn front door: the deterministic lane that sits in front of retrieval.

Why this exists. A greeting used to cost 96 seconds: Cairn embedded it, retrieved
five statutes that had nothing to do with it, handed 10,000 characters of evidence
to the generation model, and the model wrote two paragraphs explaining why health
data statutes do not address salutations before producing the refusal string. The
tool was being careful and looked slow and pedantic doing it.

Three lanes, all decided here, none of them calling a model:

  chatter   Not a question. Greetings, thanks, single words, empty input.
            Answered from authored template text plus an instrument-derived
            snapshot of what the corpus holds.
  meta      A question about Cairn itself, not about the saved material.
            Answered from SQL: counts, dates, document names. Instrument output,
            not the model's self-description.
  ask       Everything else. Falls through to the existing retrieval path,
            unchanged.

Two rules this module exists to hold:

  1. Warmth is template text, authored here and checked into the repo. Answers are
     evidence. Nothing on the chatter or meta lane is generated, so nothing on
     those lanes can make an unreceipted claim about the corpus.
  2. Every front-door reply still carries a receipt, and that receipt says plainly
     that retrieval was not run. Rule one (no receipt, no answer) is satisfied by
     an honest "no evidence was consulted", never by omitting the line.

Classification is deliberately conservative. A false chatter match sends a real
question into a canned reply, which is the expensive error, so matching is done
against whole normalized strings rather than by keyword or prefix. "hello" is
chatter; "hello, what does RCW 43.70.050 require" is a question.
"""

import re

# ---- the no-hope floor ------------------------------------------------------
# Distances at or above this skip the generation model entirely: retrieval already
# knows the corpus has nothing, and spending 90 seconds to have the model discover
# that is the disappointment this slice removes.
#
# This is NOT the Weak threshold and must not be merged with it. Weak begins at
# 0.90 and means "loosely related, consider rephrasing", which is still worth an
# answer. This floor means "nothing here at all". The value is PROVISIONAL and set
# from one observed data point: a greeting scored 1.055 against the RCW corpus on
# 2026-08-10, and the closest known good answer scored 0.843. 1.00 sits between
# them with margin on both sides. Every firing is logged with its distance so a
# week of daily use recalibrates this from data instead of from this comment.
NO_HOPE_DISTANCE = 1.00


# ---- normalization ----------------------------------------------------------

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")

# Stripped from the front so "hey cairn, what do you have" reaches the same
# matcher as "what do you have". Kept short on purpose.
_LEAD = ("cairn", "ok", "okay", "so", "hey", "hi", "hello", "please")

# Longest input still eligible for a lane. Above this it is a real question by
# construction, whatever it looks like.
MAX_LANE_CHARS = 60


def normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace. No token removal."""
    s = _PUNCT.sub(" ", (text or "").lower())
    return _WS.sub(" ", s).strip()


def strip_lead(s: str) -> str:
    """Drop leading filler tokens, so 'hey cairn, what do you have' matches."""
    changed = True
    while changed and s:
        changed = False
        for lead in _LEAD:
            if s == lead:
                return s
            if s.startswith(lead + " "):
                s = s[len(lead) + 1:]
                changed = True
    return s


def forms(text: str):
    """
    Both candidate forms, in order. The unstripped form is tried first so multi-word
    greetings survive: "hi there" is a phrase in its own right, and stripping the
    leading "hi" first would leave a bare "there" that matches nothing.
    """
    s = normalize(text)
    stripped = strip_lead(s)
    return (s,) if stripped == s else (s, stripped)


# ---- lane vocabularies ------------------------------------------------------
# Whole-string matches only. Adding a phrase here is a deliberate act; a phrase
# that could plausibly begin a real question does not belong.

CHATTER = {
    # "cairn" appears because normalize() strips leading greeting tokens, so
    # "hey cairn" and "hello cairn" both arrive here as the bare name.
    "", "cairn", "hi", "hello", "hey", "yo", "hiya", "howdy", "greetings",
    "hi there", "hello there", "hey there", "good morning", "good afternoon",
    "good evening", "morning", "afternoon", "evening",
    "test", "testing", "test test", "ping", "are you there", "you there",
    "anyone there", "is this working", "does this work", "are you working",
    "thanks", "thank you", "thanks a lot", "thank you very much", "ty",
    "cheers", "appreciated", "much appreciated", "nice", "cool", "great",
    "awesome", "perfect", "excellent", "got it", "understood", "makes sense",
    "ok", "okay", "k", "sure", "yes", "no", "yep", "nope",
    "bye", "goodbye", "good bye", "see you", "see ya", "later", "good night",
    "night", "done", "never mind", "nevermind",
}

# What Cairn holds. Answered from the database.
META_HOLDINGS = {
    "what do you have", "what do you have saved", "what have you got",
    "what do you know", "what do you know about", "what do you hold",
    "what is in there", "what s in there", "whats in there",
    "what is in cairn", "what s in cairn", "whats in cairn",
    "what is saved", "what s saved", "whats saved",
    "what have i saved", "what did i save",
    "what documents do you have", "what documents are saved",
    "what documents do you hold", "what files do you have",
    "how many documents do you have", "how many documents",
    "what is indexed", "what s indexed", "whats indexed",
    "show me what you have", "list documents", "list what you have",
    "coverage", "status",
}

# What Cairn is and how to use it. Answered from authored text.
META_CAPABILITY = {
    "what can you do", "what can i ask", "what can i ask you",
    "what can you help with", "what can you help me with",
    "how do i use this", "how do i use you", "how does this work",
    "what are you", "who are you", "what is cairn", "what is this",
    "what s this", "whats this",
    "help", "help me", "commands", "manual",
    "how do i add a document", "how do i add documents", "how do i add",
    "how do i save a document", "how do i save documents",
    "how do i put something in", "how do i index",
}

ASK = "ask"
CHAT = "chatter"
HOLDINGS = "holdings"
CAPABILITY = "capability"


def classify(question: str) -> str:
    """
    Which lane. Returns one of: "chatter", "holdings", "capability", "ask".

    Deterministic and free: no embedding, no model call, no database read. The
    default is always "ask", so anything unrecognized takes the existing path.
    """
    raw = (question or "").strip()
    if len(raw) > MAX_LANE_CHARS:
        return ASK
    for s in forms(raw):
        if s in CHATTER:
            return CHAT
        if s in META_HOLDINGS:
            return HOLDINGS
        if s in META_CAPABILITY:
            return CAPABILITY
    return ASK


# ---- the corpus snapshot (instrument output, not testimony) -----------------

def corpus_snapshot(conn) -> dict:
    """
    What Cairn actually holds, read from the database at answer time.

    Every field here is a measured quantity. Nothing is remembered, cached, or
    described by a model. Returns zeros rather than raising on a fresh or
    partially built database, so the front door never fails louder than the
    thing it is describing.
    """
    snap = {"documents": 0, "chunks": 0, "embedded": 0, "newest": None,
            "newest_at": None, "oldest_at": None, "samples": [], "statuses": {}}
    try:
        snap["documents"] = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        row = conn.execute("SELECT COUNT(*), COALESCE(SUM(embedded),0) FROM chunks").fetchone()
        snap["chunks"], snap["embedded"] = row[0], row[1]
        row = conn.execute(
            "SELECT source_name, ingested_at FROM documents "
            "WHERE ingested_at IS NOT NULL ORDER BY ingested_at DESC LIMIT 1").fetchone()
        if row:
            snap["newest"], snap["newest_at"] = row[0], (row[1] or "")[:10]
        row = conn.execute(
            "SELECT ingested_at FROM documents "
            "WHERE ingested_at IS NOT NULL ORDER BY ingested_at ASC LIMIT 1").fetchone()
        if row:
            snap["oldest_at"] = (row[0] or "")[:10]
        snap["samples"] = [r[0] for r in conn.execute(
            "SELECT DISTINCT source_name FROM documents "
            "ORDER BY ingested_at DESC LIMIT 4").fetchall()]
        for name, count in conn.execute(
                "SELECT COALESCE(status,'draft'), COUNT(*) FROM documents "
                "GROUP BY COALESCE(status,'draft')").fetchall():
            snap["statuses"][name] = count
    except Exception:
        pass
    return snap


def holdings_line(snap: dict) -> str:
    """One sentence of measured fact about the corpus."""
    if not snap["documents"]:
        return "Right now Cairn holds nothing. Drop a file into sources and run the index step."
    docs = snap["documents"]
    chunks = snap["chunks"]
    line = (f"Cairn holds {docs} document{'s' if docs != 1 else ''} "
            f"({chunks} passage{'s' if chunks != 1 else ''} indexed)")
    if snap["embedded"] and snap["embedded"] != chunks:
        line += f", {snap['embedded']} of them searchable"
    if snap["newest_at"]:
        line += f". Most recent addition {snap['newest_at']}"
        if snap["newest"]:
            line += f": {snap['newest']}"
    return line + "."


NO_RETRIEVAL_RECEIPT = (
    "\n\n---\n"
    "Retrieval: not run. This is Cairn describing itself, not an answer from your "
    "saved material.\n\nSources: none consulted."
)


def _samples_block(snap: dict) -> str:
    if not snap["samples"]:
        return ""
    lines = ["", "Some of what is in there:"]
    lines += [f"- {name}" for name in snap["samples"]]
    return "\n".join(lines)


def chatter_reply(snap: dict) -> str:
    """
    Not a question. Say what Cairn is for, show what it holds, and steer toward a
    question that will land. Authored text plus measured fact, nothing generated.
    """
    parts = [
        "Hello. Cairn answers questions from the material you have saved, and cites "
        "a source for every claim it makes.",
        "",
        holdings_line(snap),
    ]
    block = _samples_block(snap)
    if block:
        parts.append(block)
    parts += [
        "",
        "Questions land best when they name something you expect to appear in the "
        "text: a topic, a term, a document, or a date. Ask what a policy requires, "
        "what was decided, or what a statute says.",
        NO_RETRIEVAL_RECEIPT,
    ]
    return "\n".join(parts)


def holdings_reply(snap: dict) -> str:
    """What Cairn holds, entirely from the database."""
    parts = [holdings_line(snap)]
    if snap["oldest_at"] and snap["newest_at"] and snap["oldest_at"] != snap["newest_at"]:
        parts.append(f"Saved material spans {snap['oldest_at']} to {snap['newest_at']}.")
    if snap["statuses"]:
        bits = ", ".join(f"{n} {s}" for s, n in sorted(snap["statuses"].items()))
        parts.append(f"Records status: {bits}.")
    block = _samples_block(snap)
    if block:
        parts.append(block)
    parts += [
        "",
        "Ask about any of it and Cairn will answer from the text with citations.",
        NO_RETRIEVAL_RECEIPT,
    ]
    return "\n".join(parts)


def capability_reply(snap: dict) -> str:
    """What Cairn is and how to use it. Authored text, one measured line."""
    parts = [
        "Cairn answers questions from the documents you have saved on this machine. "
        "It reads, finds, and cites. It does not act on other systems, and nothing "
        "leaves the machine.",
        "",
        holdings_line(snap),
        "",
        "Three things you can do:",
        "- Ask what a saved document says, requires, or decided. Every claim comes "
        "back with the source and the passage.",
        "- Ask a question the material does not cover. Cairn says so plainly rather "
        "than guessing.",
        "- Save more material by dropping files into the sources folder and running "
        "the ingest and index steps.",
        "",
        "If an answer looks thin, the retrieval line at the bottom tells you whether "
        "Cairn found a close match or was reaching. Naming a specific term or "
        "document usually fixes a weak result.",
        NO_RETRIEVAL_RECEIPT,
    ]
    return "\n".join(parts)


def front_door_reply(conn, lane: str) -> str:
    """The whole reply for a non-ask lane, receipt included."""
    snap = corpus_snapshot(conn)
    if lane == CHAT:
        return chatter_reply(snap)
    if lane == HOLDINGS:
        return holdings_reply(snap)
    if lane == CAPABILITY:
        return capability_reply(snap)
    raise ValueError(f"front_door_reply called for lane {lane!r}")


# ---- the no-hope reply ------------------------------------------------------

def nearest_labels(rows, limit=3):
    """
    Up to `limit` distinct human labels from retrieved rows, nearest first.

    Row shape is the retrieve() tuple: index 1 is heading, index 3 is source_name.
    Deduplicated on the rendered label, because the same document often supplies
    several neighbouring chunks and listing it three times steers nobody.
    """
    labels, seen = [], set()
    for r in rows:
        heading, source_name = r[1], r[3]
        label = f"{source_name} > {heading}" if heading else source_name
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)
        if len(labels) >= limit:
            break
    return labels


def no_hope_reply(refusal_text: str, rows) -> str:
    """
    The refusal, plus the nearest material Cairn actually holds.

    The steering list is derived from the retrieval that just ran, so it is honest:
    these are the real nearest neighbours, not a guess at what the user meant. A
    dead end becomes a trail marker at no extra cost, because the rows are already
    in hand.
    """
    parts = [refusal_text]
    labels = nearest_labels(rows)
    if labels:
        parts += ["", "Closest material Cairn holds to that:"]
        parts += [f"- {label}" for label in labels]
        parts += ["", "If one of those is the right neighbourhood, naming a term or "
                      "section from it will usually land."]
    return "\n".join(parts)

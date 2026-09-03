"""
Cairn ask service: evidence-grounded question answering over the indexed corpus.

Flow: embed the question -> KNN search vec_chunks -> take the top matches ->
ask the generative model to answer STRICTLY from those chunks, citing sources ->
return the answer with citations. Serves a minimal UI on localhost.

Grounding contract: the model may use language ability to read and synthesize,
but every substantive fact must come from the retrieved evidence. It must not use
its own training memory of statute content, and must say so when the evidence does
not contain the answer.

Two faces, one engine:
  1. The built-in web UI at /, which streams answers, citations, and a strength label.
  2. A local-model protocol surface, so a third-party chat client can select "cairn"
     as its model and get grounded, cited answers underneath its own chrome. Both
     the OpenAI-compatible shape (/v1/models, /v1/chat/completions) and the
     Ollama-compatible shape (/api/tags, /api/chat) are served, because plugins
     differ in which one they speak.

What the protocol surface does NOT do, by construction: it does not honour a
client-supplied system prompt, sampling settings, or model choice. The chrome is
swappable; the contract is not. See the PROTOCOL section below.

Usage:
    ./.venv/bin/python ask.py                       start the service at http://127.0.0.1:8765
    ./.venv/bin/python ask.py --ask "your question" one-shot from the command line, no server

Requires the configured generation and embedding endpoints reachable (see
config.py / models.local.json for the machine-local model names, dialects, and
endpoints -- they need not be the same server):
    config.GEN_MODEL   (generation, config.GEN_DIALECT: "ollama" or "openai")
    config.EMBED_MODEL (retrieval, always Ollama dialect)
"""

import argparse
import json
import logging
import re
import struct
import time
import html
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
import db as dbmod
import frontdoor
import interview
import llm
import sqlite_vec

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-5s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cairn")


EMBED_URL = config.EMBED_URL
EMBED_MODEL = config.EMBED_MODEL
GEN_MODEL = config.GEN_MODEL
KEEP_ALIVE = "30m"           # embedding calls only: keep the Ollama embed model loaded
                              # between calls; cold loads are the hidden latency. Generation
                              # calls go through llm.py, which owns its own dialect-specific
                              # keep-alive handling.
TOP_K = 5
HOST, PORT = "127.0.0.1", 8765
BUILD = "cairn-frontdoor-1"  # bump when the page/JS changes; visible in the UI footer

# ---- local-model protocol identity -----------------------------------------
# The name a chat client sees in its model picker. Aliases are accepted because
# Ollama-flavoured clients tack on a ":latest" tag.
MODEL_ID = "cairn"
MODEL_ALIASES = {"cairn", "cairn:latest"}

# Origins permitted to call the protocol endpoints from a browser-like runtime.
# The service already binds to 127.0.0.1, so only local processes can reach it at
# all; this second gate stops a random web page open in a browser on the same
# machine from reading answers over CORS. Obsidian and other Electron clients send
# one of these. Matched as a prefix so ports do not need enumerating.
ALLOWED_ORIGINS = (
    "app://obsidian.md",
    "capacitor://localhost",
    "http://localhost",
    "http://127.0.0.1",
    "null",
)

# The exact refusal string, defined once so the prompt, the empty-evidence shortcut,
# and the self-test can never drift apart.
REFUSAL_TEXT = "Sorry, I was unable to find information pertaining to your question."

# ---- context budgeting (dynamic context sizing) ----------------------------
# We size the model's context window (num_ctx) per request from the actual
# payload rather than using a fixed global. The window must hold:
#   system prompt + evidence + question  (the PROMPT / prefill)
#   + room for the answer                (COMPLETION headroom / decode)
# Sizing per request keeps short queries fast (small window) and only grows the
# window when the evidence needs it, so evidence is never silently truncated.
CHARS_PER_TOKEN = 4          # standard English heuristic for token ESTIMATION
CTX_SAFETY_MARGIN = 1.20     # pad the estimate to absorb heuristic imprecision
COMPLETION_HEADROOM = 512    # output-token reserve; matches num_predict below
NUM_PREDICT = 512            # hard cap on generated tokens (prevents runaway)
CTX_FLOOR = 4096             # never smaller than Ollama's default
CTX_CEILING = 16384          # safety cap so a pathological payload can't crawl
CTX_STEPS = (4096, 8192, 16384)  # round up to a friendly window size

# Temperature 0 = greedy decoding: deterministic, reproducible, no creative drift.
# This is REQUIRED for an evidence-grounded system. Do NOT raise it: creativity is
# exactly what we do not want when the model must stick to the retrieved passages.
TEMPERATURE = 0

SYSTEM_PROMPT = (
    "You are Cairn, a retrieval assistant. Your job is to ANSWER the user's question "
    "using the numbered evidence passages, and to cite what you use, even when the "
    "evidence is partial or ambiguous.\n"
    "Every reply falls into exactly one of three cases. Decide which case applies, "
    "then follow it.\n"
    "CASE 1. The passages answer the question, even partly. Synthesize what they say. "
    "A partial answer is correct and expected: state what the passages establish, cite "
    "each claim with its number like [1] or [2], and briefly note anything the passages "
    "do not cover. If your answer feels imprecise, tell the user how they might rephrase "
    "or narrow their question for a better result.\n"
    "CASE 2. The passages are on the question's topic but do not contain the answer. "
    "Reply in AT MOST THREE SENTENCES: say that the saved material does not address the "
    "specific question, then say what the retrieved passages DO cover. Each thing you say "
    "a passage covers MUST carry that passage's number in square brackets, exactly as in "
    "case 1 — for example: \"The retrieved passages instead describe how such records are "
    "stored [1] and who may access them [2].\" A case 2 reply with no bracketed passage "
    "number is malformed. Do not speculate about what other material might say. Do not use "
    "the refusal sentence from case 3, and do not write a long explanation of the gap.\n"
    "CASE 3. NO passage relates to the question's subject at all. Your ENTIRE reply is "
    "this sentence, on its own, with no preamble and nothing after it: "
    "\"" + REFUSAL_TEXT + "\" Do NOT explain why you are declining, do NOT describe what "
    "the passages contain, and do NOT restate the question first.\n"
    "Rules that apply to all three cases:\n"
    "- Base every statement only on the passages. Do not add facts from your own knowledge "
    "of laws or regulations. If a passage conflicts with what you think you know, follow "
    "the passage. If the evidence is ambiguous or thin, say so.\n"
    "- Cite ONLY passage numbers that were actually given to you. If you were given five "
    "passages, the highest number you may ever write is [5]. Never invent a passage number "
    "and never cite a range that runs past the last passage.\n"
    "- Never narrate your reasoning and never restate the question. Begin with the answer "
    "itself. Keep the answer under 150 words unless the question genuinely needs more.\n"
    "Be concise and factual."
)


# Retrieval-strength labels derived from the top match distance (a measured quantity,
# not the model's self-assessment). Lower distance = closer semantic match. Thresholds
# are calibrated to observed behavior (strong queries ~0.75, marginal ~0.86+).
def retrieval_strength(top_distance):
    if top_distance is None:
        return ("None", "no matches")
    if top_distance <= 0.80:
        return ("Strong", "close match to the indexed text")
    if top_distance <= 0.90:
        return ("Moderate", "related, but not a tight match")
    return ("Weak", "loosely related; consider rephrasing")


# ---- citation integrity ----------------------------------------------------
# On 2026-08-10 a live answer cited passages [1] through [6] when five passages
# existed. An invented evidence index is a rule-one failure: the receipt pointed
# at something that was never there, and nothing in the system noticed.
#
# The check is mechanical and free. What it does NOT do is suppress the answer or
# retry: suppression hides a defect from the one person able to judge it, and a
# retry doubles a latency that is already the confirmed first disappointment.
# Instead the defect is labelled in the open, which is the receipts rule applied
# to Cairn's own output.

# A citation is one bracket holding 1-3 digit passage number(s); models also emit
# the grouped form "[1, 2]", which must parse the same as "[1] [2]" — both for
# crediting real citations and for catching phantoms hidden in a group ("[1, 6]").
CITATION_RE = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]")


def cited_indices(text: str):
    """Every bracketed passage number appearing in an answer, grouped or not."""
    return {int(n) for m in CITATION_RE.findall(text or "")
            for n in m.split(",")}


def phantom_citations(text: str, evidence_count: int):
    """
    Cited passage numbers that do not exist in the evidence.

    Anything above the count is invented. Zero is invalid because passages are
    numbered from one. Returned sorted so the log line and the note agree.
    """
    return sorted(n for n in cited_indices(text)
                  if n > evidence_count or n < 1)


def integrity_note(phantoms):
    """The visible label attached to an answer that cited evidence it never had."""
    if not phantoms:
        return ""
    which = ", ".join(f"[{n}]" for n in phantoms)
    return ("\n\nNote: this answer cited " + which + ", which do not exist in the "
            "evidence retrieved for it. Treat any claim resting on them as "
            "unsupported.")


def check_citations(text: str, evidence_count: int):
    """
    Scan an assembled answer and return the note to append, logging any violation.
    Empty string when the answer is clean, which is the overwhelming majority.
    """
    phantoms = phantom_citations(text, evidence_count)
    if phantoms:
        log.warning("citation integrity: answer cited %s with only %d passage(s) in evidence",
                    ", ".join(f"[{n}]" for n in phantoms), evidence_count)
    return integrity_note(phantoms)


def estimate_tokens(text: str) -> int:
    """Rough token estimate from character count (English heuristic)."""
    return int(len(text) / CHARS_PER_TOKEN)


def size_context(prompt_text: str) -> int:
    """
    Dynamic context sizing: choose num_ctx to fit the prompt plus completion
    headroom, padded by a safety margin, floored and ceilinged, rounded up to a
    friendly window step.
    """
    prompt_tokens = estimate_tokens(prompt_text) * CTX_SAFETY_MARGIN
    needed = int(prompt_tokens) + COMPLETION_HEADROOM
    for step in CTX_STEPS:
        if needed <= step:
            return max(step, CTX_FLOOR)
    return CTX_CEILING


# ---- retrieval -------------------------------------------------------------

def serialize(vec):
    return struct.pack(f"{len(vec)}f", *vec)


def embed_query(text: str):
    t0 = time.time()
    payload = json.dumps({"model": EMBED_MODEL, "input": [text], "keep_alive": KEEP_ALIVE}).encode("utf-8")
    req = urllib.request.Request(EMBED_URL, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        vec = json.loads(resp.read().decode("utf-8"))["embeddings"][0]
    log.info("embedded query in %.2fs (dim %d)", time.time() - t0, len(vec))
    return vec


def load_vec(conn):
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def vec_table_exists(conn) -> bool:
    """
    True once index.py has created vec_chunks. On a virgin DB (watcher/index
    hasn't run yet, or --reset just dropped it) the table is absent, and the
    service should still start and answer with a grounded refusal rather than
    crash with sqlite3.OperationalError.
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vec_chunks'"
    ).fetchone()
    return row is not None


def retrieve(conn, question, k=TOP_K):
    if not vec_table_exists(conn):
        log.warning("vec_chunks table does not exist yet -- index is empty, "
                    "the watcher will populate it. Retrieving no evidence.")
        return []
    qvec = embed_query(question)
    t0 = time.time()
    rows = conn.execute(
        """
        SELECT c.chunk_id, c.heading, c.text, d.source_name, d.source_path, v.distance,
               d.doc_id, d.source_url, d.vault_path
        FROM vec_chunks v
        JOIN chunks c    ON c.chunk_id = v.chunk_id
        JOIN documents d ON d.doc_id   = c.doc_id
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (serialize(qvec), k),
    ).fetchall()
    log.info("retrieved %d chunk(s) in %.2fs", len(rows), time.time() - t0)
    for i, r in enumerate(rows, 1):
        log.info("  [%d] dist=%.3f  %s", i, r[5], (r[1] or r[3])[:70])
    return rows


# ---- generation ------------------------------------------------------------

def build_evidence_block(rows):
    parts = []
    for i, r in enumerate(rows, 1):
        heading, text, source_name = r[1], r[2], r[3]
        label = heading or source_name
        parts.append(f"[{i}] (source: {source_name} | {label})\n{text}")
    return "\n\n".join(parts)


def synthesize_stream(question, rows):
    """
    Generator: yields the grounded answer token by token. On no evidence, yields
    the single refusal string. This is what the web handler streams to the browser.
    """
    if not rows:
        log.info("no evidence retrieved -> grounded refusal (model not called)")
        yield REFUSAL_TEXT
        return

    evidence = build_evidence_block(rows)
    user_msg = (
        f"Question: {question}\n\n"
        f"Evidence passages:\n\n{evidence}\n\n"
        "Answer using only the passages above, citing passage numbers."
    )
    full_prompt = SYSTEM_PROMPT + user_msg
    log.info("context: ~%d prompt tokens (estimate; num_ctx sizing is Ollama-only and "
             "handled server-side under the OpenAI dialect)", estimate_tokens(full_prompt))

    log.info("calling %s via %s (evidence %d chars), streaming ...",
             GEN_MODEL, config.GEN_DIALECT, len(evidence))
    t0 = time.time()
    n_tokens = 0
    try:
        for piece in llm.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            stream=True,
            temperature=TEMPERATURE,
            max_tokens=NUM_PREDICT,
        ):
            n_tokens += 1
            yield piece
    except llm.LLMError as e:
        log.error("generation chat call failed: %s", e)
        yield f"[service error: could not reach the generation model. {e}]"
        return
    dt = time.time() - t0
    rate = n_tokens / dt if dt > 0 else 0
    log.info("streamed ~%d chunks in %.1fs (%.1f/s)", n_tokens, dt, rate)


def synthesize(question, rows):
    """Non-streaming convenience: collect the stream into a single string (CLI path)."""
    return "".join(synthesize_stream(question, rows)).strip()


def obsidian_url(vault_path: str) -> str | None:
    """Build an obsidian:// link that opens the converted note in Obsidian."""
    import os
    from urllib.parse import quote
    if not vault_path:
        return None
    try:
        vault_root = os.path.dirname(str(config.VAULT_DIR))  # parent of the vault folder
        vault_name = os.path.basename(str(config.VAULT_DIR))
        rel = os.path.relpath(vault_path, str(config.VAULT_DIR)).replace(os.sep, "/")
        return f"obsidian://open?vault={quote(vault_name)}&file={quote(rel)}"
    except Exception:
        return None


def build_citations(rows):
    citations = []
    for i, r in enumerate(rows, 1):
        chunk_id, heading, _text, source_name, source_path, distance, doc_id, source_url, vault_path = r
        # Link precedence: canonical web URL, else the Obsidian note, else local-open endpoint.
        if source_url:
            link, link_kind = source_url, "source"
        elif vault_path:
            link, link_kind = obsidian_url(vault_path), "obsidian"
        else:
            link, link_kind = f"/open?doc={doc_id}", "open"
        citations.append({
            "n": i, "source_name": source_name, "heading": heading,
            "distance": round(distance, 3), "doc_id": doc_id,
            "link": link, "link_kind": link_kind,
        })
    return citations


def answer(conn, question, k=TOP_K):
    """Non-streaming: full answer + citations (used by the CLI --ask path)."""
    lane = frontdoor.classify(question)
    if lane != frontdoor.ASK:
        log.info("front door: lane=%s (no retrieval, no model call)", lane)
        return frontdoor.front_door_reply(conn, lane), []
    rows = retrieve(conn, question, k)
    top_dist = rows[0][5] if rows else None
    if top_dist is not None and top_dist >= frontdoor.NO_HOPE_DISTANCE:
        log.info("no-hope floor fired: top dist %.3f >= %.3f (model not called)",
                 top_dist, frontdoor.NO_HOPE_DISTANCE)
        return frontdoor.no_hope_reply(REFUSAL_TEXT, rows), build_citations(rows)
    text = synthesize(question, rows)
    text += check_citations(text, len(rows))
    return text, build_citations(rows)


# ---- open original document (guarded) --------------------------------------

def open_original(conn, doc_id: str):
    """
    Launch the original source document in its OS default app. Guarded: only a
    doc_id that exists in the index can be opened, so this endpoint can never be
    used to open an arbitrary path on disk. Returns (ok, message).
    """
    import os
    import subprocess
    import sys

    row = conn.execute(
        "SELECT source_path FROM documents WHERE doc_id=?", (doc_id,)
    ).fetchone()
    if not row:
        return False, "unknown document"
    path = row[0]
    if not os.path.exists(path):
        return False, "source file no longer at recorded path"
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: pylint os.startfile is Windows-only, which is the target
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True, "opened"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ---- PROTOCOL: cairn as a selectable local model ---------------------------
#
# A third-party chat client points at this service, picks "cairn" from its model
# list, and types a question. It believes it is talking to a language model. It is
# talking to retrieval, grounded synthesis, citations, and a strength label.
#
# Four properties are enforced here rather than trusted to the client:
#
#   1. The client's system prompt is DISCARDED, never merged. SYSTEM_PROMPT is the
#      grounding contract; if chrome could edit it, a plugin default (or text
#      inside a document the plugin echoes back) could tell Cairn to stop citing
#      or to answer from training memory. Structurally impossible: the only thing
#      that crosses into synthesis is the question string and the retrieved rows.
#   2. The client's sampling settings are DISCARDED. TEMPERATURE is 0 because
#      evidence-grounded answering requires it. A plugin defaulting to 0.7 must not
#      be able to make Cairn creative.
#   3. The client's model choice is IGNORED, and the reply is always labelled
#      "cairn". A misconfigured picker gets an answer with an honest label rather
#      than a dead UI.
#   4. Citations and the strength label RIDE INSIDE THE TEXT. The protocol carries
#      nothing but a string, so rule one (no receipt, no answer) survives contact
#      with plugin chrome only if the receipt is part of the payload.
#
# Multi-turn is deliberately not implemented yet: the question is the last user
# message and earlier turns are dropped, not silently concatenated. Conversation
# as context for understanding a question is a separate, tracked slice.


def extract_question(messages):
    """
    Pull the question out of a chat-protocol message list.

    Returns (question, dropped_turns, had_foreign_system). The last two are for
    logging: they make the discarding visible in the log rather than invisible.
    """
    msgs = messages or []
    had_foreign_system = any(m.get("role") == "system" for m in msgs)
    question, seen_user = "", False
    dropped = 0
    for m in reversed(msgs):
        if m.get("role") != "user":
            continue
        if not seen_user:
            question, seen_user = flatten_content(m.get("content")), True
        else:
            dropped += 1
    return question.strip(), dropped, had_foreign_system


def flatten_content(content):
    """Message content may be a plain string or a list of typed parts. Take the text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content
            if isinstance(part, dict) and part.get("type") in (None, "text")
        )
    return ""


def receipt_block(citations, label, note, top_distance):
    """
    The receipt, rendered as markdown for the text channel: what the retrieval was
    worth, and exactly which passages the answer stands on. No em-dashes.
    """
    dist = f" ({top_distance:.3f})" if top_distance is not None else ""
    lines = ["", "", "---", f"Retrieval: {label}{dist}. {note[:1].upper()}{note[1:]}."]
    if not citations:
        lines += ["", "Sources: none. Nothing in the saved material matched this question."]
        return "\n".join(lines)
    lines += ["", "Sources:"]
    for c in citations:
        heading = f" | {c['heading']}" if c["heading"] else ""
        lines.append(f"{c['n']}. {c['source_name']}{heading} (dist {c['distance']})")
        # The /open link is only meaningful inside Cairn's own UI, so it is omitted
        # here rather than handed to a client that cannot follow it.
        if c["link"] and c["link_kind"] != "open":
            lines.append(f"   {c['link']}")
    return "\n".join(lines)


def cairn_reply_stream(question, with_receipt=True):
    """
    The whole Cairn answer as a stream of text pieces: retrieve, synthesize from
    the evidence only, then append the receipt. This is the single path both
    protocol shapes call, so neither can drift from the other.
    """
    conn = dbmod.connect()
    try:
        # Front door first: greetings and questions about Cairn itself are answered
        # from templates and SQL, with no embedding and no model call. This lane
        # carries its own receipt, which states that retrieval was not run.
        lane = frontdoor.classify(question)
        if lane != frontdoor.ASK:
            log.info("front door: lane=%s (no retrieval, no model call)", lane)
            yield frontdoor.front_door_reply(conn, lane)
            return

        load_vec(conn)
        rows = retrieve(conn, question, TOP_K)
        citations = build_citations(rows)
        top_dist = rows[0][5] if rows else None
        label, note = retrieval_strength(top_dist)
        log.info("retrieval strength: %s (top dist %s)", label,
                 f"{top_dist:.3f}" if top_dist is not None else "n/a")

        # No-hope floor: retrieval already knows there is nothing here, so skip the
        # generation model rather than spending a minute and a half on it. The
        # nearest headings still travel, which turns a dead end into a trail marker.
        if top_dist is not None and top_dist >= frontdoor.NO_HOPE_DISTANCE:
            log.info("no-hope floor fired: top dist %.3f >= %.3f (model not called)",
                     top_dist, frontdoor.NO_HOPE_DISTANCE)
            yield frontdoor.no_hope_reply(REFUSAL_TEXT, rows)
        else:
            # Accumulate while streaming so the citation check can run on the whole
            # answer without delaying a single token of it.
            collected = []
            for piece in synthesize_stream(question, rows):
                collected.append(piece)
                yield piece
            note = check_citations("".join(collected), len(rows))
            if note:
                yield note
        if with_receipt:
            yield receipt_block(citations, label, note, top_dist)
    finally:
        conn.close()


def _now():
    return int(time.time())


def _iso_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _completion_id():
    import uuid
    return "chatcmpl-" + uuid.uuid4().hex[:24]


def log_protocol_request(shape, model_requested, question, dropped, foreign_system):
    """One line that makes every discard visible instead of silent."""
    if model_requested and model_requested not in MODEL_ALIASES:
        log.warning("%s: client asked for model %r; serving cairn (only model here)",
                    shape, model_requested)
    notes = []
    if foreign_system:
        notes.append("client system prompt discarded")
    if dropped:
        notes.append(f"{dropped} earlier turn(s) dropped (multi-turn not yet implemented)")
    log.info('%s ASK: "%s"%s', shape,
             question if len(question) <= 120 else question[:117] + "...",
             ("  [" + "; ".join(notes) + "]") if notes else "")


# ---- protocol: OpenAI-compatible shape -------------------------------------

def openai_model_list():
    return {"object": "list", "data": [{
        "id": MODEL_ID, "object": "model", "created": _now(), "owned_by": "cairn",
    }]}


def openai_chunk(cid, created, delta, finish_reason=None):
    return {"id": cid, "object": "chat.completion.chunk", "created": created,
            "model": MODEL_ID,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]}


def openai_completion(cid, created, text, prompt_text):
    return {"id": cid, "object": "chat.completion", "created": created,
            "model": MODEL_ID,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": text}}],
            # Estimated, not metered: these fields exist because clients read them.
            "usage": {"prompt_tokens": estimate_tokens(prompt_text),
                      "completion_tokens": estimate_tokens(text),
                      "total_tokens": estimate_tokens(prompt_text) + estimate_tokens(text)}}


# ---- protocol: Ollama-compatible shape -------------------------------------

def ollama_tag_list():
    return {"models": [{
        "name": f"{MODEL_ID}:latest", "model": f"{MODEL_ID}:latest",
        "modified_at": _iso_now(), "size": 0, "digest": MODEL_ID,
        "details": {"parent_model": "", "format": "gguf", "family": MODEL_ID,
                    "families": [MODEL_ID], "parameter_size": "local",
                    "quantization_level": "local"},
    }]}


def ollama_show():
    return {"license": "", "modelfile": "", "parameters": "", "template": "",
            "details": ollama_tag_list()["models"][0]["details"],
            "model_info": {"general.architecture": "cairn"},
            "capabilities": ["completion"]}


def ollama_chunk(content, done=False, total_ns=0):
    obj = {"model": f"{MODEL_ID}:latest", "created_at": _iso_now(),
           "message": {"role": "assistant", "content": content}, "done": done}
    if done:
        obj.update({"done_reason": "stop", "total_duration": total_ns,
                    "load_duration": 0, "prompt_eval_count": 0, "eval_count": 0})
    return obj


# ---- minimal web UI --------------------------------------------------------

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Cairn</title><style>
 body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:820px;
  margin:40px auto;padding:0 16px;background:#0f1417;color:#d7dee3}
 h1{font-size:15px;letter-spacing:.14em;text-transform:uppercase;color:#4fd1c5}
 textarea{width:100%;box-sizing:border-box;background:#161d22;color:#d7dee3;
  border:1px solid #263039;border-radius:8px;padding:12px;font-size:15px;min-height:64px}
 button{margin-top:8px;background:#2f7d76;color:#062521;border:0;border-radius:7px;
  padding:10px 18px;font-weight:600;cursor:pointer}
 #ans{white-space:pre-wrap;background:#161d22;border:1px solid #263039;border-radius:8px;
  padding:16px;margin-top:18px;min-height:20px}
 .cites{margin-top:14px;font-size:13px;color:#7d8b95}
 .cite{padding:6px 0;border-top:1px solid #263039}
 .n{color:#4fd1c5;font-family:ui-monospace,monospace}
 .muted{color:#7d8b95;font-size:12px}
 .path{display:block;color:#5b6770;font-family:ui-monospace,monospace;font-size:11px;
  margin-top:2px;user-select:all;word-break:break-all}
 a{color:#4fd1c5}
 #strength{display:none;font-family:ui-monospace,monospace;font-size:12px;margin:14px 0 0;
  padding:6px 10px;border-radius:6px;border:1px solid #263039}
 #strength.Strong{color:#4fd1c5;border-color:#2f7d76}
 #strength.Moderate{color:#e0a458;border-color:#6b5330}
 #strength.Weak{color:#e06c75;border-color:#6b3339}
</style></head><body>
<h1>Cairn</h1>
<p class="muted">Evidence-only answers over your indexed documents. Nothing leaves this machine. <span id="build"></span></p>
<textarea id="q" placeholder="Ask a question about the indexed documents..."></textarea><br>
<button onclick="go()">Ask</button>
<div id="strength"></div>
<div id="ans"></div><div class="cites" id="cites"></div>
<script>
async function go(){
 const q=document.getElementById('q').value.trim(); if(!q)return;
 const ans=document.getElementById('ans');
 document.getElementById('cites').innerHTML='';
 ans.textContent=''; let answer=''; let started=false;
 const sb=document.getElementById('strength'); sb.style.display='none'; sb.className='';
 let secs=0; ans.textContent='Retrieving...';
 const timer=setInterval(()=>{if(!started){secs++;ans.textContent='Retrieving... '+secs+'s';}},1000);
 try{
  const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({question:q})});
  const reader=r.body.getReader(); const dec=new TextDecoder(); let buf='';
  while(true){
    const {value,done}=await reader.read(); if(done)break;
    buf+=dec.decode(value,{stream:true});
    let idx;
    while((idx=buf.indexOf('\\n\\n'))>=0){
      const block=buf.slice(0,idx); buf=buf.slice(idx+2);
      const ev=(block.match(/event: (.*)/)||[])[1];
      const dm=block.match(/data: (.*)/); if(!dm)continue;
      const data=JSON.parse(dm[1]);
      if(ev==='strength'){ sb.className=data.label;
        sb.textContent='Retrieval: '+data.label+(data.distance!=null?' ('+data.distance+')':'')+' \u2014 '+data.note;
        sb.style.display='block'; }
      else if(ev==='token'){ if(!started){started=true;clearInterval(timer);ans.textContent='';}
        answer+=data.t; ans.textContent=answer; }
      else if(ev==='citations'){ renderCites(data.citations); }
    }
  }
  clearInterval(timer);
  if(!answer)ans.textContent='(no answer returned)';
 }catch(e){clearInterval(timer);ans.textContent='Error: '+e;}
}
function renderCites(cs){
  document.getElementById('cites').innerHTML=cs.map(c=>{
   const label={source:'open source',obsidian:'open in Obsidian',open:'open original'}[c.link_kind]||'open';
   const anchor=(c.link_kind==='open')
     ? `<a href="#" onclick="openDoc('${c.doc_id}');return false;">${label}</a>`
     : `<a href="${c.link}" target="_blank" rel="noreferrer">${label}</a>`;
   return `<div class="cite"><span class="n">[${c.n}]</span> ${c.source_name}
    <span class="muted">&mdash; ${c.heading||''} (dist ${c.distance})</span><br>${anchor}</div>`;
  }).join('');
}
async function openDoc(id){
 try{
  const r=await fetch('/open?doc='+encodeURIComponent(id));
  const d=await r.json();
  if(!d.ok) alert('Could not open: '+d.message);
 }catch(e){alert('Open failed: '+e);}
}
document.getElementById('q').addEventListener('keydown',e=>{
 if(e.key==='Enter'&&(e.ctrlKey||e.metaKey))go();});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    # ---- plumbing ----------------------------------------------------------

    def _cors_headers(self):
        """
        Echo the Origin only if it is on the allowlist. A disallowed origin gets no
        CORS header at all, so the browser refuses to hand it the response body.
        """
        origin = self.headers.get("Origin")
        if origin and origin.startswith(ALLOWED_ORIGINS):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Vary", "Origin")

    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        # Never let the browser cache Cairn's pages/responses. This is what prevents
        # a stale UI running old JavaScript against a newer server.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(b)

    def _send_json(self, code, obj):
        self._send(code, json.dumps(obj))

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _open_stream(self, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self._cors_headers()
        self.end_headers()

    def do_OPTIONS(self):
        # CORS preflight. Electron-based clients send this before POSTing.
        self.send_response(204)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---- routing -----------------------------------------------------------

    def do_POST(self):
        from urllib.parse import urlparse
        path = urlparse(self.path).path.rstrip("/")
        if path == "/ask":
            return self.handle_ask()
        # Lenient suffix matching: clients differ on whether the configured base URL
        # already ends in /v1, which otherwise produces /v1/v1/chat/completions.
        if path.endswith("/chat/completions"):
            return self.handle_openai_chat()
        if path == "/api/chat":
            return self.handle_ollama_chat()
        if path == "/api/show":
            return self._send_json(200, ollama_show())
        self._send_json(404, {"error": "not found"})

    def handle_ask(self):
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length).decode("utf-8"))
        question = (req.get("question") or "").strip()
        identity = req.get("identity", "self")  # pass-through from day one; "self" locally
        if not question:
            log.warning("rejected empty question")
            self._send(400, json.dumps({"error": "empty question"}))
            return

        log.info('ASK (%s): "%s"', identity, question if len(question) <= 120 else question[:117] + "...")
        t0 = time.time()

        # Front door: same three lanes as the protocol path, so the two faces cannot
        # drift. No strength event is sent, because no retrieval ran; the UI leaves
        # its strength box hidden and the reply carries its own receipt.
        lane = frontdoor.classify(question)
        if lane != frontdoor.ASK:
            log.info("front door: lane=%s (no retrieval, no model call)", lane)
            conn = dbmod.connect()
            try:
                text = frontdoor.front_door_reply(conn, lane)
            finally:
                conn.close()
            self._open_stream("text/event-stream")
            try:
                self.wfile.write(f"event: token\ndata: {json.dumps({'t': text})}\n\n".encode("utf-8"))
                self.wfile.write(f"event: citations\ndata: {json.dumps({'citations': []})}\n\n".encode("utf-8"))
                self.wfile.write(f"event: done\ndata: {json.dumps({'elapsed': round(time.time() - t0, 2)})}\n\n".encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                log.info("client disconnected mid-stream")
            log.info("front door complete in %.2fs", time.time() - t0)
            return

        # Stream Server-Sent Events: retrieve first (fast), then stream answer tokens,
        # then a final event carrying the citations.
        try:
            conn = dbmod.connect(); load_vec(conn)
            rows = retrieve(conn, question, TOP_K)
            citations = build_citations(rows)
        except Exception as e:
            log.exception("retrieval failed: %s", e)
            self._send(500, json.dumps({"error": str(e)}))
            return

        self._open_stream("text/event-stream")

        def sse(event, data):
            self.wfile.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8"))
            self.wfile.flush()

        try:
            # Retrieval-strength: computed from the closest match distance, sent first.
            top_dist = rows[0][5] if rows else None
            label, note = retrieval_strength(top_dist)
            sse("strength", {"label": label, "note": note,
                             "distance": round(top_dist, 3) if top_dist is not None else None})
            log.info("retrieval strength: %s (top dist %s)", label,
                     f"{top_dist:.3f}" if top_dist is not None else "n/a")
            if top_dist is not None and top_dist >= frontdoor.NO_HOPE_DISTANCE:
                log.info("no-hope floor fired: top dist %.3f >= %.3f (model not called)",
                         top_dist, frontdoor.NO_HOPE_DISTANCE)
                sse("token", {"t": frontdoor.no_hope_reply(REFUSAL_TEXT, rows)})
            else:
                collected = []
                for piece in synthesize_stream(question, rows):
                    collected.append(piece)
                    sse("token", {"t": piece})
                note = check_citations("".join(collected), len(rows))
                if note:
                    sse("token", {"t": note})
            sse("citations", {"citations": citations})
            sse("done", {"elapsed": round(time.time() - t0, 1)})
        except (BrokenPipeError, ConnectionResetError):
            log.info("client disconnected mid-stream")
        finally:
            conn.close()
        log.info("ASK complete in %.1fs total (%d citations)", time.time() - t0, len(citations))

    # ---- protocol handlers -------------------------------------------------

    def _protocol_question(self, shape, req):
        """
        Shared front half of both protocol handlers: extract the question from
        an already-read request, log the discards. Returns the question, or
        None after sending an error response.
        """
        question, dropped, foreign_system = extract_question(req.get("messages"))
        if not question:
            log.warning("%s: no user message in request", shape)
            self._send_json(400, {"error": {"message": "no user message in request",
                                            "type": "invalid_request_error"}})
            return None
        log_protocol_request(shape, req.get("model"), question, dropped, foreign_system)
        # Note what is deliberately NOT read from req beyond "messages", "model" and
        # "stream": no "system", "temperature", "top_p", "options", or "tools".
        # See the PROTOCOL section for why.
        return question

    # ---- interview routing ---------------------------------------------------
    # /interview and /checkin turn the chat into a structured interview
    # (interview.py). Routing is decided from the FULL message history: a
    # trigger command in the latest message, or an interview already in
    # progress (last marked turn not yet confirmed or cancelled). Everything
    # else falls through to retrieval untouched -- the single-question,
    # drop-earlier-turns contract of the protocol face is unchanged for
    # normal questions.

    def _interview_reply(self, shape, req):
        """Route one interview turn, streaming in the requested dialect."""
        msgs = req.get("messages")
        t0 = time.time()
        log.info("%s INTERVIEW turn (history: %d message(s))", shape, len(msgs or []))

        if shape == "openai":
            req_stream = bool(req.get("stream", False))
            cid, created = _completion_id(), _now()
            if not req_stream:
                text = "".join(interview.handle(msgs)).strip()
                self._send_json(200, openai_completion(cid, created, text, ""))
                log.info("openai interview turn complete in %.1fs", time.time() - t0)
                return
            self._open_stream("text/event-stream")
            try:
                self.wfile.write(f"data: {json.dumps(openai_chunk(cid, created, {'role': 'assistant'}))}\n\n".encode("utf-8"))
                for piece in interview.handle(msgs):
                    self.wfile.write(f"data: {json.dumps(openai_chunk(cid, created, {'content': piece}))}\n\n".encode("utf-8"))
                    self.wfile.flush()
                self.wfile.write(f"data: {json.dumps(openai_chunk(cid, created, {}, finish_reason='stop'))}\n\n".encode("utf-8"))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                log.info("openai client disconnected mid-interview")
                return
            log.info("openai interview turn complete in %.1fs", time.time() - t0)
            return

        # ollama shape: newline-delimited JSON
        req_stream = bool(req.get("stream", True))
        if not req_stream:
            text = "".join(interview.handle(msgs)).strip()
            self._send_json(200, ollama_chunk(text, done=True,
                                              total_ns=int((time.time() - t0) * 1e9)))
            log.info("ollama interview turn complete in %.1fs", time.time() - t0)
            return
        self._open_stream("application/x-ndjson")
        try:
            for piece in interview.handle(msgs):
                self.wfile.write((json.dumps(ollama_chunk(piece)) + "\n").encode("utf-8"))
                self.wfile.flush()
            self.wfile.write((json.dumps(ollama_chunk("", done=True,
                              total_ns=int((time.time() - t0) * 1e9))) + "\n").encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            log.info("ollama client disconnected mid-interview")
        log.info("ollama interview turn complete in %.1fs", time.time() - t0)

    def handle_openai_chat(self):
        req = self._read_json()
        if interview.is_interview(req.get("messages")):
            return self._interview_reply("openai", req)
        question = self._protocol_question("openai", req)
        if question is None:
            return
        req_stream = bool(req.get("stream", False))   # OpenAI default: not streaming
        cid, created, t0 = _completion_id(), _now(), time.time()

        if not req_stream:
            try:
                text = "".join(cairn_reply_stream(question)).strip()
            except Exception as e:
                log.exception("openai completion failed: %s", e)
                self._send_json(500, {"error": {"message": str(e), "type": "server_error"}})
                return
            self._send_json(200, openai_completion(cid, created, text, question))
            log.info("openai complete in %.1fs (%d chars)", time.time() - t0, len(text))
            return

        self._open_stream("text/event-stream")

        def send(obj):
            self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode("utf-8"))
            self.wfile.flush()

        try:
            send(openai_chunk(cid, created, {"role": "assistant"}))
            for piece in cairn_reply_stream(question):
                send(openai_chunk(cid, created, {"content": piece}))
            send(openai_chunk(cid, created, {}, finish_reason="stop"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            log.info("openai client disconnected mid-stream")
            return
        except Exception as e:
            log.exception("openai stream failed: %s", e)
            return
        log.info("openai stream complete in %.1fs", time.time() - t0)

    def handle_ollama_chat(self):
        req = self._read_json()
        if interview.is_interview(req.get("messages")):
            return self._interview_reply("ollama", req)
        question = self._protocol_question("ollama", req)
        if question is None:
            return
        req_stream = bool(req.get("stream", True))    # Ollama default: streaming
        t0 = time.time()

        if not req_stream:
            try:
                text = "".join(cairn_reply_stream(question)).strip()
            except Exception as e:
                log.exception("ollama completion failed: %s", e)
                self._send_json(500, {"error": str(e)})
                return
            obj = ollama_chunk(text, done=True, total_ns=int((time.time() - t0) * 1e9))
            self._send_json(200, obj)
            log.info("ollama complete in %.1fs (%d chars)", time.time() - t0, len(text))
            return

        # Ollama streams newline-delimited JSON, not SSE.
        self._open_stream("application/x-ndjson")

        def send(obj):
            self.wfile.write((json.dumps(obj) + "\n").encode("utf-8"))
            self.wfile.flush()

        try:
            for piece in cairn_reply_stream(question):
                send(ollama_chunk(piece))
            send(ollama_chunk("", done=True, total_ns=int((time.time() - t0) * 1e9)))
        except (BrokenPipeError, ConnectionResetError):
            log.info("ollama client disconnected mid-stream")
            return
        except Exception as e:
            log.exception("ollama stream failed: %s", e)
            return
        log.info("ollama stream complete in %.1fs", time.time() - t0)

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if path.endswith("/v1/models") or path == "/models":
            return self._send_json(200, openai_model_list())
        if path == "/api/tags":
            return self._send_json(200, ollama_tag_list())
        if path == "/api/version":
            # Some Ollama-flavoured clients probe this before showing a model list.
            return self._send_json(200, {"version": f"cairn-{BUILD}"})
        if parsed.path in ("/", "/index.html"):
            page = PAGE.replace('id="build"></span>', f'id="build">build {BUILD}</span>')
            self._send(200, page, "text/html; charset=utf-8")
        elif parsed.path == "/health":
            self._send(200, json.dumps({"ok": True}))
        elif parsed.path == "/open":
            doc_id = (parse_qs(parsed.query).get("doc") or [""])[0]
            conn = dbmod.connect()
            ok, msg = open_original(conn, doc_id)
            conn.close()
            log.info("OPEN doc=%s -> %s (%s)", doc_id[:16], ok, msg)
            self._send(200 if ok else 404, json.dumps({"ok": ok, "message": msg}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, *a):
        pass  # suppress the default per-request access line; we log meaningfully above


def check_embed_model(conn):
    """
    Loud-failure guard: refuse to serve if the configured embedding model does
    not match the one the index was actually built with (index.py owns writing
    that stamp via check_and_stamp_embed_model). A silent mismatch here would
    mean the query vector speaks a different geometry than the indexed vectors
    -- retrieval quietly degrades or returns garbage, with no error anywhere.
    """
    stored_model = dbmod.get_meta(conn, "embed_model")
    if stored_model is None:
        log.warning("no embed_model stamp in meta table yet -- index.py has not run. "
                    "Proceeding; run index.py to build/stamp the index.")
        return
    stored_dim = dbmod.get_meta(conn, "embedding_dim")
    if stored_model != config.EMBED_MODEL or (stored_dim is not None and str(stored_dim) != str(config.EMBEDDING_DIM)):
        raise SystemExit(
            "EMBEDDING MODEL MISMATCH -- refusing to serve.\n"
            f"  index was built with  : {stored_model} (dim {stored_dim})\n"
            f"  currently configured  : {config.EMBED_MODEL} (dim {config.EMBEDDING_DIM})\n"
            "Serving now would embed questions with a different model than the one\n"
            "that built the index, silently corrupting retrieval. Fix by either:\n"
            "  1. Deleting cairn.db and letting the watcher rebuild the index, or\n"
            "  2. Reverting EMBED_MODEL back to the model above (config.py or models.local.json)."
        )


def serve(host=HOST, port=PORT):
    conn = dbmod.connect(); load_vec(conn)
    if vec_table_exists(conn):
        n = conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
    else:
        n = 0
        log.warning("index is empty (no vec_chunks table yet) -- starting anyway; "
                    "the watcher will populate it as documents are ingested")
    conn.close()
    base = f"http://{host}:{port}"
    print(f"Cairn service on {base}  ({n} vectors indexed)")
    print(f"  Web UI             {base}/")
    print(f"  OpenAI-compatible  {base}/v1        model: {MODEL_ID}   (API key: any value)")
    print(f"  Ollama-compatible  {base}           model: {MODEL_ID}:latest")
    print("Ctrl+C to stop.")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


def main():
    ap = argparse.ArgumentParser(description="Cairn ask service")
    ap.add_argument("--ask", metavar="Q", help="one-shot question, print answer and exit")
    ap.add_argument("--port", type=int, default=PORT,
                    help=f"port to serve on (default {PORT}; tests use a scratch port)")
    ap.add_argument("--host", default=HOST, help=f"interface to bind (default {HOST})")
    args = ap.parse_args()

    startup_conn = dbmod.connect(); dbmod.init_db(startup_conn)
    check_embed_model(startup_conn)
    startup_conn.close()

    if args.ask:
        conn = dbmod.connect(); load_vec(conn)
        text, citations = answer(conn, args.ask)
        print("\n" + text + "\n")
        print("Sources:")
        for c in citations:
            print(f"  [{c['n']}] {c['source_name']}  {c['heading']}  (dist {c['distance']})")
    else:
        serve(args.host, args.port)


if __name__ == "__main__":
    main()
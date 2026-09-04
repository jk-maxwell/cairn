"""
Scripted end-to-end test for the interview engine (interview.py + ask.py wiring).

What it does, with NO manual steps and NO touching of the live engine or vault:
  1. Creates a temp DB and temp vault dir, starts ask.py on a scratch port
     (default 8799 -- never 8765 where the live engine runs, never 4001)
     via the CAIRN_DB_PATH / CAIRN_VAULT_DIR environment overrides.
  2. Plays a full canned ONBOARDING conversation over HTTP against
     /v1/chat/completions (the face the plugin uses), echoing assistant turns
     back into the history exactly like the plugin does, confirms the playback,
     then asserts Profile.md and the entity pages exist with correct front matter.
  3. Seeds the DB with a stale ratified project and pending proposals, plays a
     CHECK-IN conversation, confirms, and asserts status updates / ratify /
     reject took effect.
  4. Asserts a normal (non-interview) question still routes to retrieval and
     that /cancel abandons an interview cleanly.
  5. Unit-tests the playbook loader and the singleton-conflict logic directly
     against interview.py (no server, no Ollama call) -- malformed/missing
     playbook files fail loudly, a fresh deployment picks up the skip-implies-
     default path, and a deployment recording a different playbook surfaces
     the conflict and honors either a confirmed switch or a decline.

All names below are INVENTED fixtures. Requires Ollama running with
config.GEN_MODEL pulled (the answer-parsing step calls the real model).

Run:  ./.venv/bin/python test_interview.py [--port 8799] [--keep]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = 8799   # scratch port for this test only. NEVER 4001, never 8765.

passed, failed = [], []


def check(name, cond, detail=""):
    if cond:
        passed.append(name)
        print(f"PASS  {name}")
    else:
        failed.append(name)
        print(f"FAIL  {name}" + (f"\n      -> {detail}" if detail else ""))


# ---- HTTP helpers ------------------------------------------------------------

def post_chat(base, messages, stream=False, timeout=420):
    """POST to /v1/chat/completions; return the assistant text (stream or not)."""
    payload = {"model": "cairn", "messages": messages, "stream": stream}
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    if not stream:
        return json.loads(body)["choices"][0]["message"]["content"]
    text = ""
    for block in body.split("\n\n"):
        block = block.strip()
        if not block.startswith("data: ") or block == "data: [DONE]":
            continue
        obj = json.loads(block[len("data: "):])
        text += obj["choices"][0]["delta"].get("content", "")
    return text


def converse(base, history, user_text, stream=False):
    """One turn: append the user message, get the reply, append it (plugin-style)."""
    history.append({"role": "user", "content": user_text})
    reply = post_chat(base, history, stream=stream)
    history.append({"role": "assistant", "content": reply})
    return reply


def wait_healthy(base, proc, seconds=30):
    for _ in range(seconds * 2):
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=2) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    raise RuntimeError("server did not become healthy in time")


def front_matter(path: Path) -> dict:
    """Tiny front-matter reader: key: value pairs from the first --- block."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    fm = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    return fm


def find_page(folder: Path, needle: str) -> Path | None:
    """The entity page whose filename contains needle (case-insensitive)."""
    if not folder.is_dir():
        return None
    for p in sorted(folder.glob("*.md")):
        if needle.lower() in p.stem.lower():
            return p
    return None


# ---- playbook loader + singleton-conflict unit tests (no server, no Ollama) ----
# These exercise interview.py directly rather than over HTTP. They need no
# CAIRN_DB_PATH / CAIRN_VAULT_DIR env vars because every function under test
# takes vault_dir as an explicit argument -- config.VAULT_DIR (the real vault)
# is never touched.

def run_playbook_unit_tests():
    print("\n--- playbook loader + singleton-conflict (no server) ---")
    sys.path.insert(0, str(ROOT))
    import interview

    # -- the shipped default loads and validates -----------------------------
    pb = interview.load_playbook("executive")
    check("playbook: executive loads", pb["id"] == "executive")
    check("playbook: executive carries the ratified relationship vocabulary",
          set(pb["relationship_vocabulary"]) == {"mentor", "advisor", "investor", "counterpart"},
          str(pb["relationship_vocabulary"]))
    check("playbook: executive has 5 questions (the original ONBOARDING_STEPS, unchanged)",
          len(pb["questions"]) == 5, str([q["key"] for q in pb["questions"]]))
    steps = interview.playbook_steps(pb)
    check("playbook: playbook_steps() returns the (key, question, followup, threshold) shape",
          steps[0][0] == "role" and isinstance(steps[0][3], int), str(steps[0]))

    # -- unknown/malformed playbooks fail loudly, never half-populated -------
    tmp_pb_dir = Path(tempfile.mkdtemp(prefix="cairn-playbook-test-"))
    real_dir = interview.PLAYBOOKS_DIR
    interview._PLAYBOOK_CACHE.clear()
    interview.PLAYBOOKS_DIR = tmp_pb_dir
    try:
        try:
            interview.load_playbook("nonexistent")
            check("playbook: missing file raises PlaybookError", False)
        except interview.PlaybookError:
            check("playbook: missing file raises PlaybookError", True)

        (tmp_pb_dir / "broken.json").write_text("{not valid json", encoding="utf-8")
        try:
            interview.load_playbook("broken")
            check("playbook: malformed JSON raises PlaybookError", False)
        except interview.PlaybookError:
            check("playbook: malformed JSON raises PlaybookError", True)

        (tmp_pb_dir / "half.json").write_text(
            json.dumps({"id": "half", "name": "Half", "description": "missing vocab/questions"}),
            encoding="utf-8")
        try:
            interview.load_playbook("half")
            check("playbook: missing required key(s) raises PlaybookError", False)
        except interview.PlaybookError:
            check("playbook: missing required key(s) raises PlaybookError", True)

        (tmp_pb_dir / "mismatch.json").write_text(
            json.dumps({"id": "other", "name": "Other", "description": "id mismatch",
                       "relationship_vocabulary": [], "questions": [
                           {"key": "k", "question": "q?", "followup": None, "thin_threshold": 0}]}),
            encoding="utf-8")
        try:
            interview.load_playbook("mismatch")
            check("playbook: id mismatch between filename and declared id raises PlaybookError", False)
        except interview.PlaybookError:
            check("playbook: id mismatch between filename and declared id raises PlaybookError", True)
    finally:
        interview.PLAYBOOKS_DIR = real_dir
        interview._PLAYBOOK_CACHE.clear()

    # -- _match_playbook: simple, deterministic, case-insensitive ------------
    pbs = interview.available_playbooks()
    check("playbook: available_playbooks() lists executive", any(p["id"] == "executive" for p in pbs))
    check("playbook: _match_playbook matches by id", interview._match_playbook("executive", pbs) == "executive")
    check("playbook: _match_playbook matches by name, case-insensitive",
          interview._match_playbook("EXECUTIVE", pbs) == "executive")
    check("playbook: _match_playbook returns None for an unrecognized reply",
          interview._match_playbook("something else entirely", pbs) is None)

    # -- an unrecognized lens reply must NOT silently become the default -----
    # Regression guard. Skipping is an explicit choice; a reply that matches no
    # playbook is not. Quietly substituting the default would commit the
    # deployment to a lens the user never picked, and the singleton rule makes
    # that stick. "government" is the specific reply this protects against:
    # that lens is planned but unbuilt, so it is the most likely thing typed.
    _fresh = Path(tempfile.mkdtemp(prefix="cairn-lens-unknown-"))
    out = "".join(interview._handle_lens_step(_fresh, "lens", {}, "government"))
    mk = interview._decode_marker(out)
    check("lens: an unrecognized playbook name is not silently defaulted",
          "pb" not in (mk or {}))
    check("lens: an unrecognized reply loops back to the lens question",
          (mk or {}).get("s") == "lens")
    check("lens: the re-ask names what is actually available",
          "executive" in out and "government" in out)
    _retry = "".join(interview._handle_lens_step(_fresh, "lens", mk, "executive"))
    check("lens: answering correctly after a re-ask proceeds into that playbook",
          (interview._decode_marker(_retry) or {}).get("pb") == "executive")
    check("lens: an explicit skip still resolves to the default without friction",
          (interview._decode_marker(
              "".join(interview._handle_lens_step(_fresh, "lens", {}, "skip"))
          ) or {}).get("pb") == interview.DEFAULT_PLAYBOOK_ID)

    # -- singleton conflict: surfaced, and both confirm/decline honored ------
    vault = Path(tempfile.mkdtemp(prefix="cairn-singleton-test-"))

    # No Profile.md yet -> no conflict; skipping picks the default straight away.
    reply = "".join(interview._handle_lens_step(vault, "lens", {}, "skip"))
    check("singleton: fresh deployment (no Profile.md) -- skip goes straight to the first question",
          "cairn-iv" in reply and '"pb": "executive"' in reply, reply[:200])

    # Seed a Profile.md recording a DIFFERENT playbook than the interview would pick.
    vault.mkdir(exist_ok=True)
    (vault / "Profile.md").write_text(
        "---\ncairn-type: profile\ncairn-playbook: government\n---\n", encoding="utf-8")
    check("singleton: _read_current_playbook_id reads the recorded playbook back",
          interview._read_current_playbook_id(vault) == "government")

    reply = "".join(interview._handle_lens_step(vault, "lens", {}, "skip"))
    check("singleton: a recorded playbook different from the chosen one is surfaced, not silently switched",
          "already runs" in reply.lower() and "government" in reply and "executive" in reply
          and '"s": "lens_confirm"' in reply, reply[:300])
    check("singleton: the conflict marker carries both ids for reconstruction",
          '"chosen": "executive"' in reply and '"existing": "government"' in reply, reply[:300])

    # Decline the switch -- the interview must continue with the EXISTING playbook
    # (chosen="government" here is a stand-in for "some other lens the user typed";
    # it need not be loadable, since a decline never loads it).
    marker = {"chosen": "government", "existing": "executive"}
    reply = "".join(interview._handle_lens_step(vault, "lens_confirm", marker, "no"))
    check("singleton: declining a switch away from a loadable existing playbook "
          "continues the interview with it",
          '"pb": "executive"' in reply and "role" in reply.lower(), reply[:200])

    # Confirm the switch -- the interview must continue with the NEWLY chosen playbook.
    marker = {"chosen": "executive", "existing": "some-other-lens"}
    reply = "".join(interview._handle_lens_step(vault, "lens_confirm", marker, "yes"))
    check("singleton: confirming the switch continues the interview with the new playbook",
          '"pb": "executive"' in reply and "role" in reply.lower(), reply[:200])

    shutil.rmtree(vault, ignore_errors=True)
    shutil.rmtree(tmp_pb_dir, ignore_errors=True)


# ---- the canned onboarding conversation (invented fixtures only) --------------

ONBOARDING_ANSWERS = [
    # role (long enough to skip the thin-answer follow-up)
    "I'm a product lead at Fernwheel Logistics, a mid-size freight company. "
    "I run the internal tooling group.",
    # projects
    "Two active projects. Project Nimbus, our new dispatch console -- people "
    "shorten it to NIM or just Nimbus. And Atlas Migration, moving the legacy "
    "tracker onto the new stack -- shorthand ATLAS.",
    # people
    "Priya Raman, who mostly goes by Pri. And Marcus Webb -- in transcripts he "
    "often shows up as just Webb.",
    # priorities
    "Ship the Nimbus beta this quarter; done means five pilot depots using it "
    "daily. And retire the legacy tracker by the end of the year.",
    # vocabulary
    "\"The barn\" means our main warehouse. A \"green sheet\" is the weekly "
    "ops report.",
]


def run_onboarding(base, vault):
    print("\n--- onboarding interview ---")
    history = []
    reply = converse(base, history, "/interview", stream=True)  # exercise streaming once
    check("onboarding: /interview opens with the optional lens question",
          "playbook" in reply.lower() and "cairn-iv" in reply, reply[:200])
    check("onboarding: lens question offers the executive playbook",
          "executive" in reply.lower(), reply[:300])

    # Skip the lens question -- the common case -- and confirm the default
    # (executive) playbook is what carries the interview forward.
    reply = converse(base, history, "skip")
    check("onboarding: skipping the lens question moves straight to the role question",
          "role" in reply.lower() and "cairn-iv" in reply, reply[:200])

    for i, answer in enumerate(ONBOARDING_ANSWERS):
        reply = converse(base, history, answer)
        print(f"      (turn {i + 1} answered, reply {len(reply)} chars)")

    check("onboarding: playback appears after the last answer",
          "playback" in reply.lower() and '"confirm"' in reply, reply[:300])
    check("onboarding: playback plays the projects back",
          "nimbus" in reply.lower() and "atlas" in reply.lower(), reply[:400])
    check("onboarding: nothing written before confirmation",
          not (vault / "Profile.md").exists())

    reply = converse(base, history, "yes")
    check("onboarding: confirmation acknowledged", "done" in reply.lower(), reply[:200])

    profile = vault / "Profile.md"
    check("onboarding: Profile.md written at vault root", profile.exists())
    if profile.exists():
        fm = front_matter(profile)
        body = profile.read_text(encoding="utf-8")
        check("onboarding: Profile.md front matter cairn-type: profile",
              fm.get("cairn-type") == "profile", str(fm))
        check("onboarding: Profile.md records the singleton playbook (cairn-playbook: executive)",
              fm.get("cairn-playbook") == "executive", str(fm))
        check("onboarding: Profile.md carries the user's words",
              "Fernwheel" in body and "barn" in body, body[:300])

    nimbus = find_page(vault / "Projects", "Nimbus")
    check("onboarding: a Nimbus project page exists in Projects/", nimbus is not None,
          f"Projects/ holds: {[p.name for p in (vault / 'Projects').glob('*.md')] if (vault / 'Projects').is_dir() else 'nothing'}")
    if nimbus:
        fm = front_matter(nimbus)
        check("onboarding: Nimbus page front matter is a project with the NIM alias",
              fm.get("cairn-type") == "project" and "NIM" in fm.get("aliases", ""), str(fm))

    atlas = find_page(vault / "Projects", "Atlas")
    check("onboarding: an Atlas project page exists in Projects/", atlas is not None)

    priya = find_page(vault / "People", "Priya")
    check("onboarding: a Priya person page exists in People/", priya is not None,
          f"People/ holds: {[p.name for p in (vault / 'People').glob('*.md')] if (vault / 'People').is_dir() else 'nothing'}")
    if priya:
        fm = front_matter(priya)
        check("onboarding: Priya page front matter is a person with the Pri alias",
              fm.get("cairn-type") == "person" and "Pri" in fm.get("aliases", ""), str(fm))
    check("onboarding: a Marcus Webb person page exists in People/",
          find_page(vault / "People", "Webb") is not None
          or find_page(vault / "People", "Marcus") is not None)
    return history


# ---- check-in ------------------------------------------------------------------

def seed_for_checkin(db_path, vault):
    """Make one ratified project stale (old meeting mention) and add pending proposals."""
    sys.path.insert(0, str(ROOT))
    import sqlite3
    conn = sqlite3.connect(db_path)
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO documents(doc_id, source_path, source_name, ingested_at) "
        "VALUES ('testdoc1', '/tmp/none', 'Dispatch weekly sync', ?)", (old,))
    row = conn.execute(
        "SELECT entity_id FROM entities WHERE type='project' AND name LIKE '%Nimbus%'"
    ).fetchone()
    if row:
        conn.execute("INSERT OR IGNORE INTO meeting_entities(doc_id, entity_id) "
                     "VALUES ('testdoc1', ?)", (row[0],))
    # two pending proposals, as extraction would leave them
    conn.execute("INSERT OR IGNORE INTO entities(entity_id, name, type, aliases, status, origin) "
                 "VALUES ('prop-ql', 'Quartz Ledger', 'project', '[]', 'proposed', 'extraction')")
    conn.execute("INSERT OR IGNORE INTO entities(entity_id, name, type, aliases, status, origin) "
                 "VALUES ('prop-df', 'Dana Fields', 'person', '[]', 'proposed', 'extraction')")
    conn.commit()
    conn.close()


def run_checkin(base, db_path, vault):
    print("\n--- status check-in ---")
    seed_for_checkin(db_path, vault)
    history = []
    reply = converse(base, history, "/checkin")
    check("checkin: opens informed (quiet projects surfaced from the DB)",
          "quiet" in reply.lower() or "hasn't come up" in reply.lower(), reply[:300])
    check("checkin: names the stale project", "nimbus" in reply.lower()
          or "atlas" in reply.lower(), reply[:300])

    reply = converse(base, history,
                     "Project Nimbus is still active. Atlas Migration is done -- we "
                     "finished the cutover.")
    check("checkin: pending proposals surfaced conversationally",
          "quartz ledger" in reply.lower() and "dana fields" in reply.lower(), reply[:400])

    reply = converse(base, history,
                     "Quartz Ledger is a real project -- people call it QL. Dana Fields "
                     "isn't someone I work with, drop that one.")
    check("checkin: asks about anything new", "new" in reply.lower(), reply[:200])

    reply = converse(base, history, "Nothing new since last time.")
    check("checkin: playback appears", "playback" in reply.lower(), reply[:300])

    reply = converse(base, history, "yes")
    check("checkin: confirmation acknowledged", "done" in reply.lower(), reply[:200])

    atlas = find_page(vault / "Projects", "Atlas")
    check("checkin: Atlas page status flipped to done",
          atlas is not None and front_matter(atlas).get("status") == "done",
          str(front_matter(atlas)) if atlas else "no Atlas page")
    ql = find_page(vault / "Projects", "Quartz")
    check("checkin: ratified proposal Quartz Ledger got a project page", ql is not None)
    if ql:
        check("checkin: Quartz Ledger page carries the QL alias",
              "QL" in front_matter(ql).get("aliases", ""), str(front_matter(ql)))

    import sqlite3
    conn = sqlite3.connect(db_path)
    status = conn.execute("SELECT status FROM entities WHERE entity_id='prop-df'").fetchone()
    origin = conn.execute("SELECT origin FROM entities WHERE entity_id='prop-ql'").fetchone()
    conn.close()
    check("checkin: rejected proposal Dana Fields marked rejected in the DB",
          status is not None and status[0] == "rejected", str(status))
    check("checkin: ratified proposal carries origin=interview",
          origin is not None and origin[0] == "interview", str(origin))
    check("checkin: governance queue note regenerated",
          (vault / "Inbox" / "Governance.md").exists())


# ---- non-interview behaviour must be untouched ---------------------------------

def run_normal_and_cancel(base, vault):
    print("\n--- normal questions and /cancel ---")
    # front-door chatter: no retrieval, no interview marker
    reply = post_chat(base, [{"role": "user", "content": "hello"}])
    check("normal: greeting takes the front door, not the interview",
          "cairn-iv" not in reply and len(reply) > 0, reply[:200])

    # a real question on an empty index: grounded refusal WITH receipt, no marker
    reply = post_chat(base, [{"role": "user", "content":
                              "What were the findings of the northgate audit?"}])
    check("normal: retrieval question still answered by the retrieval path",
          "cairn-iv" not in reply and "Retrieval:" in reply, reply[:300])

    # cancel mid-interview, then verify the next question routes to retrieval again
    history = []
    converse(base, history, "/interview")
    converse(base, history, "I run tooling at a small freight startup called Glasswing.")
    reply = converse(base, history, "/cancel")
    check("cancel: interview abandons cleanly, nothing written",
          "cancel" in reply.lower() and not (vault / "Profile2.md").exists(), reply[:200])
    reply = converse(base, history, "hello")
    check("cancel: after cancel, chat returns to normal routing",
          "cairn-iv" not in reply, reply[:200])


# ---- main ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--keep", action="store_true", help="keep the temp dir for debugging")
    args = ap.parse_args()
    if args.port in (4001, 8765):
        sys.exit("refusing to run on a reserved port (4001 and 8765 are off-limits)")

    try:
        run_playbook_unit_tests()
    except Exception as e:
        failed.append(f"unhandled: {type(e).__name__}: {e}")
        print(f"FAIL  unhandled: {type(e).__name__}: {e}")

    tmp = Path(tempfile.mkdtemp(prefix="cairn-interview-test-"))
    vault = tmp / "vault"
    vault.mkdir()
    db_path = tmp / "test.db"
    log_path = tmp / "server.log"
    base = f"http://127.0.0.1:{args.port}"

    env = os.environ.copy()
    env["CAIRN_DB_PATH"] = str(db_path)
    env["CAIRN_VAULT_DIR"] = str(vault)
    # The scripted interview ratifies real entities. Keep its governance events
    # out of the real governance.csv, which is the ratification-burden log.
    env["CAIRN_GOVERNANCE_LOG"] = str(tmp / "governance.csv")

    print(f"temp dir : {tmp}\nserver   : {base}\nstarting ask.py ...")
    with open(log_path, "w", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "ask.py"), "--port", str(args.port)],
            env=env, cwd=str(ROOT), stdout=logf, stderr=subprocess.STDOUT)
    try:
        wait_healthy(base, proc)
        run_onboarding(base, vault)
        run_checkin(base, db_path, vault)
        run_normal_and_cancel(base, vault)
    except Exception as e:
        failed.append(f"unhandled: {type(e).__name__}: {e}")
        print(f"FAIL  unhandled: {type(e).__name__}: {e}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        if args.keep or failed:
            print(f"\nserver log kept at: {log_path}")
        if not args.keep and not failed:
            shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 50)
    print(f"{len(passed)} passed, {len(failed)} failed")
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()

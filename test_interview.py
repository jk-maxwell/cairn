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

All names below are INVENTED fixtures. Requires Ollama running with
config.GEN_MODEL pulled (the answer-parsing step calls the real model).

Run:  py test_interview.py [--port 8799] [--keep]
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
    check("onboarding: /interview opens with the role question",
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

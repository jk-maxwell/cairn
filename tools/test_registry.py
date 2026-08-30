"""
test_registry.py -- the registry/governance acceptance CLI.

Exercises the vault-authoritative entity registry (registry.py) and its
integration with enrichment (enrich.py) against a TEMP vault and a TEMP
database, with the model call stubbed out. No Ollama required, no real vault
touched, nothing persists: every run builds its world in a tempdir and
removes it.

The cases are the acceptance list for the 2026-08-22 governance decisions:
  1.  scan_vault builds the ratified index from user-owned pages
  2.  match resolves exact / alias / case / shorter / longer forms -- and
      NEVER inserts or mutates
  3.  match sees only RATIFIED entities
  4.  propose records once, dedupes variants, respects rejected forever
  5.  checking a queue box ratifies: page created, status flipped, rollup block present
  6.  deleting a queue line rejects permanently; the name is never re-proposed
  7.  enrichment links only ratified names, proposes the rest, tags topics
  8.  re-ingest (re-enrichment) is idempotent: no duplicate rows or proposals
  9.  proposed entities get no pages and never reach ratified surfaces (Home)
  10. scan_vault picks up a manual alias edit on a page
  11. rollup regeneration touches ONLY the marked block; the user body survives
  12. --migrate demotes every pre-governance entity to a proposal, deletes the
      generated Cairn pages, and writes the initial queue note
  13. a fresh proposal recorded after the note was written is NOT mistaken
      for a user deletion

Run:  py tools/test_registry.py        (exit 0 = all green)
"""

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config          # noqa: E402
import db as dbmod     # noqa: E402
import enrich          # noqa: E402
import registry        # noqa: E402

PASSED, FAILED = [], []


def check(name, fn):
    try:
        fn()
        PASSED.append(name)
        print(f"PASS  {name}")
    except Exception as e:
        FAILED.append(name)
        print(f"FAIL  {name}\n      -> {type(e).__name__}: {e}")


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ---- fixture world (all names invented; nothing from any real vault) --------

def make_world(tmp: Path):
    vault = tmp / "vault"
    (vault / "Projects").mkdir(parents=True)
    (vault / "People").mkdir(parents=True)
    (vault / "Meetings").mkdir(parents=True)

    (vault / "Projects" / "Atlas Migration.md").write_text(
        "---\ncairn-type: project\naliases: [Atlas, ATL]\nstatus: active\n---\n"
        "\nMy own notes about the migration. This body is mine.\n"
        "\n<!-- cairn:begin -->\n<!-- cairn:end -->\n",
        encoding="utf-8",
    )
    (vault / "People" / "Rowan Delacroix.md").write_text(
        "---\ncairn-type: person\naliases: [Rowan]\n---\n",
        encoding="utf-8",
    )
    (vault / "Profile.md").write_text(
        "---\ncairn-type: person\nname: Casey Winterbourne\naliases: [Casey]\n---\n"
        "\nI run the fixture team.\n",
        encoding="utf-8",
    )

    conn = sqlite3.connect(tmp / "test.db")
    conn.execute("PRAGMA foreign_keys = ON")
    dbmod.init_db(conn)

    # One fixture meeting document row + vault note, for provenance joins.
    meeting = vault / "Meetings" / "2026-01-15 Fixture sync.md"
    meeting.write_text("---\ntype: meeting\n---\nfixture body\n", encoding="utf-8")
    conn.execute(
        "INSERT INTO documents (doc_id, source_path, source_name, vault_path) VALUES (?,?,?,?)",
        ("doc-fixture-1", str(tmp / "src1.md"), "src1.md", str(meeting)),
    )
    conn.commit()
    return conn, vault


def entity_dump(conn):
    return conn.execute(
        "SELECT entity_id, name, type, aliases, note_path, status, origin "
        "FROM entities ORDER BY entity_id"
    ).fetchall()


# ---- cases ------------------------------------------------------------------

def run(tmp: Path):
    conn, vault = make_world(tmp)

    def c1_scan_builds_index():
        counts = registry.scan_vault(conn, vault)
        expect(counts["pages"] == 3, f"expected 3 registry pages, got {counts}")
        expect(counts["added"] == 3, f"expected 3 added, got {counts}")
        rows = entity_dump(conn)
        expect(len(rows) == 3, f"expected 3 entities, got {len(rows)}")
        expect(all(r[5] == "ratified" for r in rows), "scan rows must be ratified")
        names = {r[1] for r in rows}
        expect(names == {"Atlas Migration", "Rowan Delacroix", "Casey Winterbourne"},
               f"unexpected names {names}")

    def c2_match_semantics_read_only():
        before = entity_dump(conn)
        cases = [
            ("Atlas Migration", "project", "Atlas Migration"),  # exact
            ("atlas migration", "project", "Atlas Migration"),  # case-insensitive
            ("ATL", "project", "Atlas Migration"),              # alias
            ("Atlas", "project", "Atlas Migration"),            # alias + shorter form
            ("Rowan", "person", "Rowan Delacroix"),             # shorter variant
            ("Rowan Delacroix Jr", "person", "Rowan Delacroix"),  # longer variant
            ("Casey", "person", "Casey Winterbourne"),          # Profile alias
            ("Zephyr", "project", None),                        # unknown
            ("Rowan Delacroix", "project", None),               # wrong type
        ]
        for name, etype, want in cases:
            got = registry.match(conn, name, etype)
            expect(got == want, f"match({name!r}, {etype!r}) = {got!r}, wanted {want!r}")
        expect(entity_dump(conn) == before, "match() mutated the entities table")

    def c3_match_ratified_only():
        registry.propose(conn, "Ghost Project", "project", "doc-fixture-1")
        expect(registry.match(conn, "Ghost Project", "project") is None,
               "match() returned a proposed entity")
        conn.execute("UPDATE entities SET status='rejected' WHERE name='Ghost Project'")
        conn.commit()
        expect(registry.match(conn, "Ghost Project", "project") is None,
               "match() returned a rejected entity")

    def c4_propose_dedupe_and_rejected():
        expect(registry.propose(conn, "Beacon Redesign", "project", "doc-fixture-1") is True,
               "first propose should be new")
        expect(registry.propose(conn, "beacon redesign", "project", "doc-fixture-1") is False,
               "case variant re-proposed")
        expect(registry.propose(conn, "Beacon", "project", "doc-fixture-1") is False,
               "shorter variant re-proposed")
        expect(registry.propose(conn, "Atlas Migration", "project", "doc-fixture-1") is False,
               "ratified name proposed")
        expect(registry.propose(conn, "Ghost Project", "project", "doc-fixture-1") is False,
               "rejected name re-proposed")
        n = conn.execute(
            "SELECT COUNT(*) FROM entities WHERE status='proposed'").fetchone()[0]
        expect(n == 1, f"expected exactly 1 proposal, got {n}")
        # provenance recorded via the meeting link
        eid = conn.execute(
            "SELECT entity_id FROM entities WHERE name='Beacon Redesign'").fetchone()[0]
        link = conn.execute(
            "SELECT 1 FROM meeting_entities WHERE doc_id='doc-fixture-1' AND entity_id=?",
            (eid,)).fetchone()
        expect(link is not None, "proposal carries no meeting provenance")

    def c5_checkbox_ratifies():
        registry.write_queue_note(conn, vault)
        note = vault / "Inbox" / "Governance.md"
        text = note.read_text(encoding="utf-8")
        expect("- [ ] **Beacon Redesign**" in text, f"proposal line missing:\n{text}")
        expect("[[2026-01-15 Fixture sync]]" in text, "provenance link missing from queue line")
        note.write_text(
            text.replace("- [ ] **Beacon Redesign**", "- [x] **Beacon Redesign**"),
            encoding="utf-8",
        )
        edits = registry.apply_queue_edits(conn, vault)
        expect(edits["ratified"] == ["Beacon Redesign"], f"got {edits}")
        expect(edits["rejected"] == [], f"got {edits}")
        page = vault / "Projects" / "Beacon Redesign.md"
        expect(page.exists(), "ratified page was not created")
        content = page.read_text(encoding="utf-8")
        expect(content.startswith("---\ncairn-type: project\n"), f"bad template:\n{content}")
        expect("status: active" in content, "project page missing status front matter")
        expect(registry.MARK_BEGIN in content and registry.MARK_END in content,
               "ratified page missing cairn markers")
        expect("[[2026-01-15 Fixture sync]]" in content, "rollup missing meeting link")
        status = conn.execute(
            "SELECT status FROM entities WHERE name='Beacon Redesign'").fetchone()[0]
        expect(status == "ratified", f"status is {status}")
        expect(registry.match(conn, "Beacon", "project") == "Beacon Redesign",
               "newly ratified entity not matchable")
        registry.write_queue_note(conn, vault)  # queue refresh drops the ratified line
        expect("Beacon" not in note.read_text(encoding="utf-8"),
               "ratified proposal still in queue note")

    def c6_deleted_line_rejects_forever():
        registry.propose(conn, "Cobalt Initiative", "project", "doc-fixture-1")
        registry.write_queue_note(conn, vault)
        note = vault / "Inbox" / "Governance.md"
        lines = [l for l in note.read_text(encoding="utf-8").splitlines()
                 if "Cobalt Initiative" not in l]
        note.write_text("\n".join(lines) + "\n", encoding="utf-8")
        edits = registry.apply_queue_edits(conn, vault)
        expect(edits["rejected"] == ["Cobalt Initiative"], f"got {edits}")
        status = conn.execute(
            "SELECT status FROM entities WHERE name='Cobalt Initiative'").fetchone()[0]
        expect(status == "rejected", f"status is {status}")
        expect(registry.propose(conn, "Cobalt Initiative", "project", "doc-fixture-1") is False,
               "rejected name was re-proposed")
        expect(registry.propose(conn, "cobalt", "project", "doc-fixture-1") is False,
               "variant of rejected name was re-proposed")
        registry.write_queue_note(conn, vault)

    def c13_unpublished_proposal_not_rejected():
        # Note is current; a NEW proposal lands after the last write. Its line
        # is absent from the note -- that absence is not a user deletion.
        registry.propose(conn, "Delta Harbor", "project", "doc-fixture-1")
        note = vault / "Inbox" / "Governance.md"
        # simulate an unrelated user edit so the hash fast-path doesn't mask the case
        note.write_text(note.read_text(encoding="utf-8") + "\nA stray user note line.\n",
                        encoding="utf-8")
        edits = registry.apply_queue_edits(conn, vault)
        expect("Delta Harbor" not in edits["rejected"],
               "an unpublished proposal was mistaken for a user deletion")
        status = conn.execute(
            "SELECT status FROM entities WHERE name='Delta Harbor'").fetchone()[0]
        expect(status == "proposed", f"status is {status}")
        registry.write_queue_note(conn, vault)
        expect("- [ ] **Delta Harbor**" in note.read_text(encoding="utf-8"),
               "new proposal missing after queue rewrite")

    # ---- enrichment integration (model stubbed) -----------------------------

    FIXTURE_EXTRACT = {
        "attendees": ["Rowan", "Morgan Fairweather"],
        "projects": ["Atlas", "Quartz Pipeline"],
        "topics": ["Budget Planning", "team offsite!!", "Budget planning"],
        "decisions": ["Fixture decision."],
        "commitments": [], "action_items": [], "open_questions": [],
    }

    def with_stubbed_enrich(fn):
        real_extract, real_vault = enrich.extract, config.VAULT_DIR
        enrich.extract = lambda text: dict(FIXTURE_EXTRACT)
        config.VAULT_DIR = vault
        try:
            return fn()
        finally:
            enrich.extract, config.VAULT_DIR = real_extract, real_vault

    def c7_enrich_links_and_proposes():
        def go():
            src = tmp / "fixture-transcript.md"
            src.write_text("Fixture transcript body. Invented voices only.\n", encoding="utf-8")
            result = enrich.enrich_meeting(
                conn, "doc-fixture-1", src, "2026-01-15 Fixture sync",
                "Fixture transcript body.")
            expect(result is not None, "enrichment returned None")
            expect("Rowan Delacroix" in result["linked_people"],
                   f"ratified attendee not linked: {result}")
            expect("Morgan Fairweather" not in result["linked_people"],
                   "unratified attendee was linked")
            expect("Atlas Migration" in result["linked_projects"],
                   f"ratified project not linked via alias: {result}")
            expect("Quartz Pipeline" not in result["linked_projects"],
                   "unratified project was linked")
            expect(result["topics"] == ["budget-planning", "team-offsite"],
                   f"topic tags wrong: {result['topics']}")
            # proposals recorded for the two unmatched names
            for name, etype in (("Morgan Fairweather", "person"), ("Quartz Pipeline", "project")):
                st = conn.execute(
                    "SELECT status FROM entities WHERE name=? AND type=?",
                    (name, etype)).fetchone()
                expect(st and st[0] == "proposed", f"{name} not proposed (got {st})")
            # the marked block links only ratified names
            block = enrich.build_cairn_block(dict(result, distillation="x"))
            expect("[[Rowan Delacroix]]" in block, "block missing ratified link")
            expect("[[Morgan Fairweather]]" not in block and "Morgan Fairweather" in block,
                   "block linked an unratified name")
            expect("[[Quartz Pipeline]]" not in block and "Quartz Pipeline" in block,
                   "block linked an unratified project")
        with_stubbed_enrich(go)

    def c8_reenrich_idempotent():
        def go():
            before = entity_dump(conn)
            links_before = conn.execute(
                "SELECT COUNT(*) FROM meeting_entities WHERE doc_id='doc-fixture-1'"
            ).fetchone()[0]
            src = tmp / "fixture-transcript.md"
            enrich.enrich_meeting(conn, "doc-fixture-1", src,
                                  "2026-01-15 Fixture sync", "Fixture transcript body.")
            expect(entity_dump(conn) == before,
                   "re-enrichment changed the entities table")
            links_after = conn.execute(
                "SELECT COUNT(*) FROM meeting_entities WHERE doc_id='doc-fixture-1'"
            ).fetchone()[0]
            expect(links_after == links_before,
                   f"meeting links drifted: {links_before} -> {links_after}")
        with_stubbed_enrich(go)

    def c9_proposals_get_no_pages():
        proposed = conn.execute(
            "SELECT name, note_path FROM entities WHERE status='proposed'").fetchall()
        expect(proposed, "expected pending proposals for this case")
        page_stems = {p.stem for p in vault.rglob("*.md")}
        for name, note_path in proposed:
            expect(note_path is None, f"proposal {name!r} carries note_path {note_path!r}")
            expect(name not in page_stems, f"proposal {name!r} has a page")
        # ratified surfaces (Home) must not mention proposals
        def go():
            enrich.regenerate_home(conn)
            home = (vault / "Cairn" / "Home.md").read_text(encoding="utf-8")
            for name, _ in proposed:
                expect(f"[[{name}]]" not in home, f"Home links proposed {name!r}")
            expect("[[Rowan Delacroix]]" in home, "Home missing a ratified person")
        with_stubbed_enrich(go)

    def c10_scan_picks_up_alias_edit():
        page = vault / "People" / "Rowan Delacroix.md"
        # "Wren" shares no substring with the canonical name, so only the
        # alias edit itself (picked up by rescan) can make it match.
        page.write_text(
            page.read_text(encoding="utf-8").replace(
                "aliases: [Rowan]", "aliases: [Rowan, Wren]"),
            encoding="utf-8",
        )
        expect(registry.match(conn, "Wren", "person") is None,
               "alias visible before rescan?!")
        registry.scan_vault(conn, vault)
        expect(registry.match(conn, "Wren", "person") == "Rowan Delacroix",
               "manual alias edit not picked up by scan_vault")

    def c11_rollup_touches_only_marked_block():
        page = vault / "Projects" / "Atlas Migration.md"
        before = page.read_text(encoding="utf-8")
        expect("This body is mine." in before, "fixture body missing")
        registry.regenerate_rollups(conn, vault)
        after = page.read_text(encoding="utf-8")
        expect("This body is mine." in after, "user body was rewritten")
        expect(after.index(registry.MARK_BEGIN) > after.index("This body is mine."),
               "marked block moved above the user body")
        expect("[[2026-01-15 Fixture sync]]" in after, "rollup missing meeting link")
        expect(before.split(registry.MARK_BEGIN)[0] == after.split(registry.MARK_BEGIN)[0],
               "content before the marker changed")

    def c12_migrate():
        mtmp = tmp / "migrate-world"
        mvault = mtmp / "vault"
        for d in ("Cairn/People", "Cairn/Projects", "Inbox"):
            (mvault / d).mkdir(parents=True)
        (mvault / "Cairn" / "Projects" / "Old Generated.md").write_text(
            "---\ngenerated: true\n---\n# Old Generated\n", encoding="utf-8")
        (mvault / "Cairn" / "People" / "Old Person.md").write_text(
            "---\ngenerated: true\n---\n# Old Person\n", encoding="utf-8")
        mconn = sqlite3.connect(mtmp / "m.db")
        mconn.execute("PRAGMA foreign_keys = ON")
        dbmod.init_db(mconn)
        mconn.execute(
            "INSERT INTO entities (entity_id, name, type, aliases, note_path) "
            "VALUES ('e1','Old Generated','project','[]', ?)",
            (str(mvault / "Cairn" / "Projects" / "Old Generated.md"),))
        mconn.execute(
            "INSERT INTO entities (entity_id, name, type, aliases) "
            "VALUES ('e2','Old Person','person','[]')")
        mconn.commit()
        summary = registry.migrate(mconn, mvault)
        expect(summary["proposed"] == 2, f"got {summary}")
        expect(summary["pages_deleted"] == 2, f"got {summary}")
        statuses = {r[0] for r in mconn.execute("SELECT status FROM entities")}
        expect(statuses == {"proposed"}, f"post-migrate statuses {statuses}")
        expect(not (mvault / "Cairn" / "Projects" / "Old Generated.md").exists(),
               "generated project page survived migrate")
        note = mvault / "Inbox" / "Governance.md"
        expect(note.exists(), "migrate wrote no queue note")
        text = note.read_text(encoding="utf-8")
        expect("- [ ] **Old Generated**" in text and "- [ ] **Old Person**" in text,
               f"queue note incomplete:\n{text}")
        mconn.close()

    check("1. scan_vault builds the ratified index from pages", c1_scan_builds_index)
    check("2. match: exact/alias/case/variants, never inserts", c2_match_semantics_read_only)
    check("3. match sees ratified entities only", c3_match_ratified_only)
    check("4. propose dedupes and respects rejected", c4_propose_dedupe_and_rejected)
    check("5. checked box ratifies: page + status + rollup", c5_checkbox_ratifies)
    check("6. deleted line rejects permanently", c6_deleted_line_rejects_forever)
    check("7. enrichment links ratified, proposes rest, tags topics", c7_enrich_links_and_proposes)
    check("8. re-enrichment is idempotent", c8_reenrich_idempotent)
    check("9. proposals get no pages and stay off Home", c9_proposals_get_no_pages)
    check("10. scan_vault picks up a manual alias edit", c10_scan_picks_up_alias_edit)
    check("11. rollup rewrites only the marked block", c11_rollup_touches_only_marked_block)
    check("12. --migrate demotes, deletes, writes the queue", c12_migrate)
    def c14_rename_then_check_ratifies_under_edited_name():
        # "Delta Harbor" is pending from case 13. The user fixes the name on
        # the line, then checks the box: the edited name wins as canonical,
        # and the rename is NOT mistaken for a deletion.
        note = vault / "Inbox" / "Governance.md"
        text = note.read_text(encoding="utf-8")
        expect("- [ ] **Delta Harbor**" in text, "expected Delta Harbor pending")
        note.write_text(
            text.replace("- [ ] **Delta Harbor**", "- [x] **Delta Harbor Revamp**"),
            encoding="utf-8",
        )
        edits = registry.apply_queue_edits(conn, vault)
        expect(edits["ratified"] == ["Delta Harbor Revamp"], f"got {edits}")
        expect(edits["rejected"] == [], f"rename treated as deletion: {edits}")
        expect((vault / "Projects" / "Delta Harbor Revamp.md").exists(),
               "page not created under the edited name")
        expect(registry.match(conn, "Delta Harbor", "project") == "Delta Harbor Revamp",
               "old form does not resolve to the edited canonical name")

    check("13. unpublished proposal is not a user deletion", c13_unpublished_proposal_not_rejected)
    check("14. renamed line ratifies under the edited name", c14_rename_then_check_ratifies_under_edited_name)

    conn.close()


def main():
    tmp = Path(tempfile.mkdtemp(prefix="cairn-test-registry-"))
    # These cases propose, ratify and reject for real. Redirect the governance
    # event log into the temp directory so a test run never inflates the
    # ratification-burden numbers measured from the real one.
    registry.GOVERNANCE_LOG = tmp / "governance.csv"
    try:
        run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("=" * 40)
    print(f"{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()

# MVP and Beta Plan — 2026-09-02

*Planned on the owner's ruling of 2026-09-02: "we're close enough — plan an MVP
and move to beta testing; that feedback shapes forward momentum." Approach:
staged, owner-first. The owner dogfooding two real deployments produces
feedback in days; the work deployment is a second machine, so the install story
external testers would need gets built and proven on the way, never
speculatively.*

## The MVP cut

**In** (exists today unless marked *build*):

- **Import** — drop a file in `sources/`, the watcher converts, enriches,
  embeds; entity links against the ratified registry only.
- **Onboard** — `/interview` in plugin chat with a playbook lens
  (*build: executive lens*), playback-confirm ratification seeding
  `Profile.md` and the registry.
- **Distill** — decisions, commitments, actions, questions to `Inbox/` drafts,
  never embedded until ratified (*build: affect prohibition in the distillation
  prompt, with a gate*).
- **Govern** — the checkbox queue note; burden logged.
- **Ask** — grounded, cited answers with vault links, refusal floor, strength
  labels.
- **Maintain** — `/checkin`.

**Out**, deliberately: Generate (Horizon 2 — beta feedback should confirm its
priority, not preempt it); connectors beyond file-drop; the worker and personal
lenses; connection surfacing (withdrawn 2026-08-29); protocol multi-turn;
packaging polish beyond what the second machine actually needs.

## Phases and checkpoints

### Phase 0 — Housekeeping (one sitting) — **complete 2026-09-02/03**

1. ~~Commit the pending registry bugfix and the 2026-09-02 ratification edits,
   with the standing manual sensitive-term review.~~ **Done.**
2. ~~Restart the engine and watcher (both currently down).~~ **Done** — engine
   and watcher both up.
3. ~~Create a **private** remote and push `main`.~~ **Done, but publicly, not
   privately — this plan was overridden and the override is recorded here
   rather than absorbed silently.** The repository is public at
   `github.com/jk-maxwell/cairn`. The reason is Phase 2: Cairn is being
   installed on a **government work computer**, and on that machine an opaque
   personal binary pulled from a private URL is not installable, whereas
   auditable open source is. Being readable by the reviewer is what makes the
   second deployment possible at all — so publishing is not a departure from
   the plan's goal, it is a precondition of the plan's own Phase 2. The ruling
   itself is recorded in DECISIONS 2026-09-02, which also amends ROADMAP
   section 7.

   What protected people still held: the sensitive-term sweep covered **full
   history**, not just current files; the one real leak it found (the owner's
   absolute machine path in a smoke-test report) was removed by rewriting
   history while no remote existed; and `backup-pre-scrub` was never pushed and
   remains local-only. What was given up is optionality — a public repository
   can be cloned and cached within minutes, so the Horizon 3 integrity work now
   happens under observation rather than before it.

### Phase 1 — Personal deployment live

1. **Affect prohibition** — **done** (`enrich.py`, gate
   `t_distillation_no_affect`, fixture
   `tests/fixtures/affect-bait-transcript.md`; 29 gates total). In the
   distillation prompt plus a negative selftest gate: a checked-in fixture transcript baited with tone and assessments of
   individuals must yield drafts containing none of it. Prompt and gate
   redundant by doctrine. Lands before daily real distillation, because beta
   means real meetings about real colleagues. Implemented unconditionally —
   consistent with unratified proposal 6, which only adds the warned opt-out.
2. **Executive playbook** — *in progress, the last build item before
   checkpoint 1*: lens as data (questions + relationship vocabulary: mentor,
   advisor, investor, counterpart), lens choice as the interview's optional
   first question, persisted as `cairn-playbook` in `Profile.md`.
   Scope ruling: the lens drives the **interview only** for MVP;
   relation-proposals-from-enrichment is a fast-follow once daily use shows
   what relations actually come up.

   **Singleton ruling (owner, 2026-09-03):** *"When you run a playbook, you
   commit to it. Cairn can at most hold one playbook at a time."* One active
   playbook per deployment, not per profile and not per interview — which is
   what makes the two deployments a real test in Phase 2 rather than a
   configuration toggle: the work machine commits to the government lens, the
   personal machine to the executive one, and neither can quietly drift into
   the other. Switching an already-committed playbook is therefore never
   silent; it requires explicit confirmation and is logged.
3. **Two ownership defects, confirmed then fixed** — **done** (commit
   `2be3733`; rejections now survive a rebuild, and a deleted rollup stays
   deleted). Both were found on
   2026-08-29 and neither is cosmetic in a beta the owner lives inside.
   *Rejection permanence*: `reject()` writes only to the database, and a
   rejected entity has no vault page by definition, so dropping `cairn.db`
   and rebuilding from the vault resurrects every rejection ever made — which
   contradicts RATIONALE 8.4's promise that the vault alone gives the same
   answers, and silently re-inflates the same burden dial the adaptation
   triggers read. The drop-and-rebuild was never actually executed, so this is
   confirmed first and fixed second; if the rebuild turns out to preserve
   rejections, the finding is retracted rather than patched around.
   *A deleted rollup block did not stay deleted*: the second defect was
   narrower than first filed and one half of it was not real. `registry.py`'s
   ownership contract does not say machine contributions live in front matter
   alone -- that was a paraphrase -- it explicitly carves out "the single block
   between the cairn markers", so `_rollup_body` writing into the body is
   sanctioned, not a contradiction. What was real is worse: the block was
   re-appended after the owner deleted the markers, so deleting the machine's
   section from your own page did not stick.
   Daily use is precisely when the owner starts editing their own pages, so a
   machine that overwrites them is a trust failure in week one, not a latent
   bug. Both land before checkpoint 1, because the interview itself proposes,
   ratifies and rejects.
4. **Checkpoint 1 (owner)**: run `/interview` for real on the personal
   deployment. Pass = `Profile.md` and the seeded registry match what was
   said, playback felt usable, no hand-editing needed afterward. The script
   has never met a real user; everything learned is feedback item #1.
5. Daily use begins: transcripts as they occur, queue worked, real questions
   asked. The three dials start accumulating real data.

### Phase 2 — Work deployment (overlaps Phase 1's daily use)

0. **De-risk first, in parallel with Phase 1**: verify the work machine can
   run the stack at all (Python, a local model runtime, Obsidian, install
   rights, network policy). If not, pivot: two deployments on the personal
   machine, packaging off the critical path.
1. Ratification pass on remaining proposals (#4 gates this phase; #1, #2, #6
   are cheap in the same sitting).
2. **Entity-types-as-data**: the three hardcoded sites (folder map, queue
   parser, vault scan) driven from one declaration, gated by a
   type-added-in-one-place-works-everywhere test.
3. `organization` + `role` types, `parent:` wikilink containment, shared
   `relationship:` property.
4. **Government lens**: position and remit, org and parent chain, counterpart
   divisions, standing programmes vs initiatives, roles then holders, domain
   vocabulary; empty relationship vocabulary by design.
5. **Install story, proven by doing the real second install** from the public
   remote: setup script, start/stop wrapper replacing raw `nohup`, plugin
   steps — written up as the quickstart doc while doing it.
6. **Checkpoint 2 (owner)**: onboard the work deployment with the government
   lens. Pass criteria as checkpoint 1, plus: the seeded org chart matches how
   the owner actually thinks about the workplace — the first live test that
   government and executive are genuinely distinct lenses.

### Phase 3 — External cohort (optional; gated on checkpoints 1–2 and sane dials)

1. Verify the fully-local default path end to end (the grounding prompt was
   tuned against the remote generation model only; budget a re-tune that keeps
   both paths green).
2. Quickstart finalized from the real Phase 2 install notes, plus the privacy
   story in plain words.
3. Two to five friendly testers, fully-local defaults, own vaults. Feedback is
   a weekly conversation, not tooling.

## Beta protocol

28 days of real use, clock starting at checkpoint 1. Weekly ~30-minute review:
read the dials, note friction, pick the next week's single most valuable fix.

The dials are already ratified and instrumented; the beta adopts them:

- **Habit** — opened and asked on most working days?
- **Capability** — each week, one question answered that couldn't be the week
  before. Two dry weeks means ingestion breadth is the bottleneck, not model
  quality.
- **Burden** — `governance.csv` arrival vs drain, queue depth, decision
  latency. The abandonment predictor.

**Adaptation triggers, fixed in advance:**

- Burden arrival exceeds drain two consecutive weeks → stop feature work, fix
  extraction precision until the queue drains.
- Habit failing by week 2 → the review becomes a why-conversation; the likely
  answer re-prioritizes Generate ("Ask alone earns permissions, not desires").
  Named now as the single most probable headline of this beta.
- Checkpoint failure → fix the interview before daily use; a bad first
  onboarding poisons the registry the whole beta runs on.
- Work-machine install blocked → the Phase 2.0 pivot, recorded.

**Exit criteria** — done and succeeded when: 28 days elapsed; both deployments
onboarded and in weekly use (or the pivot recorded); habit and capability green
in 3 of 4 weekly reviews; burden drain ≥ arrival over the final 14 days; **no
failure went unannounced** (see below); and a written post-beta findings note
ranking the next horizon by observed evidence. **That note, not this plan, decides what
gets built next.**

*Amended 2026-09-03.* This criterion previously read "zero silent failures
observed", which could not be met or missed on purpose: a silent failure is
exactly the case where "nothing happened" and "nothing was supposed to happen"
look identical from outside, so watching harder never finds one. It is now
measured against the instrumentation built to make the distinction possible —
an ingest receipt per file, a watcher heartbeat that separates *idle* from
*busy* from *dead* from *stopped on purpose*, and `Cairn/Health.md` reporting
both in the vault, which is the one surface the habit dial guarantees gets
opened. Concretely, over the final 14 days: **no receipt outstanding more than
24h without appearing on the health note; and every failure that did occur was
visible there before the owner noticed the symptom.** The test is not that
nothing broke — across 28 days of real use something will — but that nothing
broke *quietly*. Not exit criteria: tester count, Generate shipped, model
quality.

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

### Phase 0 — Housekeeping (one sitting)

1. Commit the pending registry bugfix and the 2026-09-02 ratification edits,
   with the standing manual sensitive-term review.
2. Restart the engine and watcher (both currently down).
3. Create a **private** remote and push `main` — owner confirmation required.
   First time the repo ever leaves the machine, so the sensitive sweep covers
   **full history**, not just current files, and the `backup-pre-scrub` branch
   is never pushed. A dirty history blocks the remote until rewritten clean.

### Phase 1 — Personal deployment live

1. **Affect prohibition** in the distillation prompt plus a negative selftest
   gate: a checked-in fixture transcript baited with tone and assessments of
   individuals must yield drafts containing none of it. Prompt and gate
   redundant by doctrine. Lands before daily real distillation, because beta
   means real meetings about real colleagues. Implemented unconditionally —
   consistent with unratified proposal 6, which only adds the warned opt-out.
2. **Executive playbook**: lens as data (questions + relationship vocabulary:
   mentor, advisor, investor, counterpart), lens choice as the interview's
   optional first question, persisted as `cairn-playbook` in `Profile.md`.
   Scope ruling: the lens drives the **interview only** for MVP;
   relation-proposals-from-enrichment is a fast-follow once daily use shows
   what relations actually come up.
3. **Two ownership defects, confirmed then fixed.** Both were found on
   2026-08-29 and neither is cosmetic in a beta the owner lives inside.
   *Rejection permanence*: `reject()` writes only to the database, and a
   rejected entity has no vault page by definition, so dropping `cairn.db`
   and rebuilding from the vault resurrects every rejection ever made — which
   contradicts RATIONALE 8.4's promise that the vault alone gives the same
   answers, and silently re-inflates the same burden dial the adaptation
   triggers read. The drop-and-rebuild was never actually executed, so this is
   confirmed first and fixed second; if the rebuild turns out to preserve
   rejections, the finding is retracted rather than patched around.
   *Rollup writes to the body*: `registry.py` promises the ratified page body
   is never rewritten and that machine contributions live in front matter
   alone, but `_rollup_body` writes a `## Meetings` section into the body and
   `_replace_marked_block` re-appends it after the owner deletes the markers.
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
5. **Install story, proven by doing the real second install** from the private
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
in 3 of 4 weekly reviews; burden drain ≥ arrival over the final 14 days; zero
silent failures observed; and a written post-beta findings note ranking the
next horizon by observed evidence. **That note, not this plan, decides what
gets built next.** Not exit criteria: tester count, Generate shipped, model
quality.

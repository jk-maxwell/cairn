# Cairn Technical Roadmap

**Draft 2. Numbered for markup.**

*The technical companion to ROADMAP.md Horizon 1, told from the user's chair. Draft 2 restructures draft 1 on review: the journeys lead, the checkpoints are defined by what the user can do and will accept, and the technology follows as the thing that makes those checkpoints honest. Product decisions are cited, never restated.*

---

## 1. What this document is

A build plan that starts where the product starts: a person in Obsidian with a question. Each checkpoint below is a moment that person gains something real, stated with the acceptance criteria they would actually apply. The technology sections after them exist to serve the checkpoints and for no other reason. Nothing here ships because the code is done; it ships because a journey got shorter.

## 2. The journeys are the spine

The four ratified journeys: **Ask** (a question to a cited answer or an honest refusal), **Capture** (something arrives and gets its cut), **Ratify** (inbox to memory or task), **Wake** (the morning open: what changed, what dreamed, what is proposed).

Horizon 1 builds Ask end to end. Capture and Ratify open with Horizon 2, Wake completes with Horizon 3, and their checkpoints are named here so the destination is visible, but this document plans only the road to Ask.

## 3. Checkpoint 0, week one: ask the real vault today

**What the user can do.** Open an existing chat plugin inside Obsidian, pointed at the reference engine, and ask the real vault real questions. The chrome is borrowed and rough; the answers, receipts, and refusals are real.

**What the user accepts.** This is not the product and is not judged as one. It is judged as an experiment on the biggest open risk, the habit: does the author actually reach for it. The evidence is the receipt log, and the bar is the ratified one: real questions on most working days. Silence is a finding, not a failure of the checkpoint; it is exactly what the probe exists to detect early, while the surface is still cheap to change.

**What it costs.** Configuration only. The reference engine already serves the protocol both plugin dialects speak.

## 4. Checkpoint 1: drive the real surface

**What the user can do.** Open the ratified Ask surface, the right sidebar at its 300 default, and drive it: watch answers stream at true recorded speed with real pauses, click citations and land in the cited note, read confidence chips kept visually apart from provenance stamps, stop a stream and keep the partial marked stopped, hit the bare refusal, the on-topic-but-silent case, and the bad days, engine down, model missing, stream dying mid-answer. Every one of the ten palette commands works. Every move in Plate K's table works.

**What the user is NOT getting yet.** Real answers. Everything is replayed from recordings; the data is synthetic and says so on its face.

**What the user accepts.** The wireframes' own bar, applied to a living surface: if Ask does not feel simple here, the plugin has failed at the cheapest possible place to fail, and the surface gets rethought before any engine is ported. Acceptance is the watched walkthrough: the Ask journey plates (B, D, E) and all 24 movement rows, each row observed to pass, failures logged to the ledger. Feel is a first-class criterion at this checkpoint, and the recordings carry real token timing precisely so feel can be judged honestly.

## 5. Checkpoint 2, the MVP: the vault answers

**What the user can do.** Type a question about their own vault into the surface they already trust from Checkpoint 1, and get a cited answer, with a receipt, or an honest refusal, live, on their machine, with nothing leaving it.

**What the user accepts as MVP.** The ratified exit gate, which is a user's bar and not an engineer's: after two weeks of daily use, the receipt log shows real questions on most working days, and the user can name three answers that beat the old way of finding out. The log can show silence, and silence is the gate failing. Behind that sits the mechanical half of the gate: every ported gate, parity gate, the injection gate, and the rebuild gate green, and the Checkpoint 1 walkthrough repeated on the live engine with zero behavior differences. The user should be unable to tell the swap happened except that the answers are now about their life.

## 6. Later checkpoints, named now, built later

1. **Checkpoint 3, the desk flows in** (Horizon 2): drop an email, a calendar export, a transcript; watch it arrive with its cut or get asked one question in the inbox; ratify a commitment into a task. Capture and Ratify become real. The user's bar is already ratified: the three founding pain stories answered from imported content with receipts, and an inbox that stays near zero cost instead of becoming a guilt pile.
2. **Checkpoint 4, the morning open** (Horizon 3): the Wake journey. Open Obsidian in the morning to what changed, what dreamed, what is proposed, under a journal where one step reverts a night. The user's bar: thirty days of dreaming with zero rewrites of personal content and at least one accepted proposal a week.
3. Each gets its own technical document when its horizon opens. They appear here so no Checkpoint 1 or 2 decision quietly forecloses them.

## 7. The reference engine's role, stated plainly

The Python engine is reference only. It is never shipped, never extended, and no work package below is about improving it. It serves exactly three purposes and then retires to the archive:

1. **The probe's temporary backend** (Checkpoint 0), because it already answers real questions today.
2. **The source of the recordings** (Checkpoint 1), because the fixtures must carry the real contract, real receipts, real refusals, real token timing, not an invented mock.
3. **The parity standard** (Checkpoint 2), because a port proven byte-equal to a working engine needs no leap of faith.

It gets one touch: before recording, its known receipt defect (the truncated strength line) is corrected, minutes of work, with a gate asserting the whole sentence. Not because the legacy code deserves investment, but because recordings taken from a defective reference would make the defect the spec the new surface is built against. The fix is a precondition of recording, not a work package of the product.

## 8. The technical shape, serving the checkpoints

**8.1 Repository.** One npm workspace in this repository: `contracts/` (types, prompt templates, chunking spec, the single home of every cross-implementation fact), `engine/` (pure TypeScript, zero Obsidian imports), `plugin/` (the shell, importing only the engine's public interface), `fixtures/` (recordings plus the frozen synthetic corpus), `gates/` (everything runnable headless). The import rules are enforced by a lint gate. The reference engine stays at the root, frozen.

**8.2 The swap boundary.** One interface in `contracts/`: `ask(question)` returning a stream of token, receipt, done, and error events; the receipt carries citations that name how each passage was found, the full strength sentence, confidence, and dates. The fixture player implements it for Checkpoint 1; the ported engine implements it for Checkpoint 2; the shell never learns which is answering. The types freeze when the player lands; any later change reopens the Checkpoint 1 review. This freeze is what makes the swap invisible to the user, which is Checkpoint 2's acceptance.

**8.3 Recordings.** A small recorder captures the reference engine's streaming output as JSONL: a header pinning question, corpus hash, engine and Ollama versions, and exact model tags; then timestamped events. The scenario set covers every contract case the user will feel: clean, weak, flagged, bare refusal, on-topic-but-silent, front-door lanes, phantom-citation warning, stopped stream, and the failure family (engine unreachable, model missing, stream interrupted). The player replays on the recorded clock, fast for tests, real-time for judging feel.

**8.4 Storage.** No native modules can ship in a plugin, so sqlite does not port. The derived store is plain files in the plugin's data directory: a JSON content index (per file: hash, cut, source, snapshot date, processing state) and a binary embeddings store. It updates incrementally from the ratified arrival-time work queue, and the rebuild gate keeps it disposable: drop it all, rebuild from the vault alone, get the same answers. The same disposability is what makes the whole-corpus redream on a better model a rebuild, not a migration.

**8.5 Talking to Ollama.** The engine takes an injected transport. Desktop streaming uses Node's built-in `http` module, available to plugins with no native dependency; plain browser fetch hits Ollama's CORS wall and Obsidian's `requestUrl` cannot stream, so neither is the default; `requestUrl` non-streaming remains the degraded fallback so a locked-down machine gets slower answers, never none. The status item surfaces preflight state, and the failure recordings define what the user sees on a bad day.

**8.6 Parity, three layers, each a gate.** Chunking: the TypeScript chunker's output over the frozen corpus, hash-compared to the reference's manifest, byte-identical or failing. Retrieval: both implementations against the same Ollama on the same machine with pinned tags; the gate asserts ranked citation lists match and prints margins on near-ties; divergence is a stop, the ratified kill criterion. Answers: identical passages, byte-identical prompts from the shared templates, cold models; golden-answer diffs of whole strings, receipt included. Goldens are frozen per corpus, model tags, and Ollama version, all asserted at gate time; changing any means re-freezing from the reference, which the recorder makes cheap.

**8.7 Testing, honestly split.** Engine and gates run headless in vitest (`npm run gates`; `npm run gates:fast` pre-commit; `npm run bench` for the thousand-note indexing benchmark). Plugin view logic is plain functions over a thin interface of Obsidian primitives, unit-tested without Electron. The journeys themselves are watched walkthroughs generated from the ledger's ratified rows, every test written to be watched and failed. Automated Electron driving is deferred until the first regression a walkthrough misses.

## 9. Work packages, grouped by the checkpoint they serve

**Checkpoint 0:**
- **P1, the probe.** Point an existing chat plugin at the reference engine on the real vault. Configuration only. Acceptance: the receipt log exists and is being written.

**Checkpoint 1:**
- **P2, recordings.** Correct the reference's receipt line (the section 7 precondition, with its whole-sentence gate), then record the full scenario set. Acceptance: fixtures replay deterministically twice.
- **P3, contracts and player.** The types, templates, and chunking spec; the player behind the interface; a golden test proving the player emits exactly the recorded receipt. Acceptance: every scenario replays type-clean; the freeze is declared.
- **P4, the shell.** Plugin scaffold, settings tab (endpoint, model tags, scope), the Ask view with everything Checkpoint 1 promises the user, ten commands, status item. Acceptance: the Checkpoint 1 watched walkthrough.

**Checkpoint 2:**
- **P5, convention and index.** The metadata convention as a short reviewed design document before anything reads it; then the content index, embeddings store, and queue-driven updates. Acceptance: the rebuild gate.
- **P6, the port.** In `engine/`: chunker, transport client, retrieval, receipts and refusal, front door, in that order. Acceptance: the ported gate suite plus all three parity layers.
- **P7, the swap.** The shell onto the live engine. The evidence-not-instructions gate lands here, before any importer exists, and it is concrete: a fixture vault holds an attacker-authored note whose text is instructions to ignore the rules and answer from memory; the gate asserts the answer treats that text as evidence only, citations intact. Acceptance: Checkpoint 2's user bar and mechanical bar together.

## 10. Risks, named

1. **The surface fails the feel test at Checkpoint 1.** By design the cheapest failure in the plan; the answer is surface rework, not more engine.
2. **Streaming from inside Obsidian.** Held by the transport design and by the player, which makes streaming behavior testable with no network at all.
3. **Parity drift.** Held by the three gates of 8.6 and the pinned versions in every recording header; any divergence stops the line.
4. **Contract drift after the freeze.** Held by the freeze rule and the lint gate; changes reopen the Checkpoint 1 review.
5. **Windows behavior.** Held by the path-normalization rule in the contracts and Windows-path gate cases; the cross-platform promise rides in gates, not intentions.

## 11. What this document does not cover

Connector implementations, dream-mode internals, importer formats, and the mechanics of Checkpoints 3 and 4. Each arrives with its own technical document when its horizon opens, reviewed the same way this one is.

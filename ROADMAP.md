# Cairn Roadmap

*From a ratified thesis to a tool that earns its daily open.*

Cairn turns [Obsidian](https://obsidian.md) into a private working memory for one person. The full product definition, ratified after five rounds of review, is [docs/THESIS.md](docs/THESIS.md). This roadmap sequences the work of building it, and it is written against evidence: every number below was measured, not estimated, and every horizon ends at a gate that can fail.

---

## 1. What is true today

A ratified product thesis. Fourteen sections defining the vault as the hub, the personal and reflection content cut, five capabilities (Import, Ask, Distill, Generate, Dream), ratification as the gate into memory, and a connector layer built on a data contract rather than a code contract.

A working reference implementation. The Python engine from the proof-of-concept phase: grounded retrieval with a receipt on every answer, refusal when the corpus does not contain the answer, a deterministic front door that answers without a model call, a protocol surface any OpenAI-compatible or Ollama-compatible chat client can use, and 20 gates green on two operating systems. On capable hardware a real question answers in 1.2 seconds end to end.

A ratified drawing set. Twelve plates in [docs/WIREFRAMES.html](docs/WIREFRAMES.html) covering every screen, the whole-app layout, and a 24-row movement table (Plate K) that is the navigation spec, landed through four rounds of numbered review.

Zero lines of plugin code. The product the thesis describes is not built. Between those two sentences sits this entire document.

One known defect. In the reference engine's shared answer path, the retrieval-strength description is overwritten before the receipt is assembled, truncating the strength line on clean answers and doubling the warning on flagged ones. It matters more now than when it was found, for a reason named in Horizon 1.

## 2. The shape of the work

The order below is dependency, not preference.

**The surface leads** because it holds the open risk. The engine is the proven part, so building it first proves nothing new, while five capabilities packed into one surface is where the product can still fail. The sequence is the inversion argued in [docs/RATIONALE.md](docs/RATIONALE.md) section 10: land the UX as a reviewable drawing set, build a drivable shell over fixtures recorded from the reference engine, then swap the real backend in behind a stable interface, capability by capability, Ask first.

**The convention leads the backend track** because it is the public interface of everything the engine touches. The frontmatter contract, which cut, what source, what snapshot date, what provenance, gets read by the index, the importers, the receipts, and the dreaming rules. Designing it late means migrating a live vault.

**The probe runs in parallel** because the biggest risk is not technical. The prototype proved the engine; nothing yet proves the habit, and fixtures can validate comprehension but not the habit. An existing chat plugin pointed at the reference engine's endpoint, on a real vault, answers the question "does the author actually reach for this inside Obsidian" in days, alongside the shell work rather than after it.

**Dreaming ships last** because it is the only capability that acts while nobody watches. It goes behind the journal, the one-step revert, and the content cut, all proven in daylight first.

**The gates are the spec.** The engine logic lives in plain TypeScript, separate from the plugin's interface layer, so the ported gate suite runs headless in continuous integration. The rewrite is done when the ported gates go green, and no gate counts until it has been seen to fail.

## 3. Horizon 1: the vault answers

**The outcome.** A question typed in Obsidian gets a cited answer from the vault, with a receipt, or an honest refusal.

**The work: two tracks worked separately, a probe alongside, a swap at the end.**

The surface track, in order.

1. **The drawing set**, landed: twelve plates ratified through four rounds of numbered review, with Plate K's movement table as the navigation spec.
2. **Fixtures recorded from a corrected reference.** First fix the receipt defect in the reference engine, with a gate asserting the whole strength sentence, because fixtures frozen from a defective reference make the defect the spec. Then record fixtures from the reference engine on the synthetic corpus, carrying real token timing, so the shell is designed against streaming, pauses, and refusals rather than instant answers from a world that does not exist.
3. **The drivable shell, Ask first**: the plugin walking Plates B, D, E, and K against the fixtures. Plate K's table is the acceptance list, and every journey test in the drawing set is written to be watched and failed.

The backend track, in order.

4. **The metadata convention**, drafted as a short design document and reviewed before anything reads it.
5. **The TypeScript engine port**: heading-aware chunking, embeddings over Ollama HTTP, retrieval, receipts, refusal, front door. Acceptance is the ported gate suite plus golden-answer parity gates against the reference on a frozen corpus. Cold models make byte-comparable output a fair standard, so divergence is a failing gate, not a judgment call.
6. **The content index**: per file, its hash, cut, source, snapshot date, and processing state. With it, the rebuild gate: drop every derived store, rebuild from the vault alone, get the same answers.

**The probe**, in week one and in parallel with both tracks: an existing chat plugin against the reference engine on a real vault. The fixtures can validate comprehension but not the habit; the habit forms around real answers or not at all, and its finding shapes the Ask surface while the shell is still cheap to change.

**The swap.** The shell moves from fixtures to the ported engine behind the interface the fixtures froze, Ask first. The evidence-not-instructions gate lands here, before any importer exists, so the defense precedes the first attacker-authored content. Any behavior difference between the shell on fixtures and the shell on the engine is a failing gate, not a judgment call.

**Exit gate, two parts, both able to fail.**

- Ported gates, parity gates, injection gate, and rebuild gate all green in continuous integration, and the shell's journey tests passing against the real engine.
- After two weeks on a real vault, the receipt log shows real questions asked on most working days, and the author can name three answers that beat the old way of finding out. The log can show silence. Silence is the gate failing.

## 4. Horizon 2: the desk flows in

**The outcome.** Email, calendar, meeting notes, documents, spreadsheets, and diagrams land in the vault through deliberate import, and what they carry becomes decisions, commitments, and tasks through ratification.

**The work.**

1. **The import floor**: file drop, .eml, .ics, and document conversion, each arrival carrying convention frontmatter, originals kept as artifacts. Standard formats before any platform automation, so every capability works on every machine from day one.
2. **The review inbox**, the first ratification surface. Unclassified arrivals come here for their cut assignment; nothing meaning-bearing enters memory except through it.
3. **Distill**, feeding the inbox: decisions, commitments, action items, open questions. Facts only, never affect, tone, or assessments of individuals.
4. **Generate, in-vault**: tasks in the ecosystem's standard syntax and drafted briefs. Cairn proposes priority and never sets it.
5. **Diagram ingestion**: locally generated descriptions so process maps and SOPs become findable and citable, originals untouched.

**Exit gate.** The three founding pain stories, answered from imported content with receipts: a past decision retrieved from meeting notes; the current version of a policy from reflections, snapshot date visible; a commitment surfaced, ratified, and standing as a task. Plus inbox health, measured: ratification stays near zero cost and the inbox does not accumulate. A guilt pile is the gate failing.

## 5. Horizon 3: it works while you don't

**The outcome.** The vault improves itself under the journal, drafts cross the boundary to other systems but never send themselves, and the whole build is verifiable.

**The work.**

1. **Dream mode**: idle-triggered inside Obsidian, chunked and interruptible, every change journaled, one step reverts a night's work. No OS services, ever.
2. **Cross-boundary generation**: calendar events, messages, and email as drafts, staged after ratification into the other system's own drafting area by user-steered automation. Sending stays human, always.
3. **Platform connectors**: the COM proof of concept landing scrubbed, genericized, and gated, then its AppleScript sibling. The connector interface is designed before the proof of concept lands, so the code conforms to the product and not the reverse.
4. **Integrity completion**: reproducible hash-verifiable builds, self-check at load, and the security posture of thesis section 12 checkable end to end.

**Exit gate.** Thirty days of dreaming with a journal audit showing zero rewrites of personal content and at least one accepted dream proposal a week; one staged draft used in real correspondence; the full rebuild still identical. Thirty days is deliberate: trust in an unwatched capability is earned slowly or not at all.

## 6. What can kill this, and when we stop

Kill criteria are decisions already made, not warnings.

1. **The habit never forms.** If the Horizon 1 usage gate fails twice with the engine healthy, building stops and the surface gets rethought. More features cannot fix an unopened door.
2. **The port diverges.** Any parity failure against the reference is a stop, investigated to root cause. A retrieval engine that is almost the reference is not the reference.
3. **The inbox becomes a chore.** If ratification cost stays high after redesign, the human-in-the-loop model itself gets revisited, because a loop everyone bypasses protects no one.
4. **Dreaming touches what it must not.** A single rewrite of personal content in the audit is a stop, full revert, and redesign. There is no acceptable rate of this defect except zero.

Two risks are held by ordering rather than by gates: injection defense lands before the first importer, and performance work waits for a realistic benchmark before touching code, a lesson this project has already paid for once.

## 7. Beyond the horizons

**Graduation.** Action classes earning promotion from asked-every-time to journaled, on the evidence of the accumulated journal. Designed future state, deliberately after the journal has months of record to design from.

**Publishing.** Making the repository public is a one-way door and is not scheduled by any horizon. The integrity work of Horizon 3 is its precondition, not its trigger, and the sensitive-term scan runs before any push regardless.

**The promises are not on this roadmap** because they are not work items. Nothing leaves the machine; it ingests only what you point it at; it never speaks for you. They hold at every horizon, and any work item that would bend one is out of scope by construction.

---

## How this roadmap works

Horizons are sequential, and each one ends at a gate that can fail. A failed gate stops the horizon from rolling forward, full stop. Work inside a horizon is ordered but negotiable. Anything unmeasured is a hypothesis, and anything measured beats an opinion about it.

The weekly question stays the one the project started with: **can Cairn answer something today that it could not answer last week.**

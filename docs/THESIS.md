# Cairn Product Thesis

**Draft 7. Numbered for markup. Supersedes docs/DESIGN.md draft 1.**

Changes from draft 6, the work-queue amendment, ratified 2026-08-21: section 9 retitled and opened with the arrival-time work queue, dreaming recast as its idle drain and Dream now as the blocking on-demand drain; one-sentence touches in sections 2 and 6 for consistency. No sections renumbered.

---

## 1. The thesis

Cairn turns Obsidian into a private working memory for one person.

Everything that crosses your desk lands in one local vault as plain text: email, calendar, meeting notes, personal notes, documents, spreadsheets, process maps. A plugin imports it, answers questions over it with a citation for every claim, distills working content into decisions, commitments, and action items, drafts what comes next in the form of tasks, events, messages, and briefs, and improves the vault while you are away.

The machine drafts, the human ratifies, and ratification is what turns output into memory. Models and infrastructure are commodity. The product is the connected corpus and the discipline applied to it.

## 2. Two kinds of content, cut cleanly

Every piece of source content in the vault is one of two kinds, and the cut is enforced, not advisory.

**Personal.** Yours. Email, calendar, personal notes, meeting notes, drafts, local files never published. The vault is where this content lives. It is current, precious, and irreplaceable.

**Reflection.** The organization's, or the world's. Timestamped snapshots of shared drives, intranet platforms, published policies, references, SOPs. The source of truth lies elsewhere; the vault holds an extraction taken at a known moment. Reflections are replaceable by re-snapshotting.

Reflections refresh under user steering, from day one. Either a manual re-snapshot, or platform automation the user drives in the moment: COM automation on Windows, where a working proof of concept already exists, is the first example. The point is who holds the wheel. A refresh happens because the user asked for it, never on a schedule the user forgot about, which is what keeps refresh inside the promise that Cairn ingests only what you point it at.

The cut decides three things downstream:

1. **Receipts differ.** A reflection is cited with its source and its snapshot date, and an answer resting on an old snapshot says so. Personal content is cited by its place in the vault.
2. **Dream mode permissions differ.** Personal content is never rewritten, only annotated and linked. Reflections can be reformatted, reorganized, and re-snapshotted freely.
3. **Loss differs.** Reflections regenerate from their sources. Personal content does not. Backup posture, deletion prompts, and sync caution all follow the cut.

Alongside the two source kinds sits a **derived layer**: summaries, diagram descriptions, distillation drafts, index notes, and embeddings, produced on arrival by the work queue (section 9). Derived content is always marked as generated, always regenerable, and never a source of truth; receipts cite through it to the underlying source. The single exception is a distillation you have ratified, which becomes a working record: personal content by adoption (section 6).

## 3. Content types

| Type | Cut | How it arrives |
| --- | --- | --- |
| Email | Personal | Importer |
| Calendar | Personal | Importer |
| Personal notes | Personal | Written in Obsidian directly |
| Meeting notes | Personal | Written or imported; primary distillation target |
| Documents (Word, PDF, and similar) | Either | Dropped in, converted to markdown, original kept as artifact |
| Spreadsheets | Either | Converted to markdown tables where sensible, artifact otherwise |
| Process maps, diagrams, SOPs | Mostly reflection | Section 4 |

Every import is user-initiated. The importers ship together, not in sequence: each has been prototyped elsewhere with heavy precedent, and they are treated as solved problems, not research. The mechanics of arrival, and of everything that reaches back out, are the connector layer in section 8.

## 4. Process maps, diagrams, and SOPs

First-class content, with three verbs:

1. **Ingest.** Existing diagrams and images get a locally generated text description so they are findable and citable. The original stays as the artifact; the description is retrieval scaffolding, clearly marked as generated.
2. **Author.** Describe a process in words, get a draft diagram: Mermaid where its grammar fits, plain SVG where it does not, and models are reliably good at both. Both are text formats, so Obsidian renders them natively, version control diffs them, and every authored diagram carries the generated mark.
3. **Maintain.** SOPs are structured markdown. Distillation can extract steps, owners, and triggers from prose into the structure, and staleness flagging applies to them like any other reflection.

## 5. The hub and the plugin

Obsidian is the interface. The vault is plain markdown files on disk, so "nothing leaves the machine" is true by construction rather than by promise.

The bet underneath the hub choice: the vault is open all day, so capture happens as a side effect of working instead of as a filing chore. Stated honestly, that habit is being built alongside the tool, not before it. The consequence for the plugin: it must earn the daily open, not assume it. If the habit never takes despite a working plugin, the hub choice is wrong and should be revisited.

The plugin is written TypeScript-first for maximum Obsidian compatibility. No sidecar processes unless a wall forces one; that bridge gets crossed if reached. Local models are used over Ollama's HTTP interface for embeddings and generation, which keeps the plugin free of native dependencies.

The plugin adds five capabilities:

1. **Import.** The importers in section 3, always user-initiated.
2. **Ask.** Chat over the vault, grounded: every claim cited, refusal when the vault does not contain the answer, retrieval strength on every receipt. Answers are ephemeral unless deliberately saved.
3. **Distill.** Extraction of decisions, commitments, action items, and open questions from working content. Never affect, tone, or assessments of individuals. Output is always a draft until ratified (section 6).
4. **Generate.** From what the vault holds, proposals for what comes next: tasks, calendar events, messages, email, documents, and briefs. Section 7.
5. **Dream.** Section 9.

Leverage the ecosystem before writing anything: Obsidian's official Importer plugin, existing chat plugins, Excalidraw, Dataview. Build only what is missing.

## 6. The human in the loop

Cairn's bias is strong and structural: the machine drafts, the human ratifies, and ratification is what turns output into memory. The loop sits in one of three places, and every capability is assigned to a tier deliberately.

1. **Ratified: the human approves before it counts.** Anything that asserts meaning is a proposal until accepted. Distilled decisions, commitments, and action items land in a review inbox; accepting one promotes it to a working record, personal content by adoption, and only then is it embedded and citable. Kept summaries and file moves work the same way. Acceptance is the gate into memory. The review inbox is the first ratification surface; inline accept, which must understand the context it sits in, follows later. Priority is ratified like everything else: Cairn may propose an order, for the inbox or for generated tasks, and never sets one. And the cost of ratifying must stay near zero, or the inbox becomes a guilt pile and the loop gets bypassed: the first thing to watch in daily use.
2. **Journaled: pre-authorized by class, reviewed after.** Mechanical work runs autonomously, at arrival on the work queue and at idle as dreaming drains it: converting arrivals, adding links under the journal, reformatting reflections, refreshing embeddings, flagging staleness, maintaining index notes. Every action is journaled and reversible in one step.
3. **Forbidden: no authorization exists.** Rewriting personal content. Deleting source content. Transmitting anything anywhere.

The boundary still being explored is the middle of the ladder: linking and sorting are not purely mechanical, because a link asserts relatedness and sorting rearranges the owner's mental map of their own files. The v1 position:

- Inside personal notes, machine contributions live only in a clearly marked block: annotate and link, never inline edits.
- Inside index notes and reflections, dreaming may link and sort freely, under the journal.
- Moves and renames of personal files are always proposals, never actions.

Tier assignments are not permanent. Over time an action class can graduate from ratified to journaled as trust accrues, and the journal is what makes graduation safe: the record of proposals that were consistently accepted is the evidence a class is ready. Graduation is a future state; in v1 everything meaning-bearing stays a proposal.

## 7. Generation

From what the vault holds, emails, meetings, calendar, notes, Cairn suggests what comes next: tasks, calendar events, messages, email drafts, and longer documents and briefs. Distill finds the commitment; Generate proposes the artifact that honors it. Import, distill, generate is the cycle that makes the vault worth opening every morning.

Everything generated is marked generated, permanently. Ratification and the mark are two different facts about the same artifact: the mark says where it came from, adoption says who answers for it. Ratifying a draft promotes it to personal content, yours to use and send, and the provenance never washes out.

Outputs split by where they land, and the split is the whole design:

1. **Inside the vault: tasks, documents, briefs.** Governed by section 6 as usual, drafts into the review inbox, ratified into the vault. Tasks are written in the ecosystem's standard form, Obsidian's native checkboxes or the dominant tasks-plugin syntax, so ordinary tooling picks them up. Cairn does not invent a task system.
2. **Across the boundary: calendar events, messages, email.** Cairn writes the draft; the human dispatches it. The strongest form Cairn ever produces is a staged draft inside the other system's own drafting area, placed after ratification by user-steered automation, the same wheel-holding rule as reflection refresh: COM automation on Windows can stage the approved draft in the mail client's drafts folder or place the tentative calendar entry. Sending, accepting, and posting are human acts, always.

No graduation path exists across the boundary. Tier graduation (section 6) applies inside the vault only; dispatch never becomes journaled, not even in the future state.

## 8. Connectors

Import, refresh, and fulfillment staging all touch systems Cairn does not own, and the mechanics differ by platform: COM automation on Windows, AppleScript on macOS, file exports everywhere. The tempting answer is a plugin system of Cairn's own. The actual answer is a data contract rather than a code contract, in three layers:

1. **The vault is the integration bus.** Anything that can put a well-formed markdown file in the vault is an importer: a Cairn connector, another Obsidian plugin, a shell script. The contract is a documented metadata convention carried in frontmatter: which cut, what source, what snapshot date. Existing ecosystem importers are supply, not competition; they land content on the bus. Content arriving without the convention is not rejected, it lands unclassified and the review inbox asks for its cut, which is the section 6 mechanic doing double duty.
2. **First-party connectors fill the gaps, in-tree.** Where the ecosystem has no path, chiefly the user-steered platform automation of sections 2 and 7, Cairn ships its own connectors as ordinary reviewed code in this repository: one per domain per platform, no dynamic loading, ever. Each declares its domain (email, calendar, files and shares), its direction (read, stage, or both), and its mechanism. All are disabled by default and enabled individually.
3. **Files are the floor.** Every domain works with nothing but standard formats and user exports: .eml and mailbox exports, .ics, drag and drop. Platform automation is an accelerator, never a requirement, so a locked-down machine or a missing mechanism degrades convenience, not capability.

Extension by third parties happens through the vault as data, never through code injected into Cairn. That single rule is what keeps the promises of section 12 checkable rather than aspirational.

## 9. The work queue and dream mode

Integration happens on arrival, and the vault is the boundary. Anything that enters the vault by any means, a dropped file, typing in any note, another plugin writing to disk, lands on one work queue the moment it arrives: convert if needed, embed, add links under the journal, and ask the inbox for a cut when the source does not say. Obsidian raises in-app events when vault files change, and acting on them is not ambient collection, because everything in the vault is there by the user's own act; the promise governs what may enter the vault, and nothing outside it is ever watched. Links between content are the core value of the product, and value that waits for idle time is value you do not have when you need it.

While you are away, Cairn drains the same work queue with idle local compute and does the deeper work only idle time affords: link discovery beyond the arrival pass, formatting normalization, index notes, staleness flags, and distillation and generation proposals for the review inbox.

Scheduling stays inside Obsidian, light touch by design. There is no scheduling convention in the ecosystem to lean on, and plugins live only while the app is open, so Cairn dreams the way people do: when nothing else is happening. Dreaming triggers on detected idle, works in small chunks, and yields the instant the user stirs; because every chunk is journaled, a half-finished dream is safe to abandon and resume. Dream now drains the queue on demand as a blocking, journaled run with visible progress, and on battery power dreaming holds off. No OS services, no background daemons, nothing running outside the app: the security posture stays as clean as the touch is light. If overnight depth is ever wanted, an explicitly user-created OS schedule is the future-state path, never a default.

Three rules keep it trustworthy:

1. **Personal content is never rewritten.** Annotate and link only, within the section 6 boundaries. Reflections and derived artifacts can be reworked freely.
2. **Every change is journaled.** The dream journal records what changed and why. No journal entry, no change.
3. **Everything is reversible.** The vault is under version control. A morning diff shows the night's work, and one step reverts it.

## 10. Embeddings and summarization

**Embeddings.** Every source file and every ratified record is chunked heading-aware and embedded with a local model. Embeddings are derived data in the strictest sense: disposable, regenerable, refreshed incrementally during dreaming, and never something the user manages. Two exclusions are deliberate: unratified drafts and the dream journal are not indexed, so a proposal can never cite itself as evidence. The prototype proved this pipeline; the plugin reimplements it against the vault.

**The content index.** Beneath both dreaming and recovery sits a manifest: for every file in the vault, its hash, its cut, its source, its snapshot date, and its processing state. The index is what tells dreaming what changed since it last ran, and it is what makes loss survivable, because the principle underneath is absolute: the vault is the only source of truth, and everything else, embeddings, abstracts, the index itself, is a cache reconstructable from it. A gate proves it the house way: drop every derived store, rebuild from the vault alone, get the same answers.

**Summarization.** Two purposes, kept apart:

1. **Retrieval scaffolding.** Per-document abstracts and diagram descriptions that make content findable. Machine-made, machine-consumed, and invisible in receipts: an answer cites the source passage, never the abstract.
2. **Briefs for the human.** Summaries you asked for. Ephemeral unless you keep them, marked as generated if kept, and kept summaries cite their sources like any answer.

Distillation is the third and most constrained form of summarization, and it is governed entirely by sections 5 and 6: facts only, draft until ratified.

## 11. Commodity and product

**Commodity, leaned on and never rebuilt:** local models via Ollama, Obsidian and its plugin ecosystem, markdown, document conversion libraries, vector search.

**Product, the part that does not exist elsewhere:**

1. **The cut, enforced.** Personal and reflection treated differently in receipts, dreaming, and loss.
2. **The discipline.** No receipt, no answer. Refusal over guessing. Ratification as the gate into memory. Distillation that extracts facts and never characterizes people. Drafts across the boundary, never dispatch.
3. **Dreaming with a journal.** Background improvement you can audit and revert.

## 12. What Cairn promises any user

Nothing in Cairn is specific to any organization, sector, or policy regime. The promises are generic and hold everywhere it runs:

1. **Nothing leaves the machine.**
2. **It ingests only what you point it at.** Every import is user-initiated. There is no ambient monitoring. Dream mode reorganizes what is already in the vault; it collects nothing.
3. **It never speaks for you.** No receipt, no answer. No record without ratification. Drafts in other systems, never dispatch: sending, accepting, and posting are yours alone.

The promises are checkable, not aspirational, and a security review can verify them in three sentences: the core executes no third-party code and makes no network calls beyond local model inference on localhost; connectors are the only code that touches other systems, and every one is named, small, in this repository, and off by default; extension happens through data in the vault, never through code loaded into Cairn.

**Cairn cannot be extended, only used.** Obsidian is a customizable environment, and Cairn deliberately is not: no hooks, no API offered to other plugins, no configuration that loads code, no dynamic imports. The claim is stated precisely because a reviewer will hold it to the letter. Every Obsidian plugin shares one runtime, so no plugin can prove isolation from a hostile neighbor in the same process; what Cairn proves instead is provenance, releases reproducible and hash-verifiable against this repository so the code running is the code reviewed, a zero extension surface, and tamper evidence, an integrity self-check at load plus gates anyone can re-run. One further rule closes the loop: everything in the vault is evidence to quote, never instructions to obey. An imported email that tells the model what to do gets cited, not followed, and a gate asserts exactly that.

**The same question gets the same answer.** Cairn runs its models cold, with randomness turned off: on the same machine, over the same vault, the same question produces the same answer, every time. The benefits are the point: receipts can be re-verified, gates can be trusted, and a mistake reproduces exactly, which makes it findable and fixable. The limitations are real and accepted: the prose is plain, there is no rerolling for a better answer, and a wrong answer stays wrong until the evidence or the question improves. That trade dovetails with ratification: the machine drafts cold, and the voice is yours.

## 13. Work queued, not blocked

Nothing in this document waits on an open decision. Three pieces of design work are queued:

1. **The metadata convention.** The frontmatter contract in section 8 is the public interface of the whole connector layer, so its fields deserve deliberate design: cut, source, snapshot date are the obvious three, and what else earns a place decides how much the bus can carry.
2. **The COM proof of concept.** Reflection refresh (section 2) and fulfillment staging (section 7) both depend on it. It has not yet landed in this repository, and it arrives as a section 8 connector: scrubbed, genericized, and gated before it ships.
3. **Graduation mechanics.** Future state by decision. How an action class earns promotion from asked-every-time to journaled gets designed later, on the evidence the journal will have accumulated by then.

## 14. What survives from the prototype

The prototype proved the hard parts: grounded retrieval with receipts, refusal gates that hold, a deterministic front door that answers without a model call, a protocol surface any chat client can use, and 20 gates green on two operating systems.

**Carried forward:** the discipline, the gates as the spec the TypeScript rewrite must pass, and the Python engine as the reference implementation.

**How the gates survive the rewrite:** the engine logic, chunking, retrieval, receipts, refusal, and the front door, lives in plain TypeScript separate from the plugin's interface layer, so the ported gates run headless as an ordinary test suite. The grounding, refusal, receipt, and front-door gates carry over directly because they test behavior, not interface. The rewrite is done when the ported gates go green.

**Retired:** the standalone web interface as the primary surface, and design draft 1, which this document supersedes.

# Cairn Product Thesis

**Draft 3. Numbered for markup. Supersedes docs/DESIGN.md draft 1.**

Changes from draft 2: ratification starts with a review inbox, inline accept follows; tier graduation is named as a future state; reflection refresh can use user-steered platform automation from day one; the gates question is answered in section 12; open questions trimmed to what remains genuinely open.

---

## 1. The thesis

Cairn turns Obsidian into a private working memory for one person.

Everything that crosses your desk lands in one local vault as plain text: email, calendar, meeting notes, personal notes, documents, spreadsheets, process maps. A plugin imports it, answers questions over it with a citation for every claim, distills working content into decisions, commitments, and action items, and improves the vault while you are away.

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

Alongside the two source kinds sits a **derived layer**: summaries, diagram descriptions, distillation drafts, index notes, and embeddings. Derived content is always marked as generated, always regenerable, and never a source of truth; receipts cite through it to the underlying source. The single exception is a distillation you have ratified, which becomes a working record: personal content by adoption (section 6).

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

Every import is user-initiated. The importers ship together, not in sequence: each has been prototyped elsewhere with heavy precedent, and they are treated as solved problems, not research.

## 4. Process maps, diagrams, and SOPs

First-class content, with three verbs:

1. **Ingest.** Existing diagrams and images get a locally generated text description so they are findable and citable. The original stays as the artifact; the description is retrieval scaffolding, clearly marked as generated.
2. **Author.** Describe a process in words, get a draft Mermaid diagram. Obsidian renders Mermaid natively, so the draft is immediately editable and versionable as text.
3. **Maintain.** SOPs are structured markdown. Distillation can extract steps, owners, and triggers from prose into the structure, and staleness flagging applies to them like any other reflection.

## 5. The hub and the plugin

Obsidian is the interface. The vault is plain markdown files on disk, so "nothing leaves the machine" is true by construction rather than by promise.

The bet underneath the hub choice: the vault is open all day, so capture happens as a side effect of working instead of as a filing chore. Stated honestly, that habit is being built alongside the tool, not before it. The consequence for the plugin: it must earn the daily open, not assume it. If the habit never takes despite a working plugin, the hub choice is wrong and should be revisited.

The plugin is written TypeScript-first for maximum Obsidian compatibility. No sidecar processes unless a wall forces one; that bridge gets crossed if reached. Local models are used over Ollama's HTTP interface for embeddings and generation, which keeps the plugin free of native dependencies.

The plugin adds four capabilities:

1. **Import.** The importers in section 3, always user-initiated.
2. **Ask.** Chat over the vault, grounded: every claim cited, refusal when the vault does not contain the answer, retrieval strength on every receipt. Answers are ephemeral unless deliberately saved.
3. **Distill.** Extraction of decisions, commitments, action items, and open questions from working content. Never affect, tone, or assessments of individuals. Output is always a draft until ratified (section 6).
4. **Dream.** Section 7.

Leverage the ecosystem before writing anything: Obsidian's official Importer plugin, existing chat plugins, Excalidraw, Dataview. Build only what is missing.

## 6. The human in the loop

Cairn's bias is strong and structural: the machine drafts, the human ratifies, and ratification is what turns output into memory. The loop sits in one of three places, and every capability is assigned to a tier deliberately.

1. **Ratified: the human approves before it counts.** Anything that asserts meaning is a proposal until accepted. Distilled decisions, commitments, and action items land in a review inbox; accepting one promotes it to a working record, personal content by adoption, and only then is it embedded and citable. Kept summaries and file moves work the same way. Acceptance is the gate into memory. The review inbox is the first ratification surface; inline accept, which must understand the context it sits in, follows later.
2. **Journaled: pre-authorized by class, reviewed after.** Mechanical work runs autonomously: reformatting reflections, refreshing embeddings, flagging staleness, maintaining index notes. Every action is journaled and reversible in one step.
3. **Forbidden: no authorization exists.** Rewriting personal content. Deleting source content. Transmitting anything anywhere.

The boundary still being explored is the middle of the ladder: linking and sorting are not purely mechanical, because a link asserts relatedness and sorting rearranges the owner's mental map of their own files. The v1 position:

- Inside personal notes, machine contributions live only in a clearly marked block: annotate and link, never inline edits.
- Inside index notes and reflections, dreaming may link and sort freely, under the journal.
- Moves and renames of personal files are always proposals, never actions.

Tier assignments are not permanent. Over time an action class can graduate from ratified to journaled as trust accrues, and the journal is what makes graduation safe: the record of proposals that were consistently accepted is the evidence a class is ready. Graduation is a future state; in v1 everything meaning-bearing stays a proposal.

## 7. Dream mode

While you are away, Cairn improves the vault with idle local compute: discovers and adds links between related notes and reflections, normalizes formatting, refreshes embeddings, builds and maintains index notes, flags stale reflections, and drafts distillations from new working content for the review inbox.

Three rules keep it trustworthy:

1. **Personal content is never rewritten.** Annotate and link only, within the section 6 boundaries. Reflections and derived artifacts can be reworked freely.
2. **Every change is journaled.** The dream journal records what changed and why. No journal entry, no change.
3. **Everything is reversible.** The vault is under version control. A morning diff shows the night's work, and one step reverts it.

## 8. Embeddings and summarization

**Embeddings.** Every source file and every ratified record is chunked heading-aware and embedded with a local model. Embeddings are derived data in the strictest sense: disposable, regenerable, refreshed incrementally during dreaming, and never something the user manages. Two exclusions are deliberate: unratified drafts and the dream journal are not indexed, so a proposal can never cite itself as evidence. The prototype proved this pipeline; the plugin reimplements it against the vault.

**Summarization.** Two purposes, kept apart:

1. **Retrieval scaffolding.** Per-document abstracts and diagram descriptions that make content findable. Machine-made, machine-consumed, and invisible in receipts: an answer cites the source passage, never the abstract.
2. **Briefs for the human.** Summaries you asked for. Ephemeral unless you keep them, marked as generated if kept, and kept summaries cite their sources like any answer.

Distillation is the third and most constrained form of summarization, and it is governed entirely by sections 5 and 6: facts only, draft until ratified.

## 9. Commodity and product

**Commodity, leaned on and never rebuilt:** local models via Ollama, Obsidian and its plugin ecosystem, markdown, document conversion libraries, vector search.

**Product, the part that does not exist elsewhere:**

1. **The cut, enforced.** Personal and reflection treated differently in receipts, dreaming, and loss.
2. **The discipline.** No receipt, no answer. Refusal over guessing. Ratification as the gate into memory. Distillation that extracts facts and never characterizes people.
3. **Dreaming with a journal.** Background improvement you can audit and revert.

## 10. What Cairn promises any user

Nothing in Cairn is specific to any organization, sector, or policy regime. The promises are generic and hold everywhere it runs:

1. **Nothing leaves the machine.**
2. **It ingests only what you point it at.** Every import is user-initiated. There is no ambient monitoring. Dream mode reorganizes what is already in the vault; it collects nothing.
3. **It never speaks for you.** No receipt, no answer; no record without ratification; no action in any other system.

## 11. Open questions

1. **Graduation criteria.** When the future state arrives, what evidence earns an action class its promotion from ratified to journaled: a count of consistent acceptances, an explicit user grant, or both? Non-blocking for v1.
2. **Ratification cost.** The cost of ratifying must stay near zero or the inbox becomes a guilt pile and the loop gets bypassed. What near-zero looks like is a design problem for the inbox, and the first thing to watch in daily use.
3. **The refresh proof of concept.** The COM automation proof of concept has not yet landed in this repository. It needs the same treatment as everything else here: scrubbed, genericized, and gated before it ships.

## 12. What survives from the prototype

The prototype proved the hard parts: grounded retrieval with receipts, refusal gates that hold, a deterministic front door that answers without a model call, a protocol surface any chat client can use, and 20 gates green on two operating systems.

**Carried forward:** the discipline, the gates as the spec the TypeScript rewrite must pass, and the Python engine as the reference implementation.

**How the gates survive the rewrite:** the engine logic, chunking, retrieval, receipts, refusal, and the front door, lives in plain TypeScript separate from the plugin's interface layer, so the ported gates run headless as an ordinary test suite. The grounding, refusal, receipt, and front-door gates carry over directly because they test behavior, not interface. The rewrite is done when the ported gates go green.

**Retired:** the standalone web interface as the primary surface, and design draft 1, which this document supersedes.

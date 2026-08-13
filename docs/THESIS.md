# Cairn Product Thesis

**Draft 1. Numbered for markup. Supersedes docs/DESIGN.md draft 1.**

---

## 1. The thesis

Cairn turns Obsidian into a private working memory for one person.

Everything that crosses your desk lands in one local vault as plain text: email, calendar, meeting notes, personal notes, documents, spreadsheets, process maps. A plugin imports it, answers questions over it with a citation for every claim, distills working content into decisions, commitments, and action items, and improves the vault while you are away.

Models and infrastructure are commodity. The product is the connected corpus and the discipline applied to it.

## 2. Two kinds of content, cut cleanly

Every piece of content in the vault is one of two kinds, and the cut is enforced, not advisory.

**Personal.** Yours. Email, calendar, personal notes, meeting notes, drafts, local files never published. The vault is where this content lives. It is current, precious, and irreplaceable.

**Reflection.** The organization's, or the world's. Timestamped snapshots of shared drives, intranet pages, published policies, references, SOPs. The source of truth lies elsewhere; the vault holds an extraction taken at a known moment. Reflections are replaceable by re-snapshotting.

The cut decides three things downstream:

1. **Receipts differ.** A reflection is cited with its source and its snapshot date, and an answer resting on an old snapshot says so. Personal content is cited by its place in the vault.
2. **Dream mode permissions differ.** Personal content is never rewritten, only annotated and linked. Reflections can be reformatted, reorganized, and re-snapshotted freely.
3. **Loss differs.** Reflections regenerate from their sources. Personal content does not. Backup posture, deletion prompts, and sync caution all follow the cut.

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

Every import is user-initiated. Which importer gets built first is open question 9.1.

## 4. Process maps, diagrams, and SOPs

First-class content, with three verbs:

1. **Ingest.** Existing diagrams and images get a locally generated text description so they are findable and citable. The original stays as the artifact; the description is retrieval scaffolding, clearly marked as generated.
2. **Author.** Describe a process in words, get a draft Mermaid diagram. Obsidian renders Mermaid natively, so the draft is immediately editable and versionable as text.
3. **Maintain.** SOPs are structured markdown. Distillation can extract steps, owners, and triggers from prose into the structure, and staleness flagging applies to them like any other reflection.

## 5. The hub and the plugin

Obsidian is the interface. The vault is plain markdown files on disk, so "nothing leaves the machine" is true by construction rather than by promise.

The bet underneath the hub choice: the vault is open all day, so capture happens as a side effect of working instead of as a filing chore. Stated honestly, that habit is being built alongside the tool, not before it. Daily Obsidian use is the goal, and prior attempts stalled because the tooling around it was too slow to develop. The consequence for the plugin: it must earn the daily open, not assume it, and the first capability shipped should be the one that makes opening the vault each morning worth it. If the habit never takes despite a working plugin, the hub choice is wrong and should be revisited.

The plugin adds four capabilities:

1. **Import.** The importers in section 3, always user-initiated.
2. **Ask.** Chat over the vault, grounded: every claim cited, refusal when the vault does not contain the answer, retrieval strength on every receipt.
3. **Distill.** Extraction of decisions, commitments, action items, and open questions from working content. Never affect, tone, or assessments of individuals.
4. **Dream.** Section 6.

Leverage the ecosystem before writing anything: Obsidian's official Importer plugin, existing chat plugins, Excalidraw, Dataview. Build only what is missing. The existing engine already serves an OpenAI-compatible endpoint, so a working v0 may be an existing chat plugin pointed at that endpoint with zero new plugin code.

## 6. Dream mode

While you are away, Cairn improves the vault with idle local compute: discovers and adds links between related notes and reflections, normalizes formatting, refreshes embeddings, builds and maintains index notes, flags stale reflections, and extracts distillations from new working content.

Three rules keep it trustworthy:

1. **Personal content is never rewritten.** Annotate and link only. Reflections and generated artifacts can be reworked freely.
2. **Every change is journaled.** The dream journal records what changed and why. No journal entry, no change.
3. **Everything is reversible.** The vault is under version control. A morning diff shows the night's work, and one step reverts it.

## 7. Commodity and product

**Commodity, leaned on and never rebuilt:** local models via Ollama, Obsidian and its plugin ecosystem, markdown, document conversion libraries, vector search.

**Product, the part that does not exist elsewhere:**

1. **The cut, enforced.** Personal and reflection treated differently in receipts, dreaming, and loss.
2. **The discipline.** No receipt, no answer. Refusal over guessing. Distillation that extracts facts and never characterizes people.
3. **Dreaming with a journal.** Background improvement you can audit and revert.

## 8. What Cairn promises any user

Nothing in Cairn is specific to any organization, sector, or policy regime. The promises are generic and hold everywhere it runs:

1. **Nothing leaves the machine.**
2. **It ingests only what you point it at.** Every import is user-initiated. There is no ambient monitoring. Dream mode reorganizes what is already in the vault; it collects nothing.
3. **No receipt, no answer.**

## 9. Open questions

1. **Importer priority.** Which of email, calendar, meeting notes, or documents earns its importer first, by pain?
2. **Plugin architecture.** Engine in TypeScript inside the plugin, or the existing Python engine as a local sidecar behind its protocol? Install friction versus rewrite cost. Decide by probe, not preference.
3. **Where distillations live**, and whether they become citable evidence in later answers. Carried over from design draft 1.
4. **How reflections refresh.** Manual re-snapshot, a prompt when opened stale, or scheduled during dreaming?

## 10. What survives from the prototype

The prototype proved the hard parts: grounded retrieval with receipts, refusal gates that hold, a deterministic front door that answers without a model call, a protocol surface any chat client can use, and 20 gates green on two operating systems.

**Carried forward:** the discipline, the gates, and likely the engine as a backend during transition.

**Retired:** the standalone web interface as the primary surface, and design draft 1, which this document supersedes.

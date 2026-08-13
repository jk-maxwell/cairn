# Cairn Rationale

*The reasoning at full depth. THESIS.md says what, ROADMAP.md says when, DECISIONS.md is the dated ledger. This document is why: the arguments that produced those documents, including the ones that lost. Numbered for markup.*

---

## 1. Why the proof of concept was not the product

The proof of concept was a standalone question-answering tool over deliberately saved documents. It worked: grounded retrieval, receipts, refusal, 20 gates. It was still the wrong product, and the reasons are worth keeping because they are the tests any future feature must pass.

**1.1 The thesis it embodied stacked three claims**, each doing separate work: people will curate a corpus one file at a time; retrieval with citations over that corpus beats their current method; local and private is a requirement rather than a preference. Every claim has to hold or the product fails, and the first one failed on inspection.

**1.2 The pain and the product did not match.** The motivating stories were a decision nobody wrote down, a policy scattered across four sites, and a promise living in somebody's head. All three are failures of capture, and the built tool did only retrieval over what was already captured. A tool that knows only what you deliberately saved cannot answer "what did we decide" unless someone wrote minutes and filed them. The tool demanded exactly the discipline whose absence created the problem.

**1.3 Retrieval over documents is a commodity.** Tenant-integrated assistants will answer questions over organizational email, calendars, and shared drives with zero curation, by default, for everyone. A local tool cannot outcompete that on its own ground. The differentiators the proof of concept offered, private, local, cited, are permissions, not desires: reasons you are allowed to use it, not reasons you want it.

**1.4 The existence question, and its answer.** What can a local, private tool do that the tenant tool cannot? The answer that survived: hold the personal working layer, the notes you would not put in the tenant, the distillations, the connections you drew yourself, and merge it with snapshots of the organizational layer in one queryable place. The tenant tool will never hold your private thinking. A vault that joins your thinking to the organization's output is a different product, not a worse copy of the same one.

**1.5 What survived the critique.** The engine, the receipts, the refusal discipline, and the gates. The proof of concept failed as a product and succeeded completely as a proof: the hard technical parts of grounded local answering are solved and measured. That distinction, transport versus cargo, is why the pivot threw away the application and kept everything inside it.

## 2. The hub bet

**2.1 Why Obsidian.** The proof of concept hand-rolled interface, storage, editing, and search. Obsidian provides all four over plain markdown files on disk, which makes "nothing leaves the machine" true by construction rather than by promise, plus an ecosystem that supplies importers and task management for free. The instinct to layer over base functionality rather than rebuild it is the same instinct as using commodity models: the product is the discipline, never the plumbing.

**2.2 The bet stated honestly.** The hub choice assumes the vault is open all day, so capture happens as a side effect of working rather than as a filing chore. That habit is being built alongside the tool, not before it. Prior attempts at daily use stalled because the tooling around the vault was too slow to develop. The consequence is a design obligation: the plugin must earn the daily open, not assume it, and the roadmap treats the habit as a falsifiable claim with its own gate. If the habit never takes despite a working plugin, the hub choice was wrong, and no amount of features will fix an unopened door.

## 3. The cut: personal and reflection

**3.1 The definitions.** Personal content is yours: email, calendar, notes, drafts, files never published. The vault is where it lives; it is current, precious, and irreplaceable. Reflections are the organization's or the world's: timestamped snapshots of shared drives, intranet pages, policies, SOPs. The source of truth lies elsewhere; the vault holds an extraction taken at a known moment.

**3.2 Why one cut instead of three policies.** The cut is not taxonomy, it is mechanics. One classification decides three behaviors that would otherwise each need their own rules: what a receipt says (reflections cite source plus snapshot date, and answers resting on stale snapshots say so), what dreaming may touch (reflections freely, personal never rewritten), and what loss means (reflections regenerate from their sources, personal does not, so backup posture and deletion prompts follow the cut). One enforced distinction driving three behaviors is simpler to build, simpler to explain, and simpler to audit than three separate policies that could drift apart.

**3.3 The derived layer.** Alongside the two source kinds sits everything the machine makes: summaries, diagram descriptions, distillation drafts, index notes, embeddings. Derived content is always marked as generated, always regenerable, and never a source of truth; receipts cite through it to the underlying source. The single exception is a ratified distillation, which becomes a working record, personal content by adoption. That exception is deliberate and singular: it is the one door through which machine output becomes memory, and section 4 explains the door.

**3.4 Refresh and who holds the wheel.** Reflections refresh under user steering: manual re-snapshot, or platform automation the user drives in the moment. The line between allowed and forbidden is not manual versus automated; it is who initiates. A refresh happens because the user asked, never on a schedule the user forgot about, which is what keeps refresh inside the promise that Cairn ingests only what you point it at.

## 4. Ratification: the gate into memory

**4.1 The principle.** The machine drafts, the human ratifies, and ratification is what turns output into memory. This is the strongest single design commitment in the product, and it was chosen over autonomous filing for a reason about trust: confidence in an assistant's judgment is fragile and unfalsifiable, while an auditable record of proposals consistently accepted is evidence.

**4.2 The three tiers.** The human loop sits in one of three places, and every capability is assigned deliberately. Ratified: anything asserting meaning is a proposal until accepted; distillations, kept summaries, and file moves land in a review inbox, and acceptance promotes them. Journaled: mechanical work pre-authorized by class, reformatting reflections, refreshing embeddings, flagging staleness, maintaining index notes, runs autonomously but every action is journaled and reversible in one step. Forbidden: rewriting personal content, deleting source content, transmitting anything anywhere. No authorization exists and none can be granted.

**4.3 The genuinely hard boundary is the middle.** Linking and sorting are not purely mechanical: a link asserts relatedness, and sorting rearranges the owner's mental map of their own files. The v1 position: inside personal notes, machine contributions live only in a clearly marked block, annotate and link, never inline edits; inside index notes and reflections, dreaming may link and sort freely under the journal; moves and renames of personal files are always proposals. This line is the one most likely to move with experience, and it is written down precisely so that moving it is a decision rather than an erosion.

**4.4 Graduation.** Tier assignments are not permanent. Over time an action class can graduate from ratified to journaled, and the journal is what makes graduation safe: the record of proposals consistently accepted is the evidence a class is ready. Graduation is future state by decision, designed later on the evidence the journal will have accumulated, because designing a trust mechanism before any trust record exists would be designing from imagination.

**4.5 Priority is ratified like everything else.** Cairn may propose an order, for the inbox or for generated tasks, and never sets one. Priority is a judgment about what matters, and judgments about what matters are exactly the category the loop exists to keep human.

**4.6 The failure mode is the guilt pile.** If ratifying costs too much, the inbox accumulates, the user stops looking, and the loop gets bypassed in practice while remaining intact on paper. Ratification cost staying near zero is a design requirement of the inbox, the first thing to watch in daily use, and a named kill criterion: if the cost stays high after redesign, the human-in-the-loop model itself gets revisited, because a loop everyone bypasses protects no one.

## 5. Generation and the boundary

**5.1 The loop that earns the daily open.** Distill finds the commitment; Generate proposes the artifact that honors it: tasks, calendar events, messages, email drafts, documents, briefs. Import, distill, generate is the cycle that makes the vault worth opening every morning, because it converts what crossed your desk yesterday into what you should do today.

**5.2 The split is by where the output lands.** Inside the vault, tasks, documents, and briefs go through the ordinary inbox. Tasks are written in the ecosystem's standard syntax because Cairn inventing a task system would be rebuilding commodity. Across the boundary, calendar events, messages, and email, Cairn writes the draft and the human dispatches it. The strongest form Cairn ever produces is a staged draft inside the other system's own drafting area, placed after ratification by user-steered automation. Sending, accepting, and posting are human acts, always.

**5.3 No graduation across the boundary, ever.** Tier graduation applies inside the vault only. Dispatch never becomes journaled, not even in the future state. This is the one place the product refuses its own trust mechanism, deliberately: a mis-filed note is reversible, a sent email is not, and the asymmetry of harm justifies the asymmetry of rules.

**5.4 Provenance and accountability are different facts.** Everything generated is marked generated, permanently. Ratification does not remove the mark; it changes who answers for the artifact. A brief you ratified and reworked is yours to send, and the vault still remembers the machine drafted it. Conflating the two, letting adoption wash out provenance, would make the generated mark a lie by attrition.

**5.5 This redrew a rule instead of bending it.** The proof of concept promised "it does not act on other systems." Generation walks straight at that promise, and the resolution was to redraw the line precisely rather than quietly erode it: drafts yes, dispatch never. Promises survive contact with new features only when the redrawing is explicit.

## 6. Connectors: a data contract, not a code contract

**6.1 The problem.** Import, refresh, and fulfillment staging all touch systems Cairn does not own, and the mechanics differ by platform: COM automation on Windows, AppleScript on macOS, file exports everywhere. The tempting answer is a plugin system of Cairn's own.

**6.2 Why the plugin system loses.** There are two things "extensible" can mean. A code contract, where Cairn loads connector code and third parties run inside it, fails security review almost by definition: "nothing leaves the machine" becomes unverifiable the moment arbitrary code executes inside the thing that promised it. You cannot promise what you cannot inspect. A data contract, where Cairn defines what a well-formed arrival looks like and anything that can produce one is a connector, keeps every promise checkable.

**6.3 The three layers.** First, the vault is the integration bus: anything that can put a well-formed markdown file in the vault is an importer, whether a Cairn connector, another Obsidian plugin, or a shell script, and the contract is frontmatter, which cut, what source, what snapshot date. Existing ecosystem importers become supply rather than competition. Second, first-party connectors fill the gaps in-tree: one per domain per platform, no dynamic loading ever, each declaring its domain, direction, and mechanism, all disabled by default and enabled individually. Third, files are the floor: every domain works with nothing but standard formats and exports, .eml, .ics, drag and drop, so platform automation is an accelerator and losing it degrades convenience, not capability.

**6.4 Arrivals without the convention.** Content landing on the bus without frontmatter is not rejected; it lands unclassified and the review inbox asks for its cut. Third-party imports thereby get folded into the human-in-the-loop mechanic instead of bypassing it. Rejection was considered and dropped: a bus that bounces unfamiliar cargo teaches people to stop using the bus.

**6.5 The platform asymmetry, stated rather than hidden.** COM against Outlook is deeper than AppleScript against Mail and Calendar, and macOS automation consent adds friction Windows lacks. The Mac connectors will lag the Windows ones in depth. Files-as-floor covers the gap; pretending symmetry would not.

## 7. Trust made checkable

**7.1 The three promises.** Nothing leaves the machine. It ingests only what you point it at. It never speaks for you: no receipt no answer, no record without ratification, drafts in other systems never dispatch. Nothing in Cairn is specific to any organization, sector, or policy regime; the promises are generic and hold everywhere it runs.

**7.2 The security review in three sentences.** The core executes no third-party code and makes no network calls beyond local model inference on localhost. Connectors are the only code that touches other systems, and every one is named, small, in this repository, and off by default. Extension happens through data in the vault, never through code loaded into Cairn. The reviewer audits a handful of files instead of trusting a marketplace.

**7.3 Integrity, claimed precisely.** Cairn cannot be extended, only used: no hooks, no API offered to other plugins, no configuration that loads code, no dynamic imports. The claim is scoped with care because a reviewer will hold it to the letter. Every Obsidian plugin shares one runtime, so no plugin can prove isolation from a hostile neighbor in the same process, and Cairn does not pretend otherwise. What it proves instead: provenance, releases reproducible and hash-verifiable against this repository, so the code running is the code reviewed; a zero extension surface; and tamper evidence, an integrity self-check at load plus gates anyone can re-run. Precise claims survive review. Broad ones get shredded, and deserve to.

**7.4 Evidence, never instructions.** Everything in the vault is evidence to quote, never instructions to obey. This matters most for imported email, which is attacker-authored text by definition. An email that tells the model what to do gets cited, not followed, and a gate asserts exactly that. The gate must exist, and must have been seen to fail, before the first email importer lands: the defense precedes the threat's arrival, by construction of the roadmap rather than by hope.

**7.5 Cold models, both edges.** Cairn runs its models with randomness off: same machine, same vault, same question, same answer. The benefits are the point: receipts can be re-verified, gates can be trusted, and a mistake reproduces exactly, which makes it findable and fixable. The limitations are accepted, not denied: the prose is plain, there is no rerolling for a better answer, and a wrong answer stays wrong until the evidence or the question improves. The trade dovetails with ratification: the machine drafts cold, and the voice is yours. A product built on receipts chose verifiability over flair, and would choose it again.

## 8. The self-tending vault

**8.1 What dreaming is for.** Idle local compute is free and private, and the vault accumulates entropy: unlinked notes, stale snapshots, unprocessed arrivals. Dreaming spends the first against the second: link discovery, formatting normalization, embedding refresh, index notes, staleness flags, and drafting distillations and generation proposals for the inbox.

**8.2 The three trust rules.** Personal content is never rewritten, annotate and link only. Every change is journaled, no journal entry no change, the dream-time analog of no receipt no answer. Everything is reversible, the vault under version control, a morning diff showing the night's work, one step reverting it. An unwatched capability earns trust through auditability or not at all, which is also why its acceptance gate runs thirty days rather than a weekend.

**8.3 Scheduling, and why there are no services.** Obsidian has no scheduling convention and plugins live only while the app is open, so Cairn dreams the way people do: when nothing else is happening. Idle-triggered, chunked, yielding the instant the user stirs, safe to abandon mid-run because every chunk is journaled, with a manual dream-now command and a hold on battery power. No OS services and no daemons, which keeps the security posture as clean as the touch is light. An explicitly user-created OS schedule is the only future path to overnight depth, never a default.

**8.4 The vault is the only source of truth.** Everything else, embeddings, abstracts, the content index itself, is a cache reconstructable from it. The content index, per file: hash, cut, source, snapshot date, processing state, is what tells dreaming what changed and what makes loss survivable. The gate proves it the house way: drop every derived store, rebuild from the vault alone, get the same answers. Cold models make "the same answers" byte-comparable rather than approximately similar.

**8.5 Proposals cannot cite themselves.** Unratified drafts and the dream journal are excluded from the embedding index. Without this rule a draft could surface as retrieval evidence for the claim it proposes, a circularity that would let the machine bootstrap its own assertions into the corpus. The exclusion closes the loop-hole structurally rather than by policy.

**8.6 Summarization is three things kept apart.** Retrieval scaffolding, per-document abstracts and diagram descriptions, machine-made and machine-consumed, invisible in receipts because an answer cites the source passage and never the abstract. Briefs for the human, ephemeral unless kept, marked generated if kept. And distillation, the most constrained form: facts only, never affect, tone, or assessments of individuals, draft until ratified. Keeping the three apart prevents the quiet failure where a summary starts being treated as a source.

## 9. Sequencing rationale

**9.1 The dependency spine.** The metadata convention leads because everything reads it and designing it late means migrating a live vault. The content index follows because incremental embedding, dreaming's worklist, and the rebuild guarantee all stand on it. Dreaming ships last because it is the only capability that acts unwatched, and everything it depends on, journal, revert, the cut, must be proven in daylight first.

**9.2 Why the probe runs in week one.** The prototype proved the engine; nothing yet proves the habit, and the habit is the bigger risk. An existing chat plugin pointed at the reference engine's endpoint on a real vault tests "does the author actually reach for this inside Obsidian" in days, for nearly nothing, before the expensive rewrite begins. Cheap falsification of the riskiest claim first.

**9.3 The receipt defect and the fixtures.** A known defect in the reference engine truncates the retrieval-strength line on clean answers and doubles the warning on flagged ones. It was a minor fix until the reference became the parity standard: golden answers frozen from a defective reference make the defect the spec. So the fix precedes any fixture recording, and the gate asserts the whole strength sentence rather than its prefix, because the old gate's prefix-matching is exactly how the defect survived.

**9.4 Kill criteria are decisions, not warnings.** Made now, while no sunk cost argues otherwise. The habit gate failing twice with a healthy engine stops building and forces a surface rethink. Any parity divergence is a stop investigated to root cause, because a retrieval engine that is almost the reference is not the reference. A ratification cost that stays high after redesign reopens the human-in-the-loop model itself. A single dream rewrite of personal content is a stop, full revert, and redesign: the acceptable rate of that defect is zero.

## 10. The inversion: surface before backend

**10.1 The argument.** The original roadmap sequenced the engine port first and the surface second, which was momentum from the prototype: the engine is the part already proven, so building it first proves nothing new. The plugin packs five capabilities into one surface, and if that surface is not simple, the product fails regardless of engine quality. Surface risk is the open risk, so the surface goes first: land the UX as a wireframe, build the shell as a drivable plugin over synthetic data and clean contracts, then swap the real backend in behind a stable interface, capability by capability, Ask first.

**10.2 Three amendments that keep the inversion honest.** First, the probe still runs in parallel, because a mock can validate comprehension but not the habit; the habit forms around real answers or not at all, and the two tracks falsify different claims. Second, the contracts are transcribed, not invented: the reference engine already defines the real semantics, receipts, refusal, strength, citations, the on-topic-but-silent case, and the fixtures are recorded from it over the synthetic corpus, so the eventual swap is a parity exercise against golden data that existed from day one. Mock-first projects die at the swap when an invented contract meets reality; a transcribed contract has already met it. Third, the mock lies about nothing except the data, especially time: fixtures carry recorded token timing, so the shell is designed against streaming, pauses, and refusals rather than against instant answers from a world that does not exist.

**10.3 The four journeys.** Ask: a question to a cited answer or an honest refusal. Capture: something arrives and gets its cut. Ratify: inbox to memory or task. Wake: the morning open, what changed, what dreamed, what is proposed. If the wireframe cannot make these four feel simple, the plugin has failed before any code exists, which is the cheapest possible place to fail.

**10.4 Wireframes as text first.** Markdown and ASCII layouts in the repository, because they are diffable, reviewable by numbered note, and hold no tooling hostage. A clickable mock is the bridge to the shell after layouts settle, not the medium of the argument.

## 11. How the documents relate

THESIS.md is the product, ratified and authoritative. ROADMAP.md is the sequence, horizons ending at gates that can fail. DECISIONS.md is the dated, append-only ledger, one entry per decision with its reason. This document is the connective tissue: the full arguments, including the losing sides, kept so that revisiting a decision starts from why it was made rather than from archaeology. When they conflict, the thesis wins, and the conflict itself is a defect to be fixed in whichever document drifted.

The house rule binds them all: nothing lands because it was written carefully. A gate that has never been seen to fail is not yet a gate, a claim that cannot fail is not yet a claim, and a roadmap whose gates cannot fail is a wish. The documents above are full of claims that can fail, on purpose.

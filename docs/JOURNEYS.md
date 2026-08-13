# Cairn User Journeys

**Draft 1. Numbered for markup.**

*The UX comes first. These journeys are the specification the wireframes must satisfy, the wireframes are the specification the plugin shell must satisfy, and the shell runs on recorded fixtures before any real backend exists. A journey the surface cannot make simple is a defect in the surface, found at the cheapest possible moment.*

---

## 1. How to read this document

1. **Journeys are written from the user's chair.** Steps name what the person does and sees, never what the software does inside. Implementation vocabulary is a defect here.
2. **Every journey ends with a test that can fail.** Task-based, counted in actions, checkable by watching someone try. The house rule applies to interfaces too: a journey that cannot fail its test is decoration.
3. **Waits, refusals, and failures are part of the journey, not exceptions to it.** An answer takes seconds and streams. A refusal is a first-class outcome. A conversion can fail. The journeys include them because the surface must be designed against them.

There are four daily journeys, three occasional ones, and three that must never exist.

## 2. The surfaces

Five capabilities do not mean five surfaces. The user experiences three, plus the verbs to reach them:

1. **The chat pane**: where questions are asked and answers arrive with receipts.
2. **The inbox**: where everything awaiting ratification lives, arrivals needing a cut, distillations, generated drafts, proposed moves.
3. **The morning view**: what changed while you were away, what dreamed, what is waiting.

Everything else is verbs in Obsidian's own idiom: commands in the palette, drag and drop, context menus on notes. Cairn adds as little chrome as possible and never invents a container where a note or a pane already serves. Wireframes will be drawn one per surface; journeys cross surfaces freely.

---

## 3. Journey: Ask (daily)

**3.1 The moment.** Mid-work, a question surfaces: what did we decide about the exception process? The old way is five minutes of searching or an interruption of a colleague. The bet is that this reflex retargets to Cairn.

**3.2 The walk.**

1. One keystroke opens the chat pane from anywhere in Obsidian. Focus is already in the input.
2. Type the question in plain language. Enter.
3. The answer streams in over a few seconds. While it streams, the retrieval strength label is already visible, so the reader knows before the first sentence finishes whether this answer stands on solid ground.
4. The receipt sits under the answer: every citation names its source, and a reflection's citation shows its snapshot date.
5. Clicking a citation opens the source note at the cited passage, in a split, without losing the conversation.
6. The answer is ephemeral. A single visible action saves it as a note, marked generated, if it is worth keeping.

**3.3 The variants, equally designed.**

- **The refusal**: near-instant, honest, and calm: the vault does not contain this, with the nearest headings retrieval found, so a dead end is still a trail marker.
- **On topic but silent**: the material relates but does not answer; the answer says what the passages do cover, cited.
- **Weak retrieval**: the strength label says so plainly, before the reader invests belief.

**3.4 What this demands of the surface.** A global hotkey and palette command. Streaming text that renders receipts progressively. Strength shown early and impossible to miss without being alarming. Citations as first-class links. Save-as-note as an explicit act, never automatic.

**3.5 The test.** From anywhere in Obsidian to a submitted question in two actions. From answer to the cited passage in one. A refusal arrives in under a second on fixture timing. Watched once, unaided.

## 4. Journey: Capture (daily)

**4.1 The moment.** Something crossed the desk: a policy PDF, an emailed decision, a meeting invite, a diagram. It should live in the vault, correctly classified, without ceremony.

**4.2 The walk.**

1. Drag the file into the vault, or invoke the import command on it. Writing a note in Obsidian is already capture and involves Cairn not at all.
2. Conversion happens visibly: a compact report says what was converted, what was chunked, and what failed, by name. Silence is never the success signal.
3. If the arrival's cut is known from its source, it is applied and shown. If not, the item appears in the inbox as unclassified, and assigning the cut is one action there.
4. The original file is kept as the artifact beside its converted markdown.

**4.3 What this demands of the surface.** A drop target that is wherever the user already is. A conversion report that fits in a glance but names every failure. Cut assignment as a single choice, personal or reflection, with the source visible. No modal interrogation at drop time; classification can wait for the inbox.

**4.4 The test.** File to classified, searchable vault content in three actions or fewer. A deliberately corrupt file produces a named failure, not silence. The user can always answer the question "did it work?" without opening a log.

## 5. Journey: Ratify (daily)

**5.1 The moment.** Cairn has been reading what arrived and has proposals: two commitments distilled from Tuesday's meeting notes, a task suggested from an email, one unclassified arrival, a proposed file move. None of it is memory yet. That is the point.

**5.2 The walk.**

1. The inbox shows a short list, newest first, each item one line: what kind of proposal, from what source.
2. Selecting an item shows the draft and, beside it, the evidence: the source passage that produced it. No proposal is judged without its provenance visible.
3. One keystroke accepts. One rejects. Accept-with-edit opens the draft for a quick correction first. Suggested priority is visible and adjustable, never pre-applied.
4. Accepted distillations become working records; accepted tasks are written in the ecosystem's standard syntax; accepted cut assignments file the arrival. Rejected proposals vanish and are remembered as rejected, so they do not return.
5. The list shrinks to empty in minutes, and empty is the normal state, not an achievement.

**5.3 What this demands of the surface.** Keyboard-first, single-key verbs. Evidence inline, not behind a click. Editing in place. A visible count that stays honest and small. Nothing in the design that scolds: a full inbox is information, not guilt, but a full inbox that stays full is a design failure by our own kill criteria.

**5.4 The test.** Ten mixed proposals processed in under two minutes by someone who has seen the surface once. Every acceptance had its evidence on screen at decision time. Ratification cost, measured in seconds per item, is a number we track from day one.

## 6. Journey: Wake (daily)

**6.1 The moment.** Morning. Obsidian opens. The question is not "what should I do," it is "what changed while I was away, and do I trust it?"

**6.2 The walk.**

1. The morning view is the first thing shown, and it fits on one screen: what dreamed (links added, formatting normalized, embeddings refreshed, in plain counts), what arrived, what is waiting in the inbox, what went stale.
2. The dream journal is one click away and reads as a diff: this changed, here is why, here is the revert.
3. One action reverts the entire night if anything looks wrong. Trust is the default, revert is the guarantee.
4. From the same view, one click enters the inbox with the morning's proposals queued.
5. Stale reflections are flagged with their age, each carrying its one-action refresh.

**6.3 What this demands of the surface.** Calm density: counts and names, no feeds, no red badges. The revert affordance visible without being ominous. The whole state legible in under a minute, because this view is the daily open the product must earn, and a view that takes effort to read will stop being opened.

**6.4 The test.** A user who was away for a weekend understands the full state of their vault in under sixty seconds, names what dreaming changed, and can revert it in one action. Watched, timed, unaided.

---

## 7. Journey: Begin (once)

**7.1 The moment.** The plugin is installed on a machine that has never seen Cairn. The distance to the first cited answer is the whole first impression.

**7.2 The walk.**

1. Enable the plugin. It checks its world and reports in plain language: Ollama reachable or not, models present or not, vault located. Every failure names its one fix.
2. The preflight runs visibly, the gate suite in miniature, and green means something because red was possible.
3. The first ask works against whatever notes the vault already holds, because writing notes is capture and every Obsidian user already has notes. No sample corpus required for the first win.

**7.3 The test.** Fresh machine to first cited answer guided only by the plugin's own screens. Each missing prerequisite produces an instruction, not an error code.

## 8. Journey: Refresh (occasional)

**8.1 The moment.** A reflection is stale: the policy snapshot is from three months ago and the receipt on this morning's answer said so.

**8.2 The walk.** From the flag, wherever it appears, one action starts the refresh: manual re-snapshot, or the user-steered connector where one is enabled. The new snapshot records its date; the receipt on the next answer carries it. What the user steers, the user sees: automation shows what it fetched before it lands.

**8.3 The test.** Stale flag to fresh snapshot in two actions where a connector exists, and the answer's receipt shows the new date without any other change.

## 9. Journey: Recover (rare)

**9.1 The moment.** A machine migration, a corrupted cache, or plain doubt. The vault is the only source of truth, and this is the journey where that promise is redeemed.

**9.2 The walk.** One command: rebuild. Every derived store, embeddings, abstracts, the content index, is dropped and reconstructed from the vault alone, with visible progress. At the end, the same preflight as day one, and the same answers as before, byte for byte, because the models run cold.

**9.3 The test.** Rebuild is one command with no decisions inside it. The rebuild gate proves the result identical. A user who has lost everything except their vault folder has lost nothing.

---

## 10. The journeys that must not exist

Absences are design decisions too, and these three are permanent:

1. **There is no send journey.** Nothing in any surface dispatches a message, accepts an invitation, or posts anywhere. The strongest affordance that can ever appear is "staged as a draft in your mail client," and the journey ends there by construction.
2. **There is no ambient capture journey.** Nothing arrives in the vault that the user did not bring, point at, or steer. No surface offers to watch a folder, a mailbox, or a calendar on its own.
3. **There is no silent change journey.** Nothing meaning-bearing enters memory without ratification, and nothing changes in the night without a journal entry and a revert. If the user cannot find out what happened, it must not have happened.

---

## 11. What the wireframes owe this document

One wireframe per surface: the chat pane, the inbox, the morning view, plus the Begin sequence. Each wireframe must walk every journey step that touches its surface, including the variants, the refusal, the failed conversion, the rejected proposal, and each carries the journey tests it must pass. Timing is part of the design: the chat wireframe is drawn against streaming seconds, not instant answers, because the fixtures it will run on carry recorded token timing and the mock lies about nothing except the data.

# Cairn Design

> **Superseded, 2026-08-13.** This draft described Cairn as a standalone application and was never reviewed. The product was redefined before review by [THESIS.md](THESIS.md), which is ratified and authoritative. This file is kept as a record of the path taken; nothing in it should be built from.

*Draft 1. Numbered for markup. Nothing here is built yet.*

The roadmap says what and when. This says how, and what Cairn actually is.

---

## 1. What the proof of concept settled, and what it cannot carry

### 1.1 Settled, and kept

**Grounded answering with a receipt works.** Retrieval plus constrained synthesis plus a citation for every claim is the product, and it does what it promises. Nothing in this design touches it.

**Reach for a model last.** The deterministic front door took a greeting from 96 seconds to zero by answering from a template instead of a language model. The no-hope floor does the same for questions with nothing to find. This principle earns its keep and gets extended, not replaced.

**The contract lives in the engine.** Interfaces cannot edit the grounding rules, cannot supply a system prompt, and cannot change sampling. This is both the quality guarantee and the injection defence, and it is the single best structural decision in the codebase.

**Gates, not claims.** Twenty checks, each verified to fail. Kept, extended, and split so most of them can run without a model server.

### 1.2 What it cannot carry

**1.2.1 Three manual steps is not a product.** Saving a document today means dropping a file in a folder, running one script to convert it, and running a second to index it. Every one of those is a place to forget, and none of them tells the user what happened. A product does this itself and reports what it did.

**1.2.2 The borrowed interface has a hard ceiling at one surface.** Emulating a local model means the only thing Cairn can return is a string. That is why citations currently ride inside the answer text, which the design notes call out as a workaround rather than a preference. The consequence is bigger than cosmetics: no clickable sources, no coverage view, no save flow, no place to put a prepared brief. **Chat is the only one of three promised surfaces that fits through that pipe, and it fits in degraded form.** This is the decision that has to change, and section 6 argues it properly.

**1.2.3 There is no document lifecycle, and the flagship use case depends on one.** The second scenario in the product description is "the policy changed, again," and it promises that if two documents disagree, Cairn says so and shows both. Nothing implements this. Document identity is a hash of the file path, so version two of a policy saved under a new name is an unrelated document. Both versions are retrieved, nothing knows they are related, nothing surfaces the conflict, and the older one can win on distance alone. Section 4 fixes this and it is the largest change in this document.

**1.2.4 Retrieval is one channel, and it is the wrong one for half the questions.** Vector search is strong on paraphrase and weak on exact tokens: statute numbers, policy names, dates, people, acronyms. Those are precisely what real questions contain. The project's own measurements say so: the best real answerable question scored 0.754, and the "Strong" band begins at 0.80, so almost nothing real ever registers as strong. **That is a retrieval quality signal, not a threshold calibration problem.** Recalibrating the labels first would relabel weak retrieval as strong and hide the defect. Section 5 proposes the fix, and it costs no model call.

---

## 2. New evidence that changes the priorities

The engine was run on a Mac for the first time today, against the same frozen benchmark used on the original Windows machine.

| Frozen benchmark, warm | Windows, best recorded | Windows, most recent | macOS, today |
| --- | --- | --- | --- |
| Time to first token | 0.8s | 1.1s | **0.15s** |
| Total | 9.0s | 16.5s | **1.87s** |
| Tokens per second | 7 | 4 | **36.5** |

Same model, same prompt, same evidence. This machine is roughly **nine times faster** on generation throughput than the original machine at its worst, and five times faster than it at its best.

Two conclusions follow.

**2.1 Latency is substantially a deployment problem, not a product problem.** The 182 second answer was very likely 15 to 25 seconds of generation on adequate hardware. The suspected acceleration fallback on the Windows machine is not a 43 percent regression against a good baseline, it is a bad baseline getting worse. Horizon 1 should still build the realistic-evidence benchmark, because the small frozen prompt cannot measure what a user feels, but the code-level latency levers drop sharply in priority.

**2.2 The honest framing is a hardware floor, not a code optimisation.** Cairn should state what it needs to feel fast and measure itself against that, rather than contorting the design around one slow machine. Section 7.4 covers what happens when the hardware is not there.

---

## 3. The shape

One long-running service. Two internal halves. Three surfaces. Two ways in.

```
  sources/            ┌─────────────── Cairn service ───────────────┐
  (watched)  ────────▶│                                             │
                      │   Librarian            Answerer             │
                      │   watch, convert       route, retrieve,     │
                      │   chunk, embed,        compose, cite,       │
                      │   version, report      check                │
                      │        │                    ▲               │
                      │        ▼                    │               │
                      │   ┌─────────────────────────┴───────────┐   │
                      │   │ cairn.db                            │   │
                      │   │ documents / versions / chunks       │   │
                      │   │ vec_chunks (semantic)               │   │
                      │   │ fts_chunks  (exact terms)           │   │
                      │   └─────────────────────────────────────┘   │
                      └──────────────────┬──────────────────────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
             Cairn's own UI        HTTP/JSON API      Model-protocol face
             Chat, Save, Prepare   (the real one)     (integration only)
```

**The Librarian** keeps the index true. It watches, converts, chunks, embeds, tracks versions, and reports what it did. It never talks to a user and never calls a generation model.

**The Answerer** turns a question into a cited answer. It routes, retrieves, composes, and checks. It never writes to the corpus.

Splitting them matters because they fail differently and are gated differently. The Librarian is deterministic and must be idempotent. The Answerer involves a model and must be constrained.

---

## 4. Documents, versions, and the conflict case

This is the largest change and the one that makes the flagship promise real.

### 4.1 The model

- **document**: the thing itself. "Travel Policy." Stable identity that outlives any file.
- **version**: one ingested file belonging to a document. Carries the path, content hash, source date, ingest date, records status, and whether something has superseded it.
- **chunk**: belongs to a version, not to a document.

Retrieval searches **current versions by default**. Superseded versions stay indexed and stay searchable, but only when the question asks for history.

### 4.2 How Cairn learns that two files are the same document

Not by magic. **The user says so, and Cairn makes it a single click.**

When a new file is saved, the Librarian looks for a likely predecessor by filename similarity and content overlap. If it finds one, Save asks:

> This looks like a new version of **Travel Policy** (saved 2026-03-14). Replace it, or keep both as separate documents?

Replace marks the old version superseded and keeps it searchable. Keep both creates a second document. Doing nothing keeps both, because the safe default is never to hide something the user saved.

This is deliberate rather than automatic for the same reason saving is deliberate: it knows only what you give it. It also gives the Save surface something real to do, which section 7.2 builds on.

### 4.3 The fourth grounding case

The contract currently has three cases: answer, on topic but silent, refuse. Real corpora produce a fourth, and it is the one the product description promises to handle.

**Case 4. The passages disagree.** Two current versions of different documents make incompatible claims about the same thing. Cairn states that the saved material conflicts, presents both positions, cites each, gives the date and status of each source, and **does not adjudicate**. Choosing between two authorities is the user's job and Cairn has no basis for it.

The gate for this case follows the pattern the others established: build evidence that genuinely conflicts, confirm the model produces both sides with citations, confirm it does not pick a winner, and confirm it does not fall back to the refusal.

### 4.4 Why this is not premature

It changes the schema, so designing it after the fact means migrating a corpus rather than defining one. It is also the difference between a search tool and something worth trusting with policy: a tool that confidently quotes last year's rules is worse than no tool, because the user has no way to know.

---

## 5. Retrieval

### 5.1 Two channels, fused

1. **Semantic**: nearest neighbour over chunk embeddings. Strong on paraphrase, weak on exact tokens.
2. **Exact**: BM25 over chunk text and headings, using SQLite's built-in full text search. Strong on identifiers, names, numbers, and acronyms. Already available, no new dependency.

Fuse the two ranked lists with reciprocal rank fusion. It needs no weight tuning, no score normalisation between incomparable scales, and it degrades gracefully when one channel returns nothing.

Filter to current versions, then take the top passages.

### 5.2 Strength becomes agreement, not distance

Today the strength label is a function of one number, the top vector distance, and the observed data says that number discriminates poorly. With two independent channels there is a better and cheaper signal: **do they agree?**

A passage surfaced near the top by both semantic and exact search is strong evidence. A passage surfaced by only one is worth showing and worth labelling as such. This is honest, free, and it explains itself to the user in a way a distance never did.

### 5.3 Calibration comes after, not before

The backlog currently sequences threshold recalibration ahead of retrieval work. That order should flip. Calibrating labels against weak retrieval produces labels that faithfully describe weak retrieval. Fix the channel, then calibrate on the data it produces.

### 5.4 Deliberately not in this design

Query expansion, hypothetical document embeddings, and local rerankers are all real techniques and all add a model call to a path that is currently free. None of them is justified until hybrid retrieval has been measured and found wanting.

---

## 6. Interfaces

### 6.1 The decision this reverses

The existing record says a third-party chat client is the face and Cairn is the engine behind it. That was correct when it was decided. It was decided for a machine where installing software was hard, a chat client was already present, and the fastest route to a usable interface was to borrow one. The intervention ladder said take the cheapest rung that holds, and that rung held.

**The premise has expired.** The project is now developed on a machine with no such restriction, distributed as open source to people who will install a thing on purpose, and committed to three surfaces rather than one. Two of those three cannot exist behind a protocol that carries only a string.

### 6.2 What replaces it

**Cairn's own local web interface is the product interface.** It already exists, already streams, already renders citations and a strength label. It is cross-platform without packaging work, it can render everything the protocol face cannot, and investing in it is a smaller step than any alternative.

**A first-class HTTP and JSON API sits under it.** Structured answers, structured citations, structured corpus state. The web interface is its first consumer, which keeps it honest.

**The model-protocol face stays, demoted to an integration.** It is genuinely useful for people who live in a particular editor and want Cairn there, it is about sixty lines, and it costs nothing to keep. It is no longer the plan for how anyone gets a good experience. It is documented as what it is: chat only, receipt inside the text, no version awareness, no save, no prepare.

### 6.3 What this does not mean

Not a desktop application. Not a packaged binary. Not a new framework. A local service with a browser interface, which is what it already is, taken seriously.

---

## 7. The three surfaces

### 7.1 Chat, restructured around what is actually fast

Retrieval takes about 0.2 seconds. Generation takes tens of seconds. Today the user waits for generation to see anything, which means the whole experience runs at the speed of its slowest part for no reason.

**The answer renders in two stages.**

**Stage one, immediately.** The passages Cairn found: source, heading, date, version status, and why each was surfaced. This is the evidence, and it is often enough on its own. If retrieval found nothing worth composing from, the user knows in under a second and no generation happens at all.

**Stage two, streaming above it.** The composed answer, citing into the passages already on screen.

This is a reframe as much as an optimisation. Cairn becomes a finder that also composes, rather than a chatbot that cites. That is truer to the first rule, it degrades gracefully when the model is slow or absent, and it makes the tool feel fast independently of any latency work.

Follow-up questions retrieve fresh every time. Earlier turns help interpret the question and never become a source of facts.

### 7.2 Save, made a real act

Drop a file, or pick one. Then watch it happen: converted, chunked, indexed, searchable, with counts at each step and a plain statement of anything that failed and why.

Save also owns the two decisions only a human can make: **is this a new version of something I already have** (section 4.2), and **what is its records status**.

**Coverage lives here rather than as a fourth surface.** What Cairn holds, how fresh each document is, what has been superseded, what failed to convert, what is not yet indexed. Without it, silence is not diagnosable, and a user cannot tell "nothing was saved about this" from "something is broken."

### 7.3 Prepare, version one

A recipe is a markdown file in the vault describing what a brief should contain. Point it at a subject, a project, or a meeting series. Cairn assembles the brief from saved material: what was decided, what was committed, what is open, every line cited and dated. Output optionally saves back to the vault as a document like any other.

Recipes are markdown on purpose. A user can read one, copy one, and change one without touching code, which is what makes Prepare general rather than a fixed feature.

### 7.4 When the hardware is not there

Given section 2, Cairn should say plainly what it needs and behave well when it does not have it. On first run it measures the local models and reports what to expect. If generation is very slow, stage one still lands in under a second, and Cairn offers evidence-only mode: the passages, ranked and cited, with no composed prose. **Evidence-only is a legitimate way to use Cairn, not a failure state.** It also happens to be the mode that satisfies rule one most completely.

---

## 8. Providers

Ollama endpoints are currently hardcoded in three files. Two interfaces replace that:

- **Embedding provider**: text in, vectors out, with a declared dimension the index gate checks.
- **Generation provider**: messages in, a token stream out.

Ollama is the first and default implementation. Everything stays local. The point is not vendor choice, it is that a working installation should not depend on one project's tag naming, and swapping the generation model should not mean editing source.

---

## 9. Beyond documents, sketched only

Not designed here, but the schema should not preclude it.

Notes and meetings introduce material Cairn creates rather than mirrors, which is where records obligations attach and where a review with whoever owns records policy is a prerequisite rather than a formality. People and projects introduce entities and mentions: who is involved, what is committed, what is waiting on whom. Both want a **mentions** relation between a chunk and an entity, which is additive to the schema in section 4 and does not change it.

Deliberately unresolved: whether entity extraction happens at ingest, at query time, or on demand. That decision needs the documents pillar finished and a real corpus behind it.

---

## 10. What this design refuses

Unchanged from the product commitments, restated because a design document is where they get quietly broken.

1. Nothing leaves the machine. No cloud inference, no telemetry, no remote fetch of user content.
2. No receipt, no answer. Including the front door, where the receipt says retrieval was not run.
3. It knows only what it is given. No ambient collection, no watching a mailbox or a calendar.
4. It reads, finds, and cites. It does not act on other systems.
5. It does not measure people, and never records tone, affect, or assessment.
6. **New: it does not adjudicate.** When sources conflict, Cairn shows the conflict and cites both. Deciding which authority wins is the user's job.

---

## 11. Open questions

1. **Does the Librarian watch continuously, or run on demand?** Watching is a better product and edges toward ambient collection, which is a promise. The likely answer is that it watches one folder the user explicitly designated, which stays deliberate, but the wording of the promise needs care.
2. **Does chunking change?** Fixed 2000 characters with heading awareness is proof-of-concept grade. Hybrid retrieval may make it matter less. Worth measuring before touching.
3. **Where does a prepared brief live?** Writing it back into the vault makes it a document Cairn can then cite, which is either elegant or a way to launder a summary into evidence. Leaning toward saving it with a flag that keeps it out of retrieval unless asked for.
4. **What is the reference hardware?** Section 2 says Cairn should measure itself against a stated floor. That floor needs a number.

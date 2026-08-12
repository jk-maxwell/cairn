# Cairn Roadmap

*What Cairn is, what it can do today, and what it has to earn next.*

Cairn is a local, private tool that answers questions from the documents you saved, and cites a source for every claim. It runs entirely on your machine. It has no cloud service, no account, and no path for your material to leave.

This roadmap is written against evidence. Every number below was measured, not estimated, and every problem named here was found by using the tool rather than by imagining how it might fail.

---

## Where Cairn is today

The engine works. The product around it does not exist yet.

**Working now.** A document goes in and a cited answer comes out. Conversion and chunking are deterministic and re-runnable. Retrieval is nearest-neighbour search over local embeddings. Synthesis is constrained to the retrieved passages, and every answer carries a receipt naming the passages it stands on and how close the match actually was. A deterministic front door answers greetings and questions about the tool itself without calling a model at all. A local-model protocol surface lets any OpenAI-compatible or Ollama-compatible chat client become the interface, so the tool has a usable face without owning one.

**Measured, on the original development machine.**

| Quantity | Measurement |
| --- | --- |
| Real question, full answer | 80 to 182 seconds |
| Greeting, before the front door | 96 seconds |
| Greeting, after the front door | 0.0 seconds, no model call |
| Question with nothing to find | 0.2 seconds, no model call |
| Frozen benchmark, warm, best observed | 0.8s to first token, 9.0s total, 7 tokens/sec |
| Frozen benchmark, warm, most recent | 1.1s to first token, 16.5s total, 4 tokens/sec |
| Gates in the preflight suite | 20 |

**Retrieval distances observed so far.** Real answerable questions have landed at 0.754, 0.843, and 0.891. Non-questions have landed at 1.055 and 1.094. Nothing has yet been observed between 0.89 and 1.05.

**Not built.** Saving a document means dropping a file in a folder and running two scripts. There is no way to see what the tool holds or how fresh it is. There is no way to ask it to prepare anything. It has run on exactly one machine, on one operating system, against one corpus.

---

## What the experiment taught

Cairn was built across three sessions in a deliberately awkward way: a human carried every file between the editor and the machine by hand. That method is now retired. Three things it produced are worth keeping.

**1. Determinism before intelligence.** The cheapest answer is the one you never generate. A greeting used to cost 96 seconds because the tool embedded it, retrieved five irrelevant passages, and asked a language model to explain why statutes do not address salutations. Answering it from a checked-in template instead took the cost to zero. The same reasoning gave the no-hope distance floor: when retrieval already knows there is nothing to find, spending 90 seconds having a model discover that is waste. Reach for a model last, not first.

**2. The contract lives in the engine, and the interface is disposable.** Serving a standard local-model protocol meant a chat client that had not been updated in two years became a working interface in a single session, with no changes to it. The client believes it is talking to a language model. It is talking to retrieval, grounded synthesis, and citations. Because the client's system prompt, sampling settings, and model choice are discarded at the door rather than merged, no interface can weaken the grounding rules, and no text inside a document can talk its way into becoming an instruction.

**3. Gates, not claims.** Nothing is considered working because it was written carefully. It is considered working because a check that has been verified to fail when the property breaks now passes. This caught real defects that reading the code did not: a benchmark that silently changed its own payload and made every historical measurement incomparable, a refusal that technically contained the right sentence while reading as two paragraphs of hedging, and an answer that cited a sixth passage when only five existed.

---

## Horizon 1: fast enough to reach for

**The outcome.** Someone reaches for Cairn during a meeting instead of saying "I'll look that up."

**Why this is first.** Nothing else matters at three minutes per answer. Every other improvement is invisible behind that wait, and a tool nobody reaches for cannot teach us anything, because the disappointments that drive this roadmap only appear in daily use.

**Exit gate.** A real question over a realistic corpus returns a cited answer in under 10 seconds on reference hardware, measured by a committed benchmark and logged to a file, on three consecutive runs.

**The work, in order.**

1. **Build a benchmark that can see the problem.** The current frozen benchmark runs about a tenth of realistic evidence size, so it cannot measure the latency a user actually feels. A second frozen prompt at realistic evidence size, roughly 10,000 characters, comes first because everything after it is guesswork without a measuring stick.

2. **Rule out the configuration layer before touching the code.** Generation is running at roughly 57 percent of its own recorded baseline, with the same model, question, evidence, and prompt. A hardware acceleration log line appeared between the two measurements. Check the acceleration environment, the runtime version against the recorded baseline, and whether the model is placed on the GPU or the CPU during a run. If the cause is configuration, then retrieval breadth and generation limits are the wrong levers and pulling them would hide the real problem.

3. **Then, and only then, the latency levers.** Retrieval breadth, generated token limits, context sizing, and prompt length are all candidates, and each one trades away something real. None of them is worth spending until step two says where the time is actually going.

4. **Fix the receipt defect and gate it properly.** In the shared answer path, the retrieval-strength description is overwritten by the citation-integrity check before the receipt is assembled, so every clean answer on the protocol interface renders its strength line truncated and every flagged answer prints its warning twice. The existing check misses this because it asserts only that the line begins correctly. The fix is small. The gate that asserts the whole sentence is the point.

---

## Horizon 2: installable by someone who is not the author

**The outcome.** A person who has never seen this repository installs it and gets a cited answer from their own documents, without help.

**Why this is second.** This is the threshold between a personal experiment and a product. It is also the only honest way to find out whether the design holds anywhere other than the machine it was born on.

**Exit gate.** A person on macOS, Windows, or Linux goes from clone to a cited answer in under 15 minutes, following only the README, verified by someone who did not write it.

**The work.**

1. **Package it.** A project file with pinned dependencies, an installable package rather than loose scripts at the root, one command to set up and one command to run. Today the instructions assume a specific Python launcher, a specific path separator, and that the reader already knows which of three scripts to run in which order.

2. **Make it genuinely portable.** The code carries assumptions from the machine it was written on, including a Windows-only file launcher and Windows path conventions in its own usage strings. Every one of these needs finding and removing, and continuous integration on all three operating systems is what keeps them from coming back.

3. **Separate the tool from its first corpus.** The ingestion step derives canonical web links by pattern-matching filenames against one specific jurisdiction's statute naming scheme. That belongs in a plug-in resolver with the original as a worked example, not baked into the core.

4. **Ship something to ask questions about.** A small sample corpus of generic documents, so a new user reaches a cited answer in the first few minutes rather than after they have found, converted, and indexed material of their own.

5. **Split the preflight suite.** Some gates need a running model server and some do not. The offline ones should run in continuous integration on every change. The online ones stay as the local preflight they are today.

---

## Horizon 3: three surfaces, not one

**The outcome.** The tool does the three things it promises, rather than one of them well and two on paper.

**Exit gate.** Saving, asking, and preparing are all usable without the command line, for documents.

**The work.**

1. **Save, made real.** A watched inbox folder and an explicit process step that reports exactly what was converted, what was chunked, what was indexed, and what failed. Saving is currently three manual steps and a leap of faith.

2. **A coverage view.** What the tool holds, how fresh it is, and what state each document is in. Without this, silence is not diagnosable: a user cannot tell the difference between "nothing was saved about this" and "something is broken."

3. **Prepare, version one.** Ask the tool to assemble a brief on a topic, a project, or a meeting series, from everything saved: what was decided, what was committed, what is still open, every line cited and dated.

4. **Conversation as context.** Follow-up questions currently drop the earlier turns and log the drop. Earlier turns should help interpret the question without ever becoming a source of facts. Every turn still retrieves fresh, still cites, and still shows its strength.

5. **Recalibrate on accumulated data.** The strength thresholds and the no-hope floor were set from a handful of points, and the evidence so far suggests the top band is catching almost nothing real. A body of daily-use distances is what should set them, not a comment in a file.

---

## Beyond the horizons

These are real and they are next, but they are not scheduled, because each one depends on something the project does not yet control.

**Notes and meetings.** What was decided and what was promised, answerable. This is the capability with the highest daily value and it carries obligations that documents do not, because the tool would be creating working records rather than reflecting existing ones. **A review with whoever owns records and privacy policy in your organization is a hard prerequisite, not a formality.** Self-authored notes are the path in. Meeting transcripts sit behind platform policy that no amount of local code can open.

**People and projects.** How the material connects: who is involved in what, which threads are live, what is waiting on whom.

**Related material.** A "what is semantically near this" view, which the existing index already supports in about twenty lines. Deliberately deferred until daily use proves anyone wants it. It will not be built because a comparable tool has it.

---

## Non-goals

These are not "later." They are commitments about what the tool will not become, and they are the reason it can be trusted with working material at all.

1. **Nothing leaves the machine.** No cloud service, no account, no telemetry, no remote inference, no exceptions. This is the first constraint and every other decision yields to it.
2. **It knows only what it is given.** No background collection, no ambient monitoring, no watching a mailbox or a calendar or a screen. Every document it holds is there because someone deliberately put it there.
3. **It reads, finds, and cites. It does not act.** No writing to other systems, no sending messages, no taking actions on anyone's behalf.
4. **It does not measure people.** Distillation extracts decisions, commitments, action items, and open questions. It never records tone, affect, or any assessment of an individual. This is enforced by what the code is built to extract, not by policy.
5. **No receipt, no answer.** If the tool cannot show you where a claim came from, it does not make the claim.

---

## How this roadmap works

Horizons are sequential, and each one ends at a gate that can fail. Work inside a horizon is ordered but negotiable. Anything that has not been measured is a hypothesis, and anything that has been measured beats an opinion about it.

The weekly question stays the one the project started with: **can Cairn answer something today that it could not answer last week.**

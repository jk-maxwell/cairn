# Contributing to Cairn

Thanks for looking. This project has a small number of rules that are unusual enough to be worth reading before you write any code.

## The house rule: gates, not claims

**Nothing lands because it was written carefully. It lands because a check proves it works.**

Every behavioural change ships with a gate in `selftest.py`, and every new gate must be **verified to fail** before it is trusted. Break the property on purpose, watch the gate go red, then fix it and watch it go green. A gate that has never been seen to fail is decoration.

This is not process for its own sake. Three real defects got through careful reading and were caught only by a gate that could fail:

- A benchmark that imported the live system prompt, so editing the grounding rules silently changed what was being measured and made every historical number incomparable.
- A refusal that contained the correct sentence and therefore passed, while actually reading as two paragraphs of hedging in front of it. The fix was a gate asserting the reply *equals* the refusal rather than *contains* it.
- An answer that cited a sixth passage when only five existed, with nothing in the system noticing.

If you find yourself writing "this obviously works," that is the moment to write the gate.

## Running the checks

```bash
python selftest.py        # 20 gates: dependencies, retrieval, grounding, protocol, speed
python tools/mapcheck.py  # every code file must be documented in MAP.md
```

Both must be green. `selftest.py` needs Ollama running with the models pulled, because several gates put a real question to a real model. Splitting the offline gates out so they can run in continuous integration is [Horizon 2](ROADMAP.md) work and would be a genuinely useful contribution.

## The constraints that are not up for negotiation

These are the reason the tool can be trusted with someone's working material. A change that weakens one of them will not be merged, however good it is otherwise.

1. **Nothing leaves the machine.** No cloud inference, no telemetry, no analytics, no crash reporting, no remote fetch of user content. If a feature needs the network for anything other than the local model server, it is the wrong feature.
2. **No receipt, no answer.** Every claim carries a citation, and every reply carries a line stating what the retrieval was worth. A front-door reply that consulted no evidence still carries a receipt, and that receipt says plainly that retrieval was not run. Satisfying this rule by omitting the line is not satisfying it.
3. **The grounding contract lives in the engine.** An interface cannot edit it. Client-supplied system prompts, sampling settings, and model choices are discarded rather than merged. This is also the injection defence: text inside a document that a client echoes back as an instruction cannot tell Cairn to stop citing. Keep it structurally impossible rather than merely prohibited.
4. **Answers come from evidence. Warmth comes from templates.** Every word on a front-door lane is authored and checked into the repository, and every number on it is read from the database at answer time. Nothing there is generated, so nothing there can make an unsupported claim about the corpus.
5. **Reach for a model last.** If a question can be answered deterministically, answer it deterministically. The front door and the no-hope distance floor exist because the cheapest answer is the one never generated.

## Keeping the map true

`MAP.md` documents every code file and the models the code actually uses. `tools/mapcheck.py` fails if a file is missing from it, or if the map claims a model the code does not use. A new file gets its row in the same change that creates it.

## Style

- Plain language. Write for someone smart who does not work on this.
- Comments explain **why**, especially when the reason is a defect that was actually observed. Several comments in this codebase are the only record of a bug that cost real time, and they are load-bearing in the sense that removing them would let someone reintroduce the bug in good faith.
- Avoid em-dashes in prose and documentation.
- Prefer measured quantities over adjectives. "57 percent of baseline" beats "noticeably slower."

## Reporting a problem

Useful reports contain what you asked, what came back, and what you expected instead. If it is a latency problem, include the wall-clock number and the size of the evidence. If it is a grounding problem, the exact answer text matters, because the defect is usually in what the model wrote rather than in what the code did.

**Never paste your own document content into an issue.** Reproduce it with material you are happy to publish.

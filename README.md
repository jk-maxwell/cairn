# Cairn

**Everything that crossed your desk. One question away.**

Cairn answers questions from the documents you saved, and cites a source for every claim it makes. It runs entirely on your own machine.

A cairn is a small stack of stones that marks a trail. Each one is built from what was already there, and it exists so the traveler can find the way. This tool works the same way: it takes what you have already collected and turns it into a marker you can navigate by.

> **Status: early.** The engine works and is gated by a 20-check preflight suite. The product around it is not built yet. It has run on a small number of machines, answers currently take longer than they should, and installing it is harder than it needs to be. See the [Roadmap](ROADMAP.md) for exactly what is true today and what is next. If you want something finished, come back later. If you want to shape it, now is a good time.

---

## Sound familiar?

The decision was made in a meeting three weeks ago. You remember deciding. You do not remember what was decided, and neither does anyone else, and the notes are somewhere.

The policy changed. Again. The current version lives on one of four sites, and the person who understood it just moved teams.

Someone promised something. Possibly you. The promise is real, the deadline is real, and the only record of it is in somebody's head.

None of this is anyone's failure. It is what work looks like in a large organization moving fast: knowledge travels by voice, guidance changes without ceremony, and memory does the bookkeeping. Cairn is not an attempt to change that. It is built to work inside it.

## What Cairn is

Cairn does for your working files what a calculator does for arithmetic: a job you could do by hand, done in seconds instead of an afternoon, so your attention goes where it is actually needed.

You save the material that crosses your desk: documents, policies, notes. When you need something, you ask in plain language. Cairn finds the relevant passages in what you saved and composes an answer from them, with a citation for every claim showing the exact source, passage, and how close the match was. If what you saved does not contain the answer, it tells you so plainly instead of guessing.

That is the whole tool. It reads, it finds, it cites. It does not act, decide, or do anyone's job.

## Private by design

This comes before the features because it matters more than the features.

**Everything stays on the device.** Cairn runs entirely on the computer it is installed on. No cloud service, no account, no subscription, and no data transmitted anywhere. The software that reads and summarizes runs locally, through [Ollama](https://ollama.com).

**It knows only what you save.** Cairn sees nothing by default. Every document it holds is there because you deliberately put it there, one file at a time. There is no background collection and no ambient monitoring.

**It answers only from what it holds.** Every answer is built strictly from your saved material and cites it. No outside sources, no filled-in gaps, no invented content.

To be equally clear about what Cairn does not do: it does not record meetings, read your email or messages, monitor activity, evaluate people, take actions in other systems, or send information anywhere. It is a filing cabinet that answers questions, not a camera and not a robot.

## Three rules it lives by

1. **No receipt, no answer.**
2. **Nothing leaves the machine.**
3. **It knows only what you give it.**

---

## Getting started

> Packaging and setup are [Horizon 2](ROADMAP.md#horizon-2-installable-by-someone-who-is-not-the-author) work and are rougher than they should be right now. These steps assume you are comfortable at a command line.

**You need:** Python 3.10 or newer, and [Ollama](https://ollama.com) running locally.

```bash
# 1. Models (these must exist before anything else works)
ollama pull nomic-embed-text
ollama pull qwen3:4b-instruct-2507-q4_K_M

# 2. Dependencies
python3 -m venv .venv
./.venv/bin/pip install sqlite-vec 'markitdown[all]'

# 3. Save some documents
mkdir -p sources
cp ~/some-policies/*.pdf sources/
./.venv/bin/python ingest.py     # convert and chunk
./.venv/bin/python index.py      # embed into the local vector index

# 4. Check everything is wired up (21 gates)
./.venv/bin/python selftest.py

# 5. Ask
./.venv/bin/python ask.py        # web interface on http://127.0.0.1:8765
./.venv/bin/python ask.py --ask "what did we decide about the exception process?"
```

Two things that will bite you, both verified on a clean macOS install:

- **Quote `'markitdown[all]'`.** Unquoted, zsh treats the brackets as a glob and the command fails before pip sees it. Plain `markitdown` installs without the converters for PDF, Word, PowerPoint, and Excel, so every file type in the supported list except plain text and markdown will silently fail to convert.
- **Save and index before you run the preflight.** The preflight checks that the database has vectors in it, so on a fresh install with an empty corpus it correctly fails at the third gate. That is the gate doing its job, not a broken install.

### Using your own chat client

Cairn serves the OpenAI-compatible and Ollama-compatible local model protocols, so most chat clients can be its interface. Point the client at `http://127.0.0.1:8765` and select the model named `cairn`.

The client's system prompt, sampling settings, and model choice are **discarded, not merged**. The interface is swappable and the grounding rules are not. Citations and the retrieval-strength label ride inside the answer text, so the receipt survives whatever interface you put in front of it.

---

## How it works

```
sources/     documents you deliberately saved
   |
   |  ingest.py    conversion and heading-aware chunking. Deterministic, re-runnable.
   v
vault/       converted markdown, human-readable
   |
   |  index.py     embeds passages locally (nomic-embed-text, 768 dimensions)
   v
cairn.db     SQLite plus sqlite-vec for nearest-neighbour search
   |
   |  frontdoor.py  greetings and questions about Cairn itself are answered from
   |                templates and SQL, with no model call at all
   |
   |  ask.py        retrieval, then synthesis constrained to the retrieved passages,
   v                with citations, a retrieval-strength label, and a check that no
                    answer cites evidence it was never given
127.0.0.1:8765      web interface, plus OpenAI- and Ollama-compatible protocols
```

Full detail in [MAP.md](MAP.md). The reasoning behind each design choice, dated and append-only, is in [docs/DECISIONS.md](docs/DECISIONS.md).

## Contributing

Cairn has one unusual house rule: **nothing lands because it was written carefully, only because a gate proves it works.** A gate that has never been seen to fail is not yet a gate. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache License 2.0](LICENSE). Permissive, with an explicit patent grant, so it can be adopted inside organizations that need to review it before saying yes.

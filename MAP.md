# MAP

*What exists, where it lives, and how data flows. If it is not on this map, it does not exist. `tools/mapcheck.py` enforces that for code files, and also checks that this document names the models the code actually uses.*

## Data flow

```
sources/            documents deliberately saved for ingestion
   |
   |  ingest.py     conversion via MarkItDown, heading-aware chunking.
   |                Deterministic and re-runnable: a file is reconverted only
   v                when its content hash changes.
vault/              converted markdown, human-readable and linkable
   |
   |  index.py      embeds pending chunks via local Ollama
   v                (nomic-embed-text, 768 dimensions, asserted at runtime)
cairn.db            SQLite: documents, chunks, vec_chunks (sqlite-vec),
   |                plus a records status column per document
   |
   |  frontdoor.py  three deterministic lanes decided with no model call:
   |                chatter, holdings, and capability are answered from
   |                authored templates plus SQL and never reach retrieval.
   |                Everything else falls through to the retrieval path.
   |
   |  ask.py        retrieval (top-k nearest neighbour) and evidence-only
   v                synthesis (qwen3:4b-instruct-2507, temperature 0, a
                    three-case grounding contract: answer / on topic but
                    silent / fixed refusal), plus a retrieval-strength label
                    and a citation-range check on the assembled answer.
                    Above the no-hope distance floor the model is skipped
                    entirely and the nearest headings travel instead.
127.0.0.1:8765      two faces over one engine:
                      /             built-in web interface, streamed,
                                    citations, strength label
                      /v1/...       OpenAI-compatible protocol; a chat
                                    client selects the model "cairn"
                      /api/...      Ollama-compatible protocol; same engine,
                                    different dialect
```

On the protocol faces, the client's system prompt, sampling settings, and model choice are discarded at the door, and citations plus the strength label ride inside the answer text. The interface is swappable. The contract is not.

## Files

| Path | Purpose |
| --- | --- |
| `config.py` | Paths, chunking parameters, `EMBEDDING_DIM`, supported file types, default records status |
| `db.py` | SQLite schema (documents, chunks) and connection; WAL mode; idempotent migration |
| `ingest.py` | `sources/` to `vault/` and chunk rows; content-hash change detection; source URL derivation; meeting notes get clean titles, front matter (attendees, project, topic tags), and the enrichment pass |
| `enrich.py` | Meeting-transcript enrichment via the local generation model: extraction (attendees, projects, topics, decisions, commitments), the one marked machine block on each meeting note, the distillation draft in `Inbox/`, and the derived index notes (`Cairn/Home.md`, `Cairn/Meetings.md`). Extracted names resolve through `registry.py`: ratified names become links, everything else becomes a governance proposal |
| `registry.py` | The vault-authoritative entity registry and governance queue. Ratified entity pages (`Projects/`, `People/`, `Profile.md`) ARE the registry; `scan_vault` rebuilds the DB index from them, `match` is a read-only lookup against ratified structure, `propose`/`ratify`/`reject` run the queue, `Inbox/Governance.md` is the checkbox review surface, and rollup blocks between the cairn markers are the only machine-owned region of a ratified page. `--migrate` converts a pre-governance database |
| `index.py` | Embeds pending chunks into `vec_chunks`; dry-run and reset modes; dimension gate |
| `watch.py` | Polling watcher: ingest + deletion reconcile + index on `sources/` changes; registry sync (vault scan, queue edits, rollups) on entity-page/queue edits |
| `frontdoor.py` | The deterministic lane before retrieval: chatter, holdings, and capability answered from templates plus SQL with no model call; the no-hope distance floor; the nearest-headings steering list |
| `ask.py` | Retrieval, grounded synthesis, citations, strength label, streaming web interface, local-model protocol surface (OpenAI and Ollama shapes), interview routing (/interview, /checkin), one-shot command line |
| `interview.py` | The interview engine: onboarding (/interview) and status check-in (/checkin) run in the plugin chat; flow state reconstructed from the message history via invisible markers; the model only parses answers; confirmation of the playback is the ratification and the only write path |
| `test_interview.py` | Scripted end-to-end test of the interview engine on a scratch port with a temp DB and temp vault: full canned onboarding, seeded check-in, cancel, and normal-question routing |
| `selftest.py` | Preflights the whole pipeline against real models. Twenty-one gates covering dependencies, retrieval, grounding, citation integrity, the front door, the registry/governance contract, the protocol surface, and a frozen-prompt speed benchmark |
| `tools/mapcheck.py` | Fails if any tracked code file is missing from this map, or if this map names models the code does not use |
| `tools/test_registry.py` | Registry/governance acceptance CLI: thirteen cases against a temp vault and temp DB with the model stubbed -- match never inserts, proposals dedupe and respect rejection, checkbox ratifies, deleted line rejects forever, re-enrichment is idempotent, rollups touch only the marked block, migrate converts a pre-governance database |

### Generated locally, never committed

| Path | Purpose |
| --- | --- |
| `cairn.db` | The index. User content. |
| `sources/` | Documents the user saved. User content. |
| `vault/` | Converted markdown. Derived user content. |
| `benchmarks.csv` | Local speed log appended by `selftest.py` (time to first token, total, tokens per second). Metrics only, no document content. |

`.gitignore` is what enforces this, not memory. See its comment block before adding an exception.

## Documentation

| Path | Purpose |
| --- | --- |
| `README.md` | What Cairn is, why it exists, and how to run it |
| `ROADMAP.md` | Measured current state, what was learned, and the three horizons ahead |
| `CONTRIBUTING.md` | The gates-not-claims house rule and the constraints that are not negotiable |
| `MAP.md` | This file |
| `docs/DECISIONS.md` | Append-only, dated record of why each design choice was made |

## Planned components

Tracked in [ROADMAP.md](ROADMAP.md). In short: a real ingestion step with a report, a coverage view, a prepare-a-brief recipe, conversation as context, and a pluggable source-URL resolver to replace the jurisdiction-specific one currently in `ingest.py`.

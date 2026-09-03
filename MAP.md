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
| `enrich.py` | Meeting-transcript enrichment via the local generation model: extraction (attendees, projects, topics, decisions, commitments), the one marked machine block on each meeting note, the distillation draft in `Inbox/`, and the derived index notes (`Cairn/Home.md`, `Cairn/Meetings.md`). The distillation system prompt unconditionally prohibits affect, tone, and assessments of individuals (docs/DECISIONS.md, 2026-07 entry), gated by `selftest.py`'s distillation gate. Extracted names resolve through `registry.py`: ratified names become links, everything else becomes a governance proposal |
| `registry.py` | The vault-authoritative entity registry and governance queue. Ratified entity pages (`Projects/`, `People/`, `Profile.md`) ARE the registry; `scan_vault` rebuilds the DB index from them, `match` is a read-only lookup against ratified structure, `propose`/`ratify`/`reject` run the queue, `Inbox/Governance.md` is the checkbox review surface, and rollup blocks between the cairn markers are the only machine-owned region of a ratified page. Every governance event is appended to `governance.csv` (entity_id hashes, never names), and `burden_stats` turns that log into the ratification-burden numbers; `--burden` prints them. `--migrate` converts a pre-governance database |
| `llm.py` | The shared generation client, and the only place that speaks both chat dialects. `config.GEN_DIALECT` selects the wire format; `chat()` takes plain messages and returns text, streamed or not, so `ask.py`, `enrich.py`, `interview.py`, and `selftest.py` never see a transport detail |
| `index.py` | Embeds pending chunks into `vec_chunks`; dry-run and reset modes; dimension gate |
| `watch.py` | Polling watcher: ingest + deletion reconcile + index on `sources/` changes; registry sync (vault scan, queue edits, rollups) on entity-page/queue edits |
| `frontdoor.py` | The deterministic lane before retrieval: chatter, holdings, and capability answered from templates plus SQL with no model call; the no-hope distance floor; the nearest-headings steering list |
| `ask.py` | Retrieval, grounded synthesis, citations, strength label, streaming web interface, local-model protocol surface (OpenAI and Ollama shapes), interview routing (/interview, /checkin), one-shot command line |
| `interview.py` | The interview engine: onboarding (/interview) and status check-in (/checkin) run in the plugin chat; flow state reconstructed from the message history via invisible markers; the model only parses answers; confirmation of the playback is the ratification and the only write path |
| `test_interview.py` | Scripted end-to-end test of the interview engine on a scratch port with a temp DB and temp vault: full canned onboarding, seeded check-in, cancel, and normal-question routing |
| `selftest.py` | Preflights the whole pipeline against real models. Twenty-six gates covering dependencies, retrieval, grounding, citation integrity, the front door, the registry/governance contract, the affect-prohibition on distillation, the protocol surface, a frozen-prompt speed benchmark, and the ratification-burden reading |
| `tools/mapcheck.py` | Fails if any tracked Python file is missing from this map, if this map names models the tracked code does not declare, or if `ask.py` carries model names of its own instead of re-exporting `config`. Reads the models `config.py` declares at module level, not the resolved values, so a gitignored `models.local.json` override cannot fail a gate about a tracked document; an active override is reported as information |
| `tools/test_registry.py` | Registry/governance acceptance CLI: fourteen cases against a temp vault and temp DB with the model stubbed -- match never inserts, proposals dedupe and respect rejection, checkbox ratifies, deleted line rejects forever, re-enrichment is idempotent, rollups touch only the marked block, migrate converts a pre-governance database |
| `tests/fixtures/affect-bait-transcript.md` | Invented meeting transcript fixture for `selftest.py`'s distillation gate: four real decision/commitment/open-question/action items alongside four bait lines carrying affect, each tagged with a unique invented marker word so the gate can detect a leak unambiguously |

### The Obsidian plugin

The second codebase. Roughly four hundred lines of TypeScript in `obsidian-plugin/`,
built with esbuild. It is the only part of Cairn the user actually looks at; everything
above is a service it talks to over HTTP.

| Path | Purpose |
| --- | --- |
| `obsidian-plugin/src/main.ts` | Entry point: registers the chat view, the ribbon icon, and the settings tab |
| `obsidian-plugin/src/view.ts` | The chat surface. Sends the conversation to `<base>/v1/chat/completions` and renders the streamed reply as markdown. It sends the whole visible history, which is what lets `interview.py` reconstruct its flow state from the transcript instead of holding a session |
| `obsidian-plugin/src/sseParser.ts` | Incremental parser for the OpenAI-compatible SSE stream. Deliberately free of any Obsidian or DOM dependency so it can be exercised under plain Node |
| `obsidian-plugin/src/settings.ts` | One setting, the engine base URL, defaulting to `http://127.0.0.1:8765` |
| `obsidian-plugin/scripts/smoke.mjs` | Node smoke test for the parser, transpiling `sseParser.ts` in memory so it tests the shipped source rather than a copy of its logic |
| `obsidian-plugin/main.js` | The esbuild bundle, committed on purpose: Obsidian loads this file directly, and a plugin that has to be built before it can be installed is a plugin most people will not install |
| `obsidian-plugin/manifest.json`, `package.json`, `tsconfig.json`, `esbuild.config.mjs` | Plugin metadata and the build |

`tools/mapcheck.py` reads tracked Python only, so nothing enforces this section. It is
kept by hand until that gate learns to read TypeScript, and that is a real gap rather
than a decision.


### Generated locally, never committed

| Path | Purpose |
| --- | --- |
| `cairn.db` | The index. User content. |
| `sources/` | Documents the user saved. User content. |
| `vault/` | Converted markdown. Derived user content. |
| `benchmarks.csv` | Local speed log appended by `selftest.py` (time to first token, total, tokens per second). Metrics only, no document content. |
| `governance.csv` | Append-only governance event log written by `registry.py` at propose/ratify/reject time: timestamp, event, entity_id hash, type, origin. No names, ever. The instrument the burden numbers are computed from; deleting it changes no behaviour. `CAIRN_GOVERNANCE_LOG` redirects it, which is how tests avoid inflating it. |
| `burden.csv` | Ratification-burden readings appended by `selftest.py`: queue depth, oldest pending, decision latency, arrival and drain rates over 7 and 28 days, proposals per document. Counts only. |

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

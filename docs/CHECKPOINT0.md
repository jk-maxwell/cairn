# Checkpoint 0 Execution Checklist: the probe

> **What this is.** The literal execution checklist used to run Cairn's first test against a
> real vault, written to be handed to an agent task by task. It is published for methodology
> transparency, not as user documentation — if you are trying to install Cairn, you want
> [README.md](../README.md) instead. It refers to local-only files that are not in this
> repository, and its gate count (20) predates the current 25.

**Draft 2. Numbered for markup.**

*Changed from draft 1: the repository's `.gitignore` was repaired before execution (inline `#` comments had silently disabled the `sources/`, `vault/`, `*.db`, `benchmarks.csv`, and `gates.txt` patterns — git treats `#` as a comment only at the start of a line) and `*.local.json` was widened to `*.local.*` so P0-9's note is actually covered. P0-6's append was fixed to put its comment on its own line for the same reason.*

*Executes Checkpoint 0 of docs/TECHNICAL_ROADMAP.md: ask the real vault from inside Obsidian, today, through borrowed chrome. Work is performed by subagents; the orchestrating model verifies every task independently before the next one starts. Each task below is written to be handed to a subagent whole: everything a task needs is inside it or inside the facts sheet, and no subagent reads project documents or fetches anything.*

---

## 1. How this checklist is executed

1. **The orchestrator** hands one task at a time to a subagent as a self-contained brief: the facts sheet (section 2, verbatim) plus the task text. Tasks run in order; P0-3 through P0-9 each depend on their predecessor.
2. **The subagent** executes exactly the task, returns the evidence named in the task, and halts at any STOP rule with a state report instead of improvising past it. Retries and judgment calls belong to the orchestrator.
3. **The orchestrator verifies** by re-running each task's verification commands itself, never by trusting the transcript. Verification is designed to cost seconds.
4. **Two human gates** exist and cannot be waived: vault confirmation in P0-2, and plugin fallback approval in P0-8.

## 2. The facts sheet (given to every subagent verbatim)

Repository: the Cairn repository root (the orchestrator supplies the absolute path in the brief), branch `main`. The Python engine at the repository root is reference code: read it freely, modify nothing.

- **Engine service**: `./.venv/bin/python ask.py` binds `127.0.0.1:8765`. Three faces: a web UI at `/`, an OpenAI-compatible protocol under `/v1/`, an Ollama-compatible protocol under `/api/`. The model a client must select is named `cairn` (alias `cairn:latest`). The server discards client system prompts, sampling settings, and model choice; citations and the retrieval-strength label ride inside the answer text.
- **CORS**: allowed origins already include `app://obsidian.md`, so Obsidian plugins can call the protocol faces without engine changes.
- **Pipeline**: documents in `sources/` are converted by `./.venv/bin/python ingest.py` into `vault/` (markdown) and chunk rows, then `./.venv/bin/python index.py` embeds pending chunks into `cairn.db`. Both are idempotent: re-runs touch only content whose hash changed. `./.venv/bin/python selftest.py` is the 20-gate preflight.
- **Local models via Ollama** at `127.0.0.1:11434`: `nomic-embed-text` (embeddings, 768 dimensions) and `qwen3:4b-instruct-2507-q4_K_M` (generation, temperature 0).
- **Exact refusal string** (assert equality, not containment): `Sorry, I was unable to find information pertaining to your question.`
- **Receipt log**: the engine logs every question with a timestamp on both faces (lines beginning `ASK`), plus lane, retrieval, and citation-count lines. Console output redirected to a file is the receipt log.
- **Never**: touch port 4001 (unrelated local service); write into the user's Obsidian vault; commit or stage anything under `sources/`, `vault/`, any `*.db`, or any probe log (`.gitignore` enforces this; verify, do not assume); send any data off the machine.
- **The real vault path is secret to the repository**: it lives only in `probe-vault.local.json` at the repository root (`*.local.*` is gitignored) and must never appear in any committed file, including this one.

## 3. P0-1: environment preflight

**Objective.** Prove the machine can run the engine before anything else is attempted.

**Commands.**

```bash
curl -s http://127.0.0.1:11434/api/tags | head -c 400        # Ollama up?
ollama list                                                   # both models present?
./.venv/bin/python --version                                  # 3.10+
./.venv/bin/pip show sqlite-vec markitdown | grep -E 'Name|Version'
lsof -nP -iTCP:8765 -sTCP:LISTEN                              # expect empty: port free
```

**Expected.** Ollama responds with a model list containing `nomic-embed-text` and `qwen3:4b-instruct-2507-q4_K_M`; Python is 3.10 or newer; both packages are installed; port 8765 is free.

**STOP if** Ollama is down or a model is missing: report which, do not pull models or start services yourself.

**Evidence to return.** The four outputs verbatim. **Orchestrator verifies** by re-running the first and last commands.

## 4. P0-2: vault discovery, human gate

**Objective.** Enumerate the Obsidian vaults on this machine and stop for the human to name the probe vault.

**Context.** Obsidian records its vaults in `~/Library/Application Support/obsidian/obsidian.json` as a map of vault ids to `{path, ts}` entries.

**Commands.**

```bash
cat "$HOME/Library/Application Support/obsidian/obsidian.json" | python3 -m json.tool
```

**Evidence to return.** The list of vault paths found, one per line, plus each vault's approximate markdown count (`find <path> -name '*.md' | wc -l`).

**STOP always.** This task ends in a report. The human names the vault; the orchestrator then writes `probe-vault.local.json` at the repository root: `{"vault": "<confirmed absolute path>"}`. No staging happens before that file exists.

## 5. P0-3: corpus staging

**Objective.** Copy the confirmed vault's markdown into `sources/` without ever writing to the vault.

**Context.** The vault path comes only from `probe-vault.local.json`. The copy preserves relative structure so citations read sensibly. The engine ingests `.md` among other types; notes are what the probe needs. `sources/` is gitignored; verify before copying.

**Commands.**

```bash
git check-ignore -q sources/ && echo IGNORED || echo "STOP: sources/ not ignored"
VAULT=$(python3 -c "import json;print(json.load(open('probe-vault.local.json'))['vault'])")
mkdir -p sources/probe-vault
rsync -a --include='*/' --include='*.md' --exclude='.obsidian/**' --exclude='*' "$VAULT/" sources/probe-vault/
find sources/probe-vault -name '*.md' | wc -l
```

**Expected.** `IGNORED`; a file count within a few percent of P0-2's count for that vault (the `.obsidian` folder accounts for small differences).

**STOP if** the gitignore check fails, `probe-vault.local.json` is missing, or rsync reports errors. Never pass `--delete` to rsync; the source vault is opened for reading only.

**Evidence to return.** The gitignore check output, the file count, and `git status --short` (expected: empty of anything under `sources/`). **Orchestrator verifies** with the same `git status` and count.

## 6. P0-4: ingest and index

**Objective.** Convert and embed the staged corpus.

**Commands.**

```bash
./.venv/bin/python ingest.py
./.venv/bin/python index.py
```

**Expected.** Ingest reports conversions with no unexplained failures (`_ingest_failures.log` appears only if something failed; read it if so). Index reports embedded chunk counts and asserts dimension 768. Both are re-runnable; a second run should report nothing new to do.

**STOP if** more than a handful of files fail conversion, or index reports a dimension mismatch: report the exact output.

**Evidence to return.** Both outputs verbatim, plus the second-run outputs proving idempotence. **Orchestrator verifies** by re-running both (cheap when idempotent) and checking `_ingest_failures.log` absence or contents.

## 7. P0-5: the twenty gates

**Objective.** Run the preflight suite against the real corpus and models.

**Commands.**

```bash
./.venv/bin/python selftest.py
```

**Expected.** All 20 gates green. The suite also appends a row to `benchmarks.csv` (local only, gitignored).

**STOP if** any gate fails: report which gate and its output verbatim. Do not modify code or data to make a gate pass.

**Evidence to return.** The full gate tally. **Orchestrator verifies** by re-running the suite.

## 8. P0-6: service launch with the receipt log

**Objective.** Start the engine so it survives the terminal and writes the receipt log the probe's evidence depends on.

**Context.** Add the probe log pattern to `.gitignore` first, under the user-content block, honoring that file's comment: it is an allow-nothing list for data, and a log of real questions is data. The comment goes on its own line above the pattern — git treats `#` as a comment only at the start of a line, so an inline comment would become part of the pattern and silently disable it. This is the only tracked-file edit in the whole checkpoint.

**Commands.**

```bash
grep -q 'probe-\*.log' .gitignore || printf '# probe receipt log: real questions, user content\nprobe-*.log\n' >> .gitignore
nohup ./.venv/bin/python ask.py >> probe-receipts.log 2>&1 &
sleep 3
lsof -nP -iTCP:8765 -sTCP:LISTEN
tail -5 probe-receipts.log
```

**Expected.** The port is listening for a python process; the log's first lines show the service banner. Stop command, for the handoff note: `kill $(lsof -t -iTCP:8765 -sTCP:LISTEN)`.

**STOP if** the port is already occupied or the log shows a traceback.

**Evidence to return.** The lsof line, the log tail, and `git status --short` showing only the `.gitignore` edit. **Orchestrator verifies** the port, then commits the `.gitignore` line after running the sensitive-term scan from section 11.

## 9. P0-7: protocol smoke tests

**Objective.** Prove both protocol faces answer with receipts before Obsidian enters the picture.

**Commands and assertions.**

```bash
# OpenAI face: model list names cairn
curl -s http://127.0.0.1:8765/v1/models | grep -o '"cairn"'

# OpenAI face: a real question streams an answer whose text includes a receipt
curl -s http://127.0.0.1:8765/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"cairn","messages":[{"role":"user","content":"What topics do my notes cover?"}]}' \
  | head -c 2000

# Ollama face: same engine, other dialect
curl -s http://127.0.0.1:8765/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"cairn","messages":[{"role":"user","content":"hello"}],"stream":false}' \
  | head -c 1000

# Refusal: nonsense must produce the exact refusal string, not a guess
curl -s http://127.0.0.1:8765/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"cairn","messages":[{"role":"user","content":"What is the capital of the planet Zorbulon?"}]}' \
  | grep -c 'Sorry, I was unable to find information pertaining to your question.'
```

**Expected.** `"cairn"` appears; the real question returns content carrying a citation or strength label in its text; the greeting returns a front-door reply whose receipt states retrieval was not run; the refusal grep returns at least 1. After the four calls, `grep -c 'ASK' probe-receipts.log` is at least 3 (the greeting resolves on the front door; it still logs).

**STOP if** any assertion fails; capture the full response body for the orchestrator.

**Evidence to return.** All four outputs plus the log grep count. **Orchestrator verifies** by re-running the refusal call and the log grep.

## 10. P0-8: Obsidian plugin, human gate on fallback

**Objective.** Put borrowed chrome in front of the engine inside the confirmed vault.

**Context.** Candidates in order; the engine speaks both dialects, so either face can be the target. All configuration happens in Obsidian's UI; the subagent's role is to write the exact configuration values and the human clicks them in, or drives a browser tool if one is available.

1. **Copilot** (community plugin id `copilot`): add a custom model, provider "OpenAI Format" or "3rd party (openai-format)", base URL `http://127.0.0.1:8765/v1`, model name `cairn`, API key any non-empty string (the engine ignores it).
2. **BMO Chatbot** (id `bmo-chatbot`): REST API connection, base URL `http://127.0.0.1:8765/v1`, model `cairn`.
3. **Any plugin with an Ollama endpoint setting**: Ollama URL `http://127.0.0.1:8765`, model `cairn` (the `/api` face answers it).

**Acceptance.** From a note in the real vault, a question typed into the plugin's chat returns a streamed answer whose text ends with the receipt block (citations and strength label survive the chrome by design), and the question appears as an `ASK` line in `probe-receipts.log`.

**STOP for the human if** candidate 1's current version has no custom-endpoint field: report what its settings actually offer and which candidate is next; the human approves the fallback before it is tried.

**Evidence to return.** The plugin used, the exact settings values, and the matching `ASK` log line (timestamp only, never the question text, in anything written to a tracked file).

## 11. P0-9: the handoff note

**Objective.** Write the two-week probe protocol into `probe-notes.local.md` at the repository root (gitignored by the `*.local.*` pattern; verify with `git check-ignore`), so the human's morning routine needs no memory of this checklist.

**Contents, complete.** How to check the engine is up (`lsof -nP -iTCP:8765 -sTCP:LISTEN`); how to start it after a reboot (the P0-6 nohup line); how to stop it; where the receipt log lives and that it is the probe's evidence; the habit bar being tested, from the ratified exit gate: real questions on most working days for two weeks, and at the end, name three answers that beat the old way of finding out; the reminder that silence is a finding, not a shame, and exactly what the probe exists to detect.

**Evidence to return.** The note's text and the `git check-ignore` confirmation. **Orchestrator verifies** the ignore status and that no tracked file gained content in this task: `git status --short` clean except any prior approved edits.

## 12. Completion and teardown

Checkpoint 0 is complete when P0-1 through P0-9 are verified and the human has the handoff note; the two-week usage phase then belongs to the human and the receipt log. Before any commit along the way, the orchestrator runs the standing sensitive-term scan over the changed tracked files and confirms zero matches. The pattern is held by the orchestrator outside the repository, on purpose: a committed copy of the pattern would name the very terms it exists to keep out.

Teardown, when the probe ends: stop the service, keep `probe-receipts.log` for the exit-gate reading, and leave `sources/probe-vault/` in place, because Checkpoint 1's recordings use the synthetic corpus, not this one, and Checkpoint 2 will want a real corpus again.

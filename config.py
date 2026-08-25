"""
Cairn configuration. All paths resolve relative to this file's directory,
so the module runs the same regardless of the current working directory.

Expected layout:
    Cairn/
      config.py   db.py   ingest.py
      sources/    (drop documents here)
      vault/      (converted markdown lands here)
      cairn.db    (created on first run)
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES_DIR = ROOT / "sources"
VAULT_DIR = ROOT / "vault"
DB_PATH = ROOT / "cairn.db"

# Local override: if vault.local.json exists at the repo root (gitignored via the
# *.local.* pattern; personal paths never belong in tracked config), its
# "vault_dir" redirects where converted notes arrive. Point it at a real
# Obsidian vault and imports become visible notes there — and the
# obsidian:// citation links ask.py builds actually resolve.
_vault_override = ROOT / "vault.local.json"
if _vault_override.exists():
    import json as _json

    VAULT_DIR = Path(_json.loads(_vault_override.read_text())["vault_dir"])

# Test override: environment variables beat everything above. This is how the
# scripted tests point a scratch server at a temp DB and temp vault without
# touching vault.local.json or the real database. Not for production use.
import os as _os

if _os.environ.get("CAIRN_DB_PATH"):
    DB_PATH = Path(_os.environ["CAIRN_DB_PATH"])
if _os.environ.get("CAIRN_VAULT_DIR"):
    VAULT_DIR = Path(_os.environ["CAIRN_VAULT_DIR"])

# ---- model / endpoint configuration ----------------------------------------
# Generation and embeddings are two independent roles, each with its own base
# URL and model. They need not be the same server: generation can run against a
# remote inference edge (e.g. a self-hosted OpenAI-dialect box) while embeddings
# stay on local Ollama, or both can point at the same local Ollama (the
# default). ask.py, enrich.py, interview.py, llm.py, index.py, and selftest.py
# all import these — none of them may hardcode a model name, a dialect, or an
# 11434/8443-style URL themselves.

# Generation role.
GEN_BASE = "http://127.0.0.1:11434"
GEN_DIALECT = "ollama"        # "ollama" or "openai" — selects the wire format llm.py speaks
GEN_MODEL = "qwen3:4b-instruct-2507-q4_K_M"
GEN_TIMEOUT_S = 300           # generous default: must budget for queue wait + prompt
                               # ingestion on a shared/remote inference edge, not just decode

# Embedding role. Always Ollama dialect ({EMBED_BASE}/api/embed) — there is no
# OpenAI-dialect embedding path in this codebase.
EMBED_BASE = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"

# Embedding dimension for the model index.py actually calls (nomic-embed-text -> 768).
# index.py asserts returned vector length matches this at runtime, so a model swap
# that changes the dimension fails loudly instead of corrupting the vector table.
EMBEDDING_DIM = 768

# Local override: if models.local.json exists at the repo root (gitignored via
# the same *.local.* pattern as vault.local.json above), it can override any of
# the keys below. This is the ONE file a different machine needs to touch — a
# different Ollama port, a remote generation endpoint, a different embedding or
# generation model, or a different embedding dimension never require editing
# tracked code.
# Recognized keys, all optional:
#   "gen_base"        -> GEN_BASE
#   "gen_dialect"      -> GEN_DIALECT      ("ollama" or "openai")
#   "gen_model"        -> GEN_MODEL
#   "gen_timeout_s"    -> GEN_TIMEOUT_S
#   "embed_base"       -> EMBED_BASE
#   "embed_model"      -> EMBED_MODEL
#   "embedding_dim"    -> EMBEDDING_DIM
#   "ollama_base"      -> DEPRECATED. Sets BOTH gen_base and embed_base, for
#                          configs written before the two roles split. A
#                          gen_base/embed_base key present alongside it wins
#                          for that role (applied after, so it overrides).
_models_override = ROOT / "models.local.json"
if _models_override.exists():
    import json as _json

    _models_cfg = _json.loads(_models_override.read_text())
    _legacy_base = _models_cfg.get("ollama_base")
    if _legacy_base:
        GEN_BASE = _legacy_base
        EMBED_BASE = _legacy_base
    GEN_BASE = _models_cfg.get("gen_base", GEN_BASE)
    GEN_DIALECT = _models_cfg.get("gen_dialect", GEN_DIALECT)
    GEN_MODEL = _models_cfg.get("gen_model", GEN_MODEL)
    GEN_TIMEOUT_S = _models_cfg.get("gen_timeout_s", GEN_TIMEOUT_S)
    EMBED_BASE = _models_cfg.get("embed_base", EMBED_BASE)
    EMBED_MODEL = _models_cfg.get("embed_model", EMBED_MODEL)
    EMBEDDING_DIM = _models_cfg.get("embedding_dim", EMBEDDING_DIM)

if GEN_DIALECT not in ("ollama", "openai"):
    raise ValueError(f"GEN_DIALECT must be 'ollama' or 'openai', got {GEN_DIALECT!r}")

# Derived endpoint constants.
#   GEN_CHAT_URL   — where llm.chat() posts a generation request, per dialect.
#   GEN_HEALTH_URL — what selftest.py probes for liveness, per dialect.
#   EMBED_URL      — embeddings are always Ollama dialect, regardless of GEN_DIALECT.
if GEN_DIALECT == "openai":
    GEN_CHAT_URL = f"{GEN_BASE}/v1/chat/completions"
    GEN_HEALTH_URL = f"{GEN_BASE}/v1/models"
else:
    GEN_CHAT_URL = f"{GEN_BASE}/api/chat"
    GEN_HEALTH_URL = f"{GEN_BASE}/api/version"
EMBED_URL = f"{EMBED_BASE}/api/embed"

# Chunking: heading-aware, with a character cap and a little overlap for continuity.
MAX_CHUNK_CHARS = 2000
CHUNK_OVERLAP_CHARS = 150

# Drop tiny chunks that have NO heading (page furniture above the first heading).
MIN_CHUNK_CHARS = 120

# File types we hand to MarkItDown. Everything else under sources/ is ignored.
SUPPORTED_SUFFIXES = {
    ".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".xls",
    ".html", ".htm", ".md", ".txt", ".csv",
}

# Records classification default for newly ingested docs.
# Conservative on purpose: everything is pre-decisional until a human says otherwise.
DEFAULT_STATUS = "draft"
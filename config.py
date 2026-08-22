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
# Single source of truth for every model name and Ollama URL in the pipeline.
# ask.py, index.py, and selftest.py all import these — none of them may
# hardcode a model name or an 11434 URL themselves.
OLLAMA_BASE = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"
GEN_MODEL = "qwen3:4b-instruct-2507-q4_K_M"

# Embedding dimension for the model index.py actually calls (nomic-embed-text -> 768).
# index.py asserts returned vector length matches this at runtime, so a model swap
# that changes the dimension fails loudly instead of corrupting the vector table.
EMBEDDING_DIM = 768

# Local override: if models.local.json exists at the repo root (gitignored via
# the same *.local.* pattern as vault.local.json above), it can override any of
# the four keys above. This is the ONE file a different machine needs to touch —
# a different Ollama port, a different embedding or generation model, or a
# different embedding dimension never require editing tracked code.
# Recognized keys, all optional:
#   "ollama_base"    -> OLLAMA_BASE
#   "embed_model"     -> EMBED_MODEL
#   "gen_model"       -> GEN_MODEL
#   "embedding_dim"   -> EMBEDDING_DIM
_models_override = ROOT / "models.local.json"
if _models_override.exists():
    import json as _json

    _models_cfg = _json.loads(_models_override.read_text())
    OLLAMA_BASE = _models_cfg.get("ollama_base", OLLAMA_BASE)
    EMBED_MODEL = _models_cfg.get("embed_model", EMBED_MODEL)
    GEN_MODEL = _models_cfg.get("gen_model", GEN_MODEL)
    EMBEDDING_DIM = _models_cfg.get("embedding_dim", EMBEDDING_DIM)

# Derived endpoint constants. Everything that talks to Ollama builds its URL
# from OLLAMA_BASE so there is exactly one place a machine-specific port lives.
OLLAMA_EMBED_URL = f"{OLLAMA_BASE}/api/embed"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE}/api/chat"
OLLAMA_VERSION_URL = f"{OLLAMA_BASE}/api/version"

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
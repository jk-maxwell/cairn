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

# Embedding dimension for the model index.py actually calls (nomic-embed-text -> 768).
# index.py asserts returned vector length matches this at runtime, so a model swap
# that changes the dimension fails loudly instead of corrupting the vector table.
EMBEDDING_DIM = 768

# Records classification default for newly ingested docs.
# Conservative on purpose: everything is pre-decisional until a human says otherwise.
DEFAULT_STATUS = "draft"
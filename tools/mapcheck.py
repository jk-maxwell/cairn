"""
mapcheck.py  (the Map gate)

Two checks, both Rule 1 applied to the repo itself:
  1. Existence: every tracked code file appears on the Map. An unmapped file is a
     labeled failure rather than silent rot.
  2. Truth: the Map names the models the code actually uses. The Map claiming
     qwen2.5 while ask.py runs qwen3 is exactly the drift this catches; it
     happened once (found by hand, 2026-08-07) and now fails loudly instead.

Run:  py tools\\mapcheck.py     (exit 0 = green)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP = ROOT / "MAP.md"

def tracked():
    files = [p.name for p in ROOT.glob("*.py")]
    files += [p.name for p in ROOT.glob("*.ps1")]
    files += ["tools/" + p.name for p in (ROOT / "tools").glob("*.py")]
    files += ["tools/" + p.name for p in (ROOT / "tools").glob("*.ps1")]
    return sorted(files)


def truths():
    """
    Facts the Map must state literally, read from the code itself so the code is
    the source and the Map is the mirror. Import without side effects: ask.py and
    index.py only run things under __main__, so importing is safe and cheap.
    """
    sys.path.insert(0, str(ROOT))
    import ask
    import index
    return {
        "generation model (ask.GEN_MODEL)": ask.GEN_MODEL,
        "embedding model (ask.EMBED_MODEL)": ask.EMBED_MODEL,
        "embedding model (index.EMBED_MODEL)": index.EMBED_MODEL,
    }


def main():
    if not MAP.exists():
        sys.exit("FAIL  MAP.md not found at repo root")
    text = MAP.read_text(encoding="utf-8")

    failed = False

    missing = [f for f in tracked() if Path(f).name not in text]
    if missing:
        failed = True
        print("FAIL  files missing from MAP.md:")
        for f in missing:
            print(f"        {f}")

    try:
        facts = truths()
    except Exception as e:
        sys.exit(f"FAIL  could not read model constants from the code: {e}")
    # The Map may state the model family without a quant suffix; the family name
    # must appear. "qwen3:4b-instruct-2507" satisfies "qwen3:4b-instruct-2507-q4_K_M".
    untrue = []
    for label, value in facts.items():
        base = value.split("-q")[0] if "-q" in value else value
        if value not in text and base not in text:
            untrue.append((label, value))
    if untrue:
        failed = True
        print("FAIL  the Map does not name what the code uses:")
        for label, value in untrue:
            print(f"        {label} = {value!r} absent from MAP.md")

    if failed:
        sys.exit(1)
    print(f"PASS  all {len(tracked())} tracked code files on the Map; "
          f"Map names the code's actual models")

if __name__ == "__main__":
    main()

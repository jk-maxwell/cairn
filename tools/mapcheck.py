"""
mapcheck.py  (the Map gate)

Three checks, all Rule 1 applied to the repo itself:
  1. Existence: every tracked code file appears on the Map. An unmapped file is a
     labeled failure rather than silent rot.
  2. Truth: the Map names the models the tracked code declares. The Map claiming
     qwen2.5 while config.py declares qwen3 is exactly the drift this catches;
     it happened once (found by hand, 2026-08-07) and now fails loudly instead.
  3. Re-export: ask.py serves whatever config.py resolved to, rather than
     carrying model names of its own.

The Map describes the REPOSITORY, not the machine. Check 2 therefore reads the
model names config.py DECLARES at module level, ignoring models.local.json --
which is gitignored, per-machine, and so can never legitimately be named in a
tracked document. Asserting against the resolved value made this gate fail on
every machine running an override, and a gate that is permanently red is a gate
nobody reads, which is how the drift it was built to catch gets through.

That trade gives up one thing: this gate no longer says anything about the model
this machine is actually running. Check 3 keeps the part that still can be
checked here -- that ask.py has not grown its own copy of a model name -- and
the running configuration belongs to selftest.py, whose first two gates print
the resolved model and endpoint and probe them for real. An active override is
reported below as information, never as a failure.

Run:  py tools\\mapcheck.py     (exit 0 = green)
"""

import ast
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


def declared_in_config():
    """
    The model names config.py declares, read from its source rather than from an
    import, so models.local.json cannot reach them.

    The parse walks module-level assignments only. That is not a shortcut -- it
    is the whole mechanism. config.py applies its override inside
    `if _models_override.exists():`, so those assignments live in an ast.If body
    and never appear at module level. The tracked default is exactly what a
    top-level walk sees.
    """
    tree = ast.parse((ROOT / "config.py").read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                out[target.id] = node.value.value
    return out


def truths():
    """
    Facts the Map must state literally, read from the tracked source so the
    repository is the source and the Map is the mirror.
    """
    declared = declared_in_config()
    missing = [k for k in ("GEN_MODEL", "EMBED_MODEL") if k not in declared]
    if missing:
        raise RuntimeError(
            f"config.py declares no module-level string for {', '.join(missing)}; "
            f"the Map gate cannot read the tracked default")
    return {
        "generation model (config.GEN_MODEL, as declared)": declared["GEN_MODEL"],
        # index.py reads config.EMBED_MODEL directly (it does not re-export it),
        # so the shared source of truth is what the Map must state.
        "embedding model (config.EMBED_MODEL, as declared)": declared["EMBED_MODEL"],
    }


def reexport_drift():
    """
    ask.py must serve whatever config.py resolved to, not a model name of its
    own. This is what remains of the old resolved-value check, and it is the
    part that was actually catching drift: it holds whether or not an override
    is active, because it compares two live values rather than a live value
    against a document. Import without side effects: ask.py only runs things
    under __main__, so importing is safe and cheap.
    """
    sys.path.insert(0, str(ROOT))
    import ask
    import config
    drift = []
    for name in ("GEN_MODEL", "EMBED_MODEL"):
        served, resolved = getattr(ask, name), getattr(config, name)
        if served != resolved:
            drift.append((name, served, resolved))
    return drift, config, declared_in_config()


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
        print("FAIL  the Map does not name what the tracked code declares:")
        for label, value in untrue:
            print(f"        {label} = {value!r} absent from MAP.md")

    try:
        drift, cfg, declared = reexport_drift()
    except Exception as e:
        sys.exit(f"FAIL  could not import ask.py / config.py: {e}")
    if drift:
        failed = True
        print("FAIL  ask.py does not serve what config.py resolved to:")
        for name, served, resolved in drift:
            print(f"        ask.{name} = {served!r} but config.{name} = {resolved!r}")

    if failed:
        sys.exit(1)

    # Information, never a failure: models.local.json is gitignored and
    # per-machine, so the Map cannot name it and must not be asked to.
    overrides = [(k, declared[k], getattr(cfg, k))
                 for k in ("GEN_MODEL", "EMBED_MODEL")
                 if declared.get(k) != getattr(cfg, k)]
    print(f"PASS  all {len(tracked())} tracked code files on the Map; "
          f"Map names the models the tracked code declares; ask.py re-exports config")
    if overrides:
        print("      local override active (models.local.json), not checked against the Map:")
        for name, default, live in overrides:
            print(f"        {name}: {default!r} declared -> {live!r} running")
        print("      selftest.py gates 1 and 2 are what probe the running configuration.")

if __name__ == "__main__":
    main()

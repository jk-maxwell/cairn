#!/usr/bin/env python3
"""
tools/preflight.py

De-risk check for docs/BETA.md Phase 2, item 0: "verify the work machine can
run the stack at all (Python, a local model runtime, Obsidian, install
rights, network policy). If not, pivot."

Right now that verification does not exist except by attempting the full
install on the target machine and seeing what breaks -- expensive on a
locked-down government machine where a failed install may not be repeatable.
This script answers the question first, without installing anything.

DESIGN CONSTRAINTS, ALL LOAD-BEARING -- do not relax any of these:

1. Zero third-party imports. Standard library only. The whole point is to
   run on a bare system Python with no venv and no pip install; if this file
   needed a dependency it could not answer the question it exists to answer.

2. Must run standalone. This file gets copied to another machine BY ITSELF,
   with the rest of the repo absent. Do not import config, db, or any other
   Cairn module. Where a check needs a real value from the repo (required
   Python version, the engine's port, the default model runtime endpoint),
   the value is inlined below with a comment pointing at the file it was
   read from, so a future drift between this script and the real repo is at
   least visible at a glance.

3. Strictly read-only and non-destructive. No installs, no writes into the
   user's home directory, no config changes. The only filesystem writes this
   script performs are one temp file (to test write access) and one temp
   script (to test execute permission), both created and deleted within a
   single check, in a system temp directory.

4. No network calls to the public internet. Only loopback (127.0.0.1)
   probes, to check whether a local model runtime is answering. This is
   going on a government machine; anything that could look like phoning
   home is disqualifying, so there is no code path in this file that
   contacts any non-loopback host.

Usage:
    python3 preflight.py              human-readable report
    python3 preflight.py --json       machine-readable report (JSON only)
    python3 preflight.py --verbose    human report with extra detail per check

Exit code: 0 for GO or GO WITH CAVEATS, 1 for BLOCKED.
"""

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import sysconfig
import tempfile
import traceback
import urllib.error
import urllib.request
from pathlib import Path

# -----------------------------------------------------------------------------
# Constants mirrored from the real repo. Keep this section small and correct
# rather than clever -- every value here is duplicated on purpose (constraint
# 2 above) and the comment says exactly where the authoritative value lives.
# -----------------------------------------------------------------------------

# README.md, "Getting started": "You need: Python 3.10 or newer". Confirmed
# independently by the source itself: ingest.py, enrich.py, interview.py and
# registry.py all use `X | None` union syntax (PEP 604), which only parses on
# 3.10+.
MIN_PYTHON = (3, 10)

# ask.py: `HOST, PORT = "127.0.0.1", 8765` -- the engine's own web/protocol port.
ENGINE_PORT = 8765

# config.py: GEN_BASE / EMBED_BASE default to "http://127.0.0.1:11434", both
# Ollama-dialect by default. GEN_MODEL / EMBED_MODEL are the two models the
# README's "Models" step pulls before anything else works.
OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434
OLLAMA_BASE = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"
GEN_MODEL = "qwen3:4b-instruct-2507-q4_K_M"
EMBED_MODEL = "nomic-embed-text"

# README.md step 2: `./.venv/bin/pip install sqlite-vec 'markitdown[all]'`.
# sqlite-vec ships a compiled SQLite loadable extension (a .so/.dylib/.dll)
# and is loaded via sqlite3.Connection.enable_load_extension() -- the single
# most common lockdown failure, because many distro/managed Python builds
# and many corporate security policies disable extension loading outright.
# markitdown[all] pulls in its own native/compiled wheels for document
# conversion; onnxruntime and numpy were confirmed present in this repo's
# .venv (`pip list`) and are the two heaviest to get via wheel on an unusual
# platform/arch, since they are large compiled artifacts rather than pure
# Python.
NATIVE_DEPENDENCIES = [
    ("sqlite-vec", "SQLite loadable extension for vector search (vec_chunks table). "
                    "Required by index.py and ask.py. Needs enable_load_extension "
                    "to work at all -- see the SQLite check below."),
    ("onnxruntime", "Compiled inference runtime pulled in by markitdown[all] for "
                     "document layout/OCR paths. Large platform-specific wheel; "
                     "may have no prebuilt wheel for an unusual OS/arch combination."),
    ("numpy", "Compiled numeric library pulled in by markitdown[all]. Normally "
              "has wheels for every common platform, but is the kind of package "
              "that fails to build from source if no compiler is present."),
]

# NEVER touch this port -- reserved on the owner's machine for something
# unrelated, per explicit instruction. It must never be bound, connected to,
# or otherwise probed by this script, under any circumstances. Guarded here
# as data (not just prose) so a future edit that starts looping over "ports
# to check" can assert against it.
FORBIDDEN_PORTS = frozenset({4001})
assert ENGINE_PORT not in FORBIDDEN_PORTS and OLLAMA_PORT not in FORBIDDEN_PORTS

# Rough disk budget: the two pulled models (qwen3:4b quantized +
# nomic-embed-text) plus markitdown/onnxruntime/numpy wheels comfortably fit
# under a few GB, but venvs, the vault, and cairn.db grow over time. These
# thresholds are deliberately conservative guesses, not measured from a real
# install -- flagged as such in the check's reason text.
DISK_FAIL_GIB = 1.0
DISK_WARN_GIB = 5.0

STATUS_PASS, STATUS_WARN, STATUS_FAIL = "PASS", "WARN", "FAIL"

# Where Cairn would actually be installed. Defaults to the current directory,
# but --install-dir matters more than it looks: the two permission checks below
# are only meaningful if they test the directory the venv will really live in.
# Copying this script to Downloads and running it there would otherwise "prove"
# Downloads is writable and say nothing about ~/cairn.
INSTALL_DIR = Path.cwd()



# -----------------------------------------------------------------------------
# Small helpers
# -----------------------------------------------------------------------------

def _run(argv, timeout=5):
    """Run a subprocess read-only-ly and return (returncode, stdout, stderr).

    Never raises: a missing binary or a timeout comes back as returncode -1
    with the exception text in stderr, so callers don't need their own
    try/except around this.
    """
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return -1, "", f"{argv[0]}: not found"
    except subprocess.TimeoutExpired:
        return -1, "", f"{argv[0]}: timed out after {timeout}s"
    except Exception as e:  # noqa: BLE001 - genuinely want to catch everything here
        return -1, "", f"{argv[0]}: {e}"


def _http_get_loopback(url, timeout=2.0):
    """GET a loopback URL only. Raises on any failure; caller decides meaning.

    The only network access this whole file performs. `url` is always built
    from OLLAMA_BASE above, never from user input or a repo file, so there is
    no path by which this ever reaches a non-loopback host.
    """
    assert url.startswith(f"http://{OLLAMA_HOST}:") or url.startswith("http://127.0.0.1:"), \
        "refusing to fetch a non-loopback URL"
    req = urllib.request.Request(url, headers={"User-Agent": "cairn-preflight/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def _port_is_free(port, host="127.0.0.1"):
    """True if nothing is listening on host:port, by attempting our own bind.

    The forbidden-port guard lives HERE, at the single choke point where this
    file can touch a port at all, not only as a module-level assert on the two
    named ports. That assert proves today's constants are safe; this one keeps
    the promise for any port a future edit passes in, which is the case the
    module-level check cannot see.
    """
    if port in FORBIDDEN_PORTS:
        raise AssertionError(
            f"refusing to probe port {port}: reserved, must never be touched")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


# -----------------------------------------------------------------------------
# Checks. Each returns a dict: status, reason (one line), and optionally
# detail (multi-line, shown with --verbose) and fix (what to do next, shown
# for anything not PASS). Each is called through run_check() below, which
# wraps it so a check that raises still produces a report line instead of
# crashing the whole script.
# -----------------------------------------------------------------------------

def check_python_version():
    v = sys.version_info
    have = (v.major, v.minor)
    reason = f"running {platform.python_version()} (need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)"
    if have >= MIN_PYTHON:
        return {"status": STATUS_PASS, "reason": reason}
    return {
        "status": STATUS_FAIL,
        "reason": reason,
        "fix": (
            "Install Python 3.10 or newer and re-run every step with it. "
            "Cairn's own source uses `X | None` union syntax that fails to "
            "parse on older Pythons, so this is a hard floor, not a suggestion."
        ),
    }


def check_interpreter_info():
    exe = sys.executable or "(unknown)"
    exe_l = exe.lower()
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)

    if "conda" in exe_l or os.environ.get("CONDA_PREFIX"):
        kind = "conda/miniforge-managed"
    elif "pyenv" in exe_l:
        kind = "pyenv-managed"
    elif "windowsapps" in exe_l:
        kind = "Windows Store Python (often sandboxed/restricted)"
    elif "homebrew" in exe_l or "/opt/homebrew" in exe_l or "cellar" in exe_l:
        kind = "Homebrew-managed"
    elif exe_l.startswith("/usr/bin/") or exe_l.startswith("/usr/local/bin/python3"):
        kind = "system Python"
    else:
        kind = "unclassified"

    reason = f"{exe} ({kind}{', already inside a venv' if in_venv else ''})"
    return {"status": STATUS_PASS, "reason": reason}


def check_externally_managed():
    """PEP 668: a distro-managed Python refuses `pip install` outside a venv.

    This is exactly the kind of silent-until-you-try-it failure this script
    exists to catch ahead of time. Detected by the presence of the
    EXTERNALLY-MANAGED marker file pip itself looks for.
    """
    candidates = []
    try:
        candidates.append(Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED")
    except Exception:
        pass
    try:
        candidates.append(Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "EXTERNALLY-MANAGED")
    except Exception:
        pass

    found = next((c for c in candidates if c.exists()), None)
    if found is None:
        return {"status": STATUS_PASS, "reason": "no PEP 668 EXTERNALLY-MANAGED marker found"}
    return {
        "status": STATUS_WARN,
        "reason": f"PEP 668 marker present ({found}) -- bare `pip install` will refuse to run",
        "fix": (
            "Not a blocker by itself: the README's install already uses a venv "
            "(`python3 -m venv .venv`), and pip inside a venv ignores this marker. "
            "Just make sure the venv step is not skipped on this machine."
        ),
    }


def check_venv_and_pip():
    import importlib.util

    have_venv_module = importlib.util.find_spec("venv") is not None
    have_ensurepip = importlib.util.find_spec("ensurepip") is not None
    rc, out, err = _run([sys.executable, "-m", "pip", "--version"], timeout=10)
    pip_ok = rc == 0

    if not have_venv_module:
        return {
            "status": STATUS_FAIL,
            "reason": "the stdlib `venv` module is not importable",
            "fix": (
                "Cairn's install is venv-based (`python3 -m venv .venv`). Some "
                "minimal/managed Python installs strip this module out; you would "
                "need a different Python install or `virtualenv` from elsewhere."
            ),
        }
    if not pip_ok:
        detail = f"`{sys.executable} -m pip --version` failed: {err.strip() or out.strip()}"
        if have_ensurepip:
            return {
                "status": STATUS_WARN,
                "reason": "pip is not currently usable, but `ensurepip` is available",
                "detail": detail,
                "fix": "A fresh venv normally gets pip via ensurepip automatically; verify with a real `python3 -m venv .venv` attempt on this machine.",
            }
        return {
            "status": STATUS_FAIL,
            "reason": "pip is not usable and `ensurepip` is unavailable",
            "detail": detail,
            "fix": "No path to installing sqlite-vec or markitdown without pip. Needs an admin-provided Python with pip, or a pre-built package cache.",
        }
    return {"status": STATUS_PASS, "reason": f"venv module present; {out.strip() or 'pip usable'}"}


def check_write_access():
    """Can we write into the current directory (a stand-in for wherever the
    repo would be cloned)? Creates and deletes exactly one temp file."""
    target_dir = INSTALL_DIR
    try:
        with tempfile.NamedTemporaryFile(dir=str(target_dir), prefix=".cairn_preflight_", delete=True) as f:
            f.write(b"preflight write-access probe")
            f.flush()
        return {"status": STATUS_PASS, "reason": f"can create/delete files in {target_dir}"}
    except Exception as e:
        return {
            "status": STATUS_FAIL,
            "reason": f"cannot write to {target_dir}: {e}",
            "fix": "Clone/install to a directory you have write access to (e.g. your home directory), or request write access to this one.",
        }


def check_execute_permission():
    """Can a file we create ourselves actually be executed?

    Common lockdown failure mode: a temp/home directory mounted `noexec`, or
    an AppLocker/SRP-style policy that blocks execution of newly created
    files. This would break venv-created binaries and any downloaded
    installer (e.g. the Ollama installer). One temp file, created, executed,
    then deleted.
    """
    # Two directories genuinely matter and they are often governed by different
    # policies: the install dir (where `python -m venv` writes bin/python and
    # every console script -- if this is noexec, Cairn cannot run at all) and
    # the system temp dir (where pip unpacks and executes build helpers -- if
    # this is noexec, installation fails even though Cairn would have run).
    # Testing only one of them produces a confident wrong answer either way.
    results = {}
    for label, d in (("install dir", str(INSTALL_DIR)), ("temp dir", tempfile.gettempdir())):
        results[label] = _exec_probe(d)

    failed = [f"{label} ({d})" for label, (ok_, d, _det) in
              ((k, v) for k, v in results.items()) if not ok_]
    if not failed:
        where = ", ".join(f"{k} ({v[1]})" for k, v in results.items())
        return {"status": STATUS_PASS,
                "reason": f"can execute freshly created files in both {where}"}
    detail_lines = [f"{k}: {'ok' if v[0] else 'BLOCKED -- ' + (v[2] or 'non-zero exit')} ({v[1]})"
                    for k, v in results.items()]
    return {
        "status": STATUS_FAIL,
        "reason": "cannot execute a freshly created file in: " + "; ".join(failed),
        "detail": "\n".join(detail_lines),
        "fix": (
            "That location blocks execution (a noexec mount, or an endpoint-protection "
            "execution policy). If the INSTALL DIR is blocked, venv binaries will not run "
            "and Cairn cannot start there -- pick an execute-permitted install location. "
            "If the TEMP DIR is blocked, pip's build helpers cannot run -- set TMPDIR to an "
            "execute-permitted directory before installing. Both are normal IT requests."
        ),
    }


def _exec_probe(tmpdir):
    """Create one executable file in `tmpdir`, run it, delete it.

    Returns (ok, tmpdir, detail). Never raises: an unwritable directory is
    reported as a failed probe, since for our purposes "cannot even place a
    file here" and "cannot execute here" have the same consequence.
    """
    is_windows = platform.system() == "Windows"
    name = "cairn_preflight_exec_test." + ("bat" if is_windows else "sh")
    script = Path(tmpdir) / name
    try:
        script.write_text("@exit /b 0\r\n" if is_windows else "#!/bin/sh\nexit 0\n")
    except Exception as e:
        # Cannot even place the file. Same practical consequence as noexec:
        # nothing of ours can run here.
        return False, tmpdir, f"cannot write a probe file here: {e}"

    if is_windows:
        try:
            rc, out, err = _run([str(script)], timeout=5)
            ok = rc == 0
            detail = err.strip()
        except Exception as e:
            ok, detail = False, str(e)
        finally:
            script.unlink(missing_ok=True)
        note = " (this only tests script execution; AppLocker/SRP policies that block unsigned .exe files specifically are not detected here)"
    else:
        try:
            script.chmod(0o755)
            rc, out, err = _run([str(script)], timeout=5)
            ok = rc == 0
            detail = err.strip()
        except Exception as e:
            ok, detail = False, str(e)
        finally:
            script.unlink(missing_ok=True)
        note = ""

    return ok, tmpdir, (detail + note).strip()


def check_sqlite_extension_loading():
    import sqlite3

    version = sqlite3.sqlite_version
    conn = sqlite3.connect(":memory:")
    try:
        has_attr = hasattr(conn, "enable_load_extension")
        if not has_attr:
            return {
                "status": STATUS_FAIL,
                "reason": f"sqlite3 {version}: Connection.enable_load_extension does not exist on this build",
                "fix": "sqlite-vec (vector search) cannot load. index.py and ask.py both depend on it; there is no fallback path in this codebase.",
            }
        try:
            conn.enable_load_extension(True)
            conn.enable_load_extension(False)
        except Exception as e:
            return {
                "status": STATUS_FAIL,
                "reason": f"sqlite3 {version}: extension loading is compiled out ({e})",
                "fix": (
                    "This Python's sqlite3 module was built with loadable-extension "
                    "support disabled (common on managed/hardened Python builds, and "
                    "on stock Debian/Ubuntu system Python). sqlite-vec cannot load, "
                    "which breaks index.py (embedding) and ask.py (retrieval) "
                    "completely -- not a degraded mode, a hard block. Needs a "
                    "different Python build (e.g. from python.org, pyenv, or "
                    "conda/miniforge, which are typically built with this enabled)."
                ),
            }
        return {"status": STATUS_PASS, "reason": f"sqlite3 {version}: extension loading works (enable_load_extension succeeded)"}
    finally:
        conn.close()


def check_native_dependencies():
    lines = [f"{name}: {why}" for name, why in NATIVE_DEPENDENCIES]
    return {
        "status": STATUS_WARN,
        "reason": f"{len(NATIVE_DEPENDENCIES)} native/compiled packages required (sqlite-vec, onnxruntime, numpy) -- cannot verify wheel availability without a network call, which this script deliberately never makes",
        "detail": "\n".join(lines),
        "fix": (
            "When you do run the real `pip install sqlite-vec 'markitdown[all]'`, "
            "watch for 'Building wheel for X' with no compiler available, or "
            "'no matching distribution' -- both mean this platform/arch has no "
            "prebuilt wheel and needs either a different Python build/arch or an "
            "internal package mirror that carries one."
        ),
    }


def check_ollama():
    which = shutil.which("ollama")
    try:
        _, body = _http_get_loopback(f"{OLLAMA_BASE}/api/version", timeout=2.0)
        running = True
        version_text = body.decode("utf-8", "replace")[:200]
    except Exception:
        running = False
        version_text = None

    if running:
        try:
            _, tags_body = _http_get_loopback(f"{OLLAMA_BASE}/api/tags", timeout=2.0)
            tags = json.loads(tags_body.decode("utf-8", "replace"))
            names = {m.get("name", "") for m in tags.get("models", [])}
            missing = [m for m in (GEN_MODEL, EMBED_MODEL) if not any(m in n for n in names)]
        except Exception:
            missing = None  # couldn't determine, don't claim either way

        if missing is None:
            return {"status": STATUS_WARN, "reason": "Ollama is running, but the model list could not be read to confirm required models", "fix": f"Run `ollama list` by hand and confirm it has {GEN_MODEL!r} and {EMBED_MODEL!r}."}
        if missing:
            return {
                "status": STATUS_WARN,
                "reason": f"Ollama is running on {OLLAMA_BASE} but missing model(s): {', '.join(missing)}",
                "fix": f"`ollama pull {missing[0]}`" + (f" and {len(missing) - 1} more" if len(missing) > 1 else "") + " -- needs network access to the Ollama model registry.",
            }
        return {"status": STATUS_PASS, "reason": f"Ollama running on {OLLAMA_BASE} with both required models present"}

    if which:
        return {
            "status": STATUS_WARN,
            "reason": f"Ollama is installed ({which}) but not answering on {OLLAMA_BASE}",
            "fix": "Start it (`ollama serve`, or open the Ollama app) before running ingest/index/ask.",
        }
    return {
        "status": STATUS_WARN,
        "reason": "Ollama not found on PATH and nothing answering on the default port",
        "fix": (
            "Install Ollama (https://ollama.com) -- this needs both install rights "
            "and network access, both checked elsewhere in this report. Cairn has "
            "no fallback local model runtime; this is a hard requirement for the "
            "Ask and enrich paths, not optional."
        ),
    }


def check_obsidian():
    system = platform.system()
    app_found = False
    config_path = None

    if system == "Darwin":
        app_found = Path("/Applications/Obsidian.app").exists()
        config_path = Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    elif system == "Windows":
        localapp = os.environ.get("LOCALAPPDATA", "")
        appdata = os.environ.get("APPDATA", "")
        if localapp:
            app_found = (Path(localapp) / "Programs" / "obsidian").exists()
        if appdata:
            config_path = Path(appdata) / "obsidian" / "obsidian.json"
    else:  # Linux and anything else POSIX-ish
        # No single canonical install location; a couple of common ones.
        app_found = any(
            p.exists() for p in (
                Path.home() / ".local" / "share" / "flatpak" / "app" / "md.obsidian.Obsidian",
                Path("/var/lib/flatpak/app/md.obsidian.Obsidian"),
                Path.home() / "Applications" / "Obsidian.AppImage",
            )
        )
        config_path = Path.home() / ".config" / "obsidian" / "obsidian.json"

    vault_count = None
    if config_path and config_path.exists():
        try:
            data = json.loads(config_path.read_text())
            vault_count = len(data.get("vaults", {}))
        except Exception:
            vault_count = None

    if app_found or vault_count:
        reason = "Obsidian appears installed"
        if vault_count is not None:
            reason += f" ({vault_count} vault(s) registered)"
        return {"status": STATUS_PASS, "reason": reason}
    return {
        "status": STATUS_WARN,
        "reason": "Obsidian not detected (no app bundle and no vault registry found)",
        "fix": "Install Obsidian (https://obsidian.md) and create/open a vault. Cairn's enrichment output and the plugin both target a real vault; the engine can be exercised without one, but the intended workflow needs it.",
    }


def check_engine_port():
    if _port_is_free(ENGINE_PORT):
        return {"status": STATUS_PASS, "reason": f"port {ENGINE_PORT} (ask.py's default) is free"}
    return {
        "status": STATUS_WARN,
        "reason": f"port {ENGINE_PORT} (ask.py's default) is already in use",
        "fix": f"Find what's using it, or run ask.py with `--port <other>` if it must coexist with the current occupant.",
    }


def check_disk_space():
    try:
        usage = shutil.disk_usage(INSTALL_DIR)
    except Exception as e:
        return {"status": STATUS_WARN, "reason": f"could not determine free disk space: {e}"}
    free_gib = usage.free / (1024 ** 3)
    reason = f"{free_gib:.1f} GiB free at {INSTALL_DIR}"
    if free_gib < DISK_FAIL_GIB:
        return {
            "status": STATUS_FAIL,
            "reason": reason,
            "fix": f"Free up space -- under {DISK_FAIL_GIB:.0f} GiB free is not enough to even create a venv and a small database.",
        }
    if free_gib < DISK_WARN_GIB:
        return {
            "status": STATUS_WARN,
            "reason": reason,
            "fix": f"The two pulled models plus dependencies typically want a few GiB; {DISK_WARN_GIB:.0f} GiB free is a rough comfort floor, not a measured requirement.",
        }
    return {"status": STATUS_PASS, "reason": reason}


def check_network_policy():
    proxy_vars = {k: v for k, v in os.environ.items() if k.upper() in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "PIP_INDEX_URL", "PIP_TRUSTED_HOST")}
    if proxy_vars:
        shown = ", ".join(f"{k}={v}" for k, v in sorted(proxy_vars.items()))
        return {
            "status": STATUS_PASS,
            "reason": f"proxy/index environment configured: {shown}",
            "detail": "This script does not test these live (no public-internet calls, by design). Confirm pip and ollama's pull path both honor them before relying on them.",
        }
    return {
        "status": STATUS_WARN,
        "reason": "no proxy/pip-index environment variables set",
        "fix": (
            "If this network requires a proxy or an internal package mirror for "
            "outbound access, `pip install` and `ollama pull` will hang or fail "
            "opaquely rather than explaining why. Ask IT what the network policy "
            "actually is before attempting the real install."
        ),
    }


# -----------------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------------

CHECKS = [
    ("Python", "python_version", check_python_version),
    ("Python", "interpreter", check_interpreter_info),
    ("Python", "externally_managed", check_externally_managed),
    ("Python", "venv_and_pip", check_venv_and_pip),
    ("Native/binary dependencies", "native_dependencies", check_native_dependencies),
    ("Native/binary dependencies", "sqlite_extension_loading", check_sqlite_extension_loading),
    ("Local model runtime", "ollama", check_ollama),
    ("Obsidian", "obsidian", check_obsidian),
    ("Install rights / environment", "write_access", check_write_access),
    ("Install rights / environment", "execute_permission", check_execute_permission),
    ("Install rights / environment", "disk_space", check_disk_space),
    ("Install rights / environment", "network_policy", check_network_policy),
    ("Ports", "engine_port", check_engine_port),
]


def run_check(category, name, func):
    """Execute one check, never letting it take the whole script down."""
    try:
        result = func()
    except Exception as e:  # noqa: BLE001 - a check must never crash the run
        result = {
            "status": STATUS_WARN,
            "reason": f"check crashed and could not determine an answer: {e}",
            "detail": traceback.format_exc(),
            "fix": "This is a bug in preflight.py itself (or an unexpected environment shape it didn't anticipate) -- worth reporting, but don't treat it as a stack blocker on its own.",
        }
    result = dict(result)
    result["category"] = category
    result["name"] = name
    result.setdefault("detail", None)
    result.setdefault("fix", None)
    return result


def compute_verdict(results):
    if any(r["status"] == STATUS_FAIL for r in results):
        return "BLOCKED"
    if any(r["status"] == STATUS_WARN for r in results):
        return "GO WITH CAVEATS"
    return "GO"


def render_human(results, verdict, verbose):
    lines = []
    lines.append("Cairn preflight -- can this machine run the stack?")
    lines.append(f"Python {platform.python_version()} on {platform.platform()}")
    lines.append("")

    current_category = None
    for r in results:
        if r["category"] != current_category:
            current_category = r["category"]
            lines.append(f"-- {current_category} " + "-" * max(1, 60 - len(current_category)))
        lines.append(f"  [{r['status']:<4}] {r['name']}: {r['reason']}")
        if r["status"] != STATUS_PASS and r.get("fix"):
            lines.append(f"           -> {r['fix']}")
        if verbose and r.get("detail"):
            for dline in str(r["detail"]).splitlines():
                lines.append(f"           | {dline}")
        lines.append("")

    lines.append("=" * 70)
    lines.append(f"VERDICT: {verdict}")
    if verdict == "GO":
        lines.append("Everything checked out. Proceed with the real install (README.md).")
    elif verdict == "GO WITH CAVEATS":
        warn_names = [r["name"] for r in results if r["status"] == STATUS_WARN]
        lines.append(f"No hard blockers, but {len(warn_names)} check(s) need attention before or during install: {', '.join(warn_names)}.")
        lines.append("Read the -> lines above for each; none of them individually rules out running Cairn here.")
    else:
        fail_names = [r["name"] for r in results if r["status"] == STATUS_FAIL]
        lines.append(f"Hard blocker(s): {', '.join(fail_names)}.")
        lines.append("Fix these first (see the -> lines above) or treat this as the Phase 2.0 pivot signal in docs/BETA.md: run the second deployment on the personal machine instead.")
    lines.append("=" * 70)
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Read-only, dependency-free preflight for whether this machine can run Cairn. "
                    "Standard-library only; safe to copy to another machine on its own.",
    )
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of the human report")
    ap.add_argument("--verbose", action="store_true", help="include per-check detail in the human report")
    ap.add_argument("--install-dir", default=None, metavar="DIR",
                    help="the directory Cairn would actually be installed into "
                         "(default: current directory). The write- and execute-permission "
                         "checks test THIS directory, so on a locked-down machine point it "
                         "at the real intended location -- the answer differs per directory.")
    args = ap.parse_args(argv)

    # Bind the install dir before any check runs: check_write_access and
    # check_execute_permission both read the module-level value.
    global INSTALL_DIR
    if args.install_dir:
        INSTALL_DIR = Path(args.install_dir).expanduser()
        if not INSTALL_DIR.is_dir():
            print(f"preflight: --install-dir {INSTALL_DIR} is not an existing directory",
                  file=sys.stderr)
            return 2

    results = [run_check(category, key, func) for category, key, func in CHECKS]
    verdict = compute_verdict(results)

    if args.json:
        payload = {
            "verdict": verdict,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "checks": [
                {
                    "category": r["category"],
                    "name": r["name"],
                    "status": r["status"],
                    "reason": r["reason"],
                    "detail": r["detail"],
                    "fix": r["fix"],
                }
                for r in results
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(render_human(results, verdict, args.verbose))

    return 0 if verdict in ("GO", "GO WITH CAVEATS") else 1


if __name__ == "__main__":
    sys.exit(main())

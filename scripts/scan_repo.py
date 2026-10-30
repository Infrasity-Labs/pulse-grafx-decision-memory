"""Scan the repo for things that must not be published.

Checks every file git would track (tracked or untracked, not ignored):
  1. em dashes (U+2014) outside app/ (the fork is a plain copy)
  2. key-like strings: Pulse agent keys (dash_...), bearer tokens, common API key shapes
  3. the exact key values stored in agents/.keys.local, if that file exists
  4. absolute paths from a user machine (/Users/<name>, /home/<name>, C:\\Users) and their dash-encoded form (a leading dash, Users or home, then the name). In app/ only this machine's home path.
Files that hold verbatim output of a model, of Pulse or of a read file (demo-state transcript.jsonl and logs/*.log) are treated like app/: this machine's home
path and every key shape are flagged, but not the em dashes and example paths (an upstream README quotes a home folder of a stranger) that the quoted text contains.
Exit code 0 if clean. Prints file:line for each hit and never prints a matched secret.

Usage: python scripts/scan_repo.py [--root DIR]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

EM_DASH = "\u2014"
KEY_PATTERNS = [
    ("pulse agent key", re.compile(r"\bdash_[A-Za-z0-9]{20,}")),
    ("openai-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer literal", re.compile(r"Bearer\s+(?!\$\{)[A-Za-z0-9._~+/-]{24,}")),
    ("assigned secret", re.compile(r"(?i)\b(api[_-]?key|secret|passwd|password|token)\b\s*[:=]\s*['\"][A-Za-z0-9_\-]{24,}['\"]")),
]
PATH_PATTERNS = [
    re.compile(r"/Users/[A-Za-z0-9._-]+"), re.compile(r"/home/[A-Za-z0-9._-]+"), re.compile(r"[A-Za-z]:\\Users\\"),
    # the dash-encoded form Claude Code uses for a project folder name: the slashes and dots of the path turned into dashes
    re.compile(r"(?<![A-Za-z0-9])-(?:Users|home)-[A-Za-z0-9_]+-[A-Za-z0-9_-]+"),
]


SKIP_PARTS = {".venv", "venv", ".ci", "node_modules", "site-packages", "__pycache__", ".work"}


def home_pattern(home: str | Path) -> re.Pattern | None:
    """A regex for this machine's home folder as a real absolute path, or None if the home is too short to be told apart from a word.

    The home must not continue a longer name before it ('source/root' is not '/root') and must not continue into a longer name after it
    ('/rooted' is not '/root'). A home of '/' (nothing left after trimming the trailing slash) is never searched for."""
    h = str(home).rstrip("/\\")
    if not h:
        return None
    return re.compile(r"(?<![A-Za-z0-9_.\-])(?<![A-Za-z0-9_.\-]/)" + re.escape(h) + r"(?![A-Za-z0-9_\-])(?!\.[A-Za-z0-9_\-])")


def files(root: Path) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=root, capture_output=True).stdout.decode()
    return [root / p for p in out.split("\0") if p and not SKIP_PARTS & set(Path(p).parts)]


def scan(root: Path) -> tuple[list[str], int]:
    """Return (hits, number of files scanned) for the files git would track under root."""
    exact: list[str] = []
    kf = root / "agents" / ".keys.local"
    if kf.exists():
        exact = [ln.partition("=")[2].strip() for ln in kf.read_text().splitlines() if "=" in ln and len(ln.partition("=")[2].strip()) >= 20]
    home_re = home_pattern(Path.home())
    hits: list[str] = []
    scanned = 0
    for p in files(root):
        rel = p.relative_to(root)
        if not p.is_file() or p.suffix in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2"}:
            continue
        try:
            text = p.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        in_fork = rel.parts[0] == "app" or (rel.parts[0] == "demo-state" and (rel.name == "transcript.jsonl" or "logs" in rel.parts))
        for n, line in enumerate(text.splitlines(), 1):
            if not in_fork and EM_DASH in line:
                hits.append(f"{rel}:{n}: em dash")
            for label, pat in KEY_PATTERNS:
                if (not in_fork or label == "pulse agent key") and pat.search(line):
                    hits.append(f"{rel}:{n}: {label}")
            if any(k in line for k in exact):
                hits.append(f"{rel}:{n}: exact agent key from the local keys file")
            if in_fork:
                if home_re and home_re.search(line):  # the fork is a plain copy; only flag this machine's own home path, as a path and not as a word
                    hits.append(f"{rel}:{n}: machine-local absolute path")
                continue
            for pat in PATH_PATTERNS:
                if pat.search(line):
                    hits.append(f"{rel}:{n}: machine-local absolute path")
                    break
    return hits, scanned


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    root = Path(ap.parse_args().root).resolve()
    hits, scanned = scan(root)
    for h in hits:
        print(h)
    print(f"scanned {scanned} files, {len(hits)} hit(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())

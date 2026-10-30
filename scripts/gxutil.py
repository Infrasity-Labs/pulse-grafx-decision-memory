"""Standard-library helpers shared by the step scripts, so they also run where Pulse is not installed."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _replace_path(text: str, base: str, tag: str) -> str:
    """Replace a path only where it ends: /repo must not eat the start of /repositories (the repo sits at /repo in the Linux container)."""
    return re.sub(re.escape(base) + r"(?![A-Za-z0-9_.-])", lambda _: tag, text)


def scrub(text: str) -> str:
    for base, tag in ((ROOT, "<dash-encoded-project-path>"), (Path.home(), "<dash-encoded-home>")):  # Claude Code project folder names
        encoded = re.sub(r"[/.]", "-", str(base))
        if encoded not in ("-", ""):
            text = _replace_path(text, encoded, tag)
    for base, tag in ((ROOT, "<repo>"), (Path.home(), "<home>")):
        if str(base) not in ("/", ""):  # inside a container the root can be "/"; never replace every slash
            text = _replace_path(text, str(base), tag)
    return text


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(scrub(json.dumps(obj, indent=2, default=str)) + "\n")


def data_file_hashes(store: Path) -> dict:
    """SHA-256 of data files (not lock, lease or reader files) so a read-only pass can be shown to write nothing."""
    out = {}
    for p in sorted(store.rglob("*")):
        if p.is_file() and p.suffix != ".lock" and "readers" not in p.parts and p.name != "writer.lease" and "control" not in p.parts:
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            out[str(p.relative_to(store))] = h.hexdigest()
    return out

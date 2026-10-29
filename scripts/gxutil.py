"""Standard-library helpers shared by the step scripts, so they also run where Pulse is not installed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def scrub(text: str) -> str:
    for base, tag in ((ROOT, "<repo>"), (Path.home(), "<home>")):
        if str(base) not in ("/", ""):  # inside a container the root can be "/"; never replace every slash
            text = text.replace(str(base), tag)
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

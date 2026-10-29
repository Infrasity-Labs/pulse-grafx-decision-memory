"""Step 1 proof: installed versions and the Requires-Dist line that pins Grafx. Reads package metadata only.

Writes demo-state/step1/versions.json and prints it.
"""
from __future__ import annotations

import json
import platform
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, requires, version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo-state" / "step1"


def ver(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def main() -> None:
    reqs = requires("okto-pulse") or []
    grafx_req = next((r for r in reqs if r.lower().startswith("okto-grafx")), None)
    st_req = next((r for r in reqs if r.lower().startswith("sentence-transformers")), None)
    core_reqs = [r for r in (requires("okto-pulse-core") or []) if "grafx" in r.lower()]
    installed_grafx = ver("okto-grafx")
    claude = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip() or None
    out = {
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.machine()}",
        "okto_pulse": ver("okto-pulse"),
        "okto_pulse_core": ver("okto-pulse-core"),
        "okto_grafx": installed_grafx,
        "sentence_transformers": ver("sentence-transformers"),
        "torch": ver("torch"),
        "requires_dist_grafx_line": f"Requires-Dist: {grafx_req}" if grafx_req else None,
        "requires_dist_sentence_transformers_line": f"Requires-Dist: {st_req}" if st_req else None,
        "okto_pulse_core_requires_grafx": core_reqs,
        "pulse_requires_exact_installed_grafx": bool(grafx_req and f"=={installed_grafx}" in grafx_req),
        "claude_code": claude,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "versions.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    sys.exit(main())

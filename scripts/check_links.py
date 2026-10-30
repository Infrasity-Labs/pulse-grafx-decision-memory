"""Check that every JSON file parses and every link in the Markdown files resolves.

  - JSON: every *.json and *.jsonl file outside app/, .venv/ and .work/ must parse.
  - Relative links in *.md must point at files that exist. Anchors (#...) are not checked.
  - External http(s) links are checked only with --external. A link fails on 404 or 410. Other errors
    (timeouts, 403 from bot filters) are reported as warnings and do not fail the run.

Usage: python scripts/check_links.py [--external]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|!\[[^\]]*\]\(([^)\s]+)\)")
SKIP_TOP = {"app", ".venv", ".work", ".git"}


def tracked() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True).stdout.decode()
    return [ROOT / p for p in out.split("\0") if p and Path(p).parts[0] not in SKIP_TOP and (ROOT / p).exists()]  # tracked but deleted in the working tree: skip


def check_external(url: str) -> str | None:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "link-check/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20):
            return None
    except urllib.error.HTTPError as e:
        return "FAIL" if e.code in (404, 410) else f"warn http {e.code}"
    except Exception as e:  # noqa: BLE001
        return f"warn {type(e).__name__}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--external", action="store_true")
    a = ap.parse_args()
    failures, warnings, n_json, n_links = [], [], 0, 0
    externals: dict[str, str] = {}
    for p in tracked():
        rel = p.relative_to(ROOT)
        if p.suffix in {".json", ".jsonl"}:
            n_json += 1
            try:
                if p.suffix == ".json":
                    json.loads(p.read_text())
                else:
                    for ln in p.read_text().splitlines():
                        if ln.strip():
                            json.loads(ln)
            except json.JSONDecodeError as e:
                failures.append(f"{rel}: invalid JSON ({e})")
        if p.suffix == ".md":
            for m in LINK.finditer(p.read_text()):
                target = m.group(1) or m.group(2)
                n_links += 1
                if target.startswith(("http://", "https://")):
                    externals.setdefault(target, str(rel))
                elif target.startswith(("mailto:", "#")):
                    continue
                else:
                    path_part = target.split("#", 1)[0]
                    if path_part and not (p.parent / path_part).exists():
                        failures.append(f"{rel}: broken relative link {target}")
    if a.external:
        for url, src in sorted(externals.items()):
            res = check_external(url)
            if res == "FAIL":
                failures.append(f"{src}: dead external link {url}")
            elif res:
                warnings.append(f"{src}: {url} ({res})")
    for w in warnings:
        print("warning:", w)
    for f in failures:
        print("FAIL:", f)
    print(f"json files {n_json}, links {n_links} ({len(externals)} external{'' if a.external else ', not checked'}), failures {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

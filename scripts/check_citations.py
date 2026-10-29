"""Check that every decision recorded in the graph cites a file and line that exist.

Input: a JSON file with a list of decision rows, as written by step03_recorder.py
  (each row has slug, title, content, quote). The content ends with a line `Source: <path>:<line>`.
For each decision the checker verifies:
  - the cited file exists under the repo root
  - the cited line number exists in that file
  - the quoted text, if given, appears on that line (whitespace trimmed)
Exit code 0 only if there are exactly the expected slugs and every citation holds.

Usage: python scripts/check_citations.py DECISIONS_JSON [--out RESULT_JSON] [--root REPO_ROOT]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXPECTED_SLUGS = [
    "auth-header-scheme", "token-expiry", "password-hashing", "error-response-shape",
    "pagination-parameters", "slug-rules", "comment-ownership", "favorites",
    "tag-handling", "database-access-layer", "settings-loading", "test-layout",
]
SOURCE_RE = re.compile(r"^Source:\s*(?P<path>\S+?):(?P<line>\d+)\s*$", re.MULTILINE)


def check_one(row: dict, root: Path) -> dict:
    res = {"slug": row.get("slug"), "title": row.get("title"), "ok": False, "problem": None, "file": None, "line": None}
    m = None
    for m in SOURCE_RE.finditer(row.get("content") or ""):
        pass  # keep the last match
    if not m:
        res["problem"] = "no 'Source: path:line' line in content"
        return res
    rel, line_no = m.group("path"), int(m.group("line"))
    res.update(file=rel, line=line_no)
    path = (root / rel).resolve()
    if root.resolve() not in path.parents:
        res["problem"] = "path escapes the repo root"
        return res
    if not path.is_file():
        res["problem"] = "file does not exist"
        return res
    lines = path.read_text(errors="replace").splitlines()
    if not 1 <= line_no <= len(lines):
        res["problem"] = f"line {line_no} not in file ({len(lines)} lines)"
        return res
    text = lines[line_no - 1]
    quote = (row.get("quote") or "").strip()
    res["line_text"] = text.strip()
    if quote and quote not in text:
        res["problem"] = "quote not found on the cited line"
        return res
    res["quote_checked"] = bool(quote)
    res["ok"] = True
    return res


def check(rows: list[dict], root: Path) -> dict:
    slugs = [r.get("slug") for r in rows]
    results = [check_one(r, root) for r in rows]
    missing = [s for s in EXPECTED_SLUGS if s not in slugs]
    extra = [s for s in slugs if s not in EXPECTED_SLUGS]
    dupes = sorted({s for s in slugs if slugs.count(s) > 1})
    all_ok = all(r["ok"] for r in results) and not missing and not extra and not dupes and len(rows) == len(EXPECTED_SLUGS)
    return {
        "expected": len(EXPECTED_SLUGS), "found": len(rows), "citations_ok": sum(r["ok"] for r in results),
        "missing_slugs": missing, "unexpected_slugs": extra, "duplicate_slugs": dupes, "all_ok": all_ok, "results": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("decisions_json")
    ap.add_argument("--out")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    a = ap.parse_args()
    rows = json.loads(Path(a.decisions_json).read_text())
    result = check(rows, Path(a.root))
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=2) + "\n")
    print(f"decisions={result['found']}/{result['expected']} citations_ok={result['citations_ok']} all_ok={result['all_ok']}")
    for r in result["results"]:
        if not r["ok"]:
            print(f"  FAIL {r['slug']}: {r['problem']}")
    return 0 if result["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

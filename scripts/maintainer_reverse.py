"""The Maintainer reverses one decision: error-response-shape.

This writes the reversal note that the Reviewer session reads. It does not edit the fork under app/.
The reason is invented for the demo scenario.

--no-rationale writes a second note, maintainer-reversal-no-rationale.json, that reverses slug-rules and gives no reason.
It is the failing path: a Reviewer that records it anyway has invented a reason.

Usage: python scripts/maintainer_reverse.py [--no-rationale]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import stepslib as sl  # noqa: E402

NOTE = {
    "maintainer_note_version": 1,
    "reverses_slug": "error-response-shape",
    "new_slug": "error-response-shape-v2",
    "old_choice": "HTTP errors return the JSON body {\"errors\": [detail]} with the status code of the exception (app/app/api/errors/http_error.py).",
    "new_choice": "Error responses return RFC 7807 application/problem+json with the fields type, title, status and detail.",
    "new_title": "Error responses use RFC 7807 problem+json with type, title, status and detail",
    "reason": "The public API is moving to a standard error format so client libraries can parse errors without custom code. (Invented for this demo.)",
    "scope": "Decision only. The code under app/ is not changed.",
}

NO_RATIONALE = {
    "maintainer_note_version": 1,
    "reverses_slug": "slug-rules",
    "new_slug": "slug-rules-v2",
    "old_choice": "Article slugs are generated from the title with the slugify library (app/app/services/articles.py).",
    "new_choice": "Article slugs are random identifiers.",
    "new_title": "Article slugs are random identifiers",
    "reason": "",
    "scope": "Decision only. The code under app/ is not changed.",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-rationale", action="store_true")
    a = ap.parse_args()
    out = sl.STATE / "step5" / ("maintainer-reversal-no-rationale.json" if a.no_rationale else "maintainer-reversal.json")
    note = dict(NO_RATIONALE if a.no_rationale else NOTE, reversed_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), by="Maintainer")
    sl.save_json(out, note)
    print(f"reversal note written: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out.name}")


if __name__ == "__main__":
    main()

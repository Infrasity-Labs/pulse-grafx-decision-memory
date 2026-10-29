"""The Maintainer reverses one decision: error-response-shape.

This writes the reversal note that the Reviewer session reads. It does not edit the fork under app/.
The reason is invented for the demo scenario.

Usage: python scripts/maintainer_reverse.py
"""
from __future__ import annotations

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


def main() -> None:
    out = sl.STATE / "step5" / "maintainer-reversal.json"
    note = dict(NOTE, reversed_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), by="Maintainer")
    sl.save_json(out, note)
    print(f"reversal note written: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out.name}")


if __name__ == "__main__":
    main()

"""Tiny REST helper for the local Pulse API (no auth in Community local mode)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API = f"http://127.0.0.1:{os.environ.get('PULSE_API_PORT', '8100')}/api/v1"


def rest(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, method=method, data=data, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:500]}") from None

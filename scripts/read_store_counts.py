"""Read-only Python reader for a Grafx store. Counts rows per node table and per relationship table.

Opens with connect(path, read_only=True). It never opens writable and does not retry or work around a
refusal: a refusal is recorded as is. Also probes whether commit history is enabled, using a read transaction.

With --decisions the result also lists every Decision node (id, title, content, source_artifact_ref, quote) sorted by source_artifact_ref,
so two stores can be compared by decision content and not only by counts.

Usage: python scripts/read_store_counts.py STORE_PATH [--out JSON_FILE] [--decisions]
Exit code 0 on a successful read, 4 if the read-only open was refused.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from okto_grafx import connect


def describe_exc(exc: BaseException) -> dict:
    d = {"exception_type": f"{type(exc).__module__}.{type(exc).__name__}", "message": str(exc)[:1500]}
    for attr in ("code", "field", "reason", "details", "operation"):
        if hasattr(exc, attr):
            d[attr] = json.loads(json.dumps(getattr(exc, attr), default=str))
    return d


def kind_of(t) -> str:
    k = str(getattr(t.kind, "name", getattr(t.kind, "value", t.kind))).lower()
    return "node" if "node" in k else "rel"


def read_counts(path: str, with_decisions: bool = False) -> dict:
    result: dict = {"path_name": Path(path).name, "read_only_requested": True, "opened": False}
    try:
        db = connect(path, read_only=True)
    except Exception as exc:  # recorded, never worked around by opening writable
        result["refused"] = describe_exc(exc)
        return result
    with db:
        result["opened"] = True
        result["db_read_only"] = bool(db.read_only)
        try:
            result["database_uuid"] = str(db.identity.database_uuid)
        except Exception:
            pass
        view = db.catalog.catalog if hasattr(db.catalog, "catalog") else db.catalog
        tables = view.tables()
        nodes, rels = {}, {}
        for t in tables:
            if kind_of(t) == "node":
                nodes[t.name] = db.execute(f"MATCH (n:{t.name}) RETURN count(*)").rows[0][0]
            else:
                rels[t.name] = db.execute(f"MATCH ()-[r:{t.name}]->() RETURN count(*)").rows[0][0]
        result["node_counts"] = nodes
        result["rel_counts"] = rels
        result["node_total"] = sum(nodes.values())
        result["rel_total"] = sum(rels.values())
        result["tables_total"] = len(tables)
        if with_decisions and "Decision" in nodes:
            rows = db.execute("MATCH (n:Decision) RETURN n.id, n.title, n.content, n.source_artifact_ref, n.source_span_quote").rows
            result["decisions"] = sorted(({"id": r[0], "title": r[1], "content": r[2], "source_artifact_ref": r[3], "quote": r[4]} for r in rows),
                                         key=lambda d: (d["source_artifact_ref"] or "", d["id"]))
        try:
            with db.begin("read") as tx:
                page = tx.commit_history(limit=1)
            result["commit_history"] = {"enabled": True, "entries_on_first_page": len(page.entries)}
        except Exception as exc:
            result["commit_history"] = {"enabled": False, **describe_exc(exc)}
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("store")
    ap.add_argument("--out")
    ap.add_argument("--decisions", action="store_true", help="also list every Decision node")
    a = ap.parse_args()
    res = read_counts(a.store, a.decisions)
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k not in ("node_counts", "rel_counts", "decisions")}, indent=1)[:1500])
    return 0 if res["opened"] else 4


if __name__ == "__main__":
    sys.exit(main())

"""Render the generated README blocks from the recorded outputs, so the README holds no hand-typed measurements.

Blocks (each sits between <!-- NAME:start --> and <!-- NAME:end -->):
  scoreboard  docs/SCOREBOARD.md  the full scoreboard table
  timings     docs/SCOREBOARD.md  a Mermaid pie of seconds per step
  recall      docs/SCOREBOARD.md  the ten recall questions, from demo-state/step4/recall-results.json

  python scripts/render_scoreboard.py            print every block
  python scripts/render_scoreboard.py --write    replace the blocks in their files
  python scripts/render_scoreboard.py --check    exit 1 if a file differs from the rendered blocks
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# One Mermaid theme for every diagram: dark surfaces and one purple accent, matching the banner.
MERMAID_INIT = '%%{init: {"theme":"base","themeVariables":{"fontFamily":"Helvetica, Arial, sans-serif","fontSize":"15px","primaryColor":"#17152b","primaryTextColor":"#f5f3ff","primaryBorderColor":"#7c6cf0","lineColor":"#a79de8","secondaryColor":"#1d1a38","secondaryTextColor":"#f5f3ff","secondaryBorderColor":"#8b7cf6","tertiaryColor":"#100f1e","tertiaryTextColor":"#f5f3ff","tertiaryBorderColor":"#4a4380","mainBkg":"#17152b","nodeBorder":"#7c6cf0","nodeTextColor":"#f5f3ff","clusterBkg":"#100f1e","clusterBorder":"#4a4380","titleColor":"#c4b5fd","edgeLabelBackground":"#0d0c18","textColor":"#b3add9","noteBkgColor":"#1d1a38","noteTextColor":"#f5f3ff","noteBorderColor":"#8b7cf6","actorBkg":"#17152b","actorBorder":"#7c6cf0","actorTextColor":"#f5f3ff","actorLineColor":"#4a4380","signalColor":"#a79de8","signalTextColor":"#b3add9","labelBoxBkgColor":"#1d1a38","labelBoxBorderColor":"#4a4380","labelTextColor":"#f5f3ff","loopTextColor":"#b3add9","sequenceNumberColor":"#0a0b10","pie1":"#8b7cf6","pie2":"#c4b5fd","pie3":"#6d5ae0","pie4":"#a78bfa","pie5":"#5b3fd1","pie6":"#d8ccff","pie7":"#7c6cf0","pie8":"#9b8ce8","pie9":"#4a3aa8","pieTitleTextSize":"20px","pieTitleTextColor":"#b3add9","pieSectionTextColor":"#0a0b10","pieLegendTextColor":"#b3add9","pieStrokeColor":"#0d0c18","pieStrokeWidth":"2px","pieOuterStrokeColor":"#4a4380","pieOuterStrokeWidth":"2px","pieOpacity":"0.95"}}}%%'


def counts(d: dict) -> str:
    return ", ".join(f"{v} {k}" for k, v in d.items())


def render_scoreboard(c: dict) -> str:
    v, d, r, rv = c["versions"], c["decisions"], c["recall"], c["reversal"]
    ka, kb, g = c["kill_a"], c["kill_b"], c["global_discovery"]
    nc, br = c["node_counts"], c["backup_restore"]
    ver = c["verify"]
    linux = br.get(c["backup_restore_exercised_on"], {})
    mac = br.get("darwin")
    gq = g["queries"]
    rows = [
        ("Pulse and Grafx versions", f"okto-pulse {v['okto_pulse']}, okto-pulse-core {v['okto_pulse_core']}, okto-grafx {v['okto_grafx']}"),
        ("Installed Pulse pins the installed Grafx", f"{'yes' if v['installed_pulse_requires_installed_grafx'] else 'no'} (`{v['requires_dist_grafx_line']}`)"),
        ("Embedding model", f"{c['machine']['embedding_model']} ({'stub' if c['machine']['embedding_is_stub'] else 'real model, not the stub'})"),
        ("Decisions committed in one consolidation", f"{d['committed_to_graph']} of {d['expected']}"),
        ("Cited file and line that exist", f"{d['citations_checked_and_valid']} of {d['expected']}"),
        ("Recall: right decision chosen by the Recaller", f"{r['agent_choice_correct']} of {r['questions']}"),
        ("Recall: right decision ranked first, similarity search", f"{r['similar_top1_correct']} of {r['questions']}"),
        ("Recall: right decision ranked first, natural-language search", f"{r['natural_top1_correct']} of {r['questions']}"),
        ("Recall: right decision ranked first, decision history", f"{r['history_top1_correct']} of {r['questions']} (the tool returned no decisions for sentence-length topics)"),
        ("Contradiction pairs: before, after supersede only, after explicit flag", f"{rv['contradiction_pairs_before']}, {rv['contradiction_pairs_after_supersede_only']}, {rv['contradiction_pairs_after_explicit_flag']}"),
        ("Pulse flagged the reversal as a contradiction by itself", "yes" if rv["pulse_flagged_a_contradiction_without_an_agent_edge"] else "no"),
        ("Supersedence chain length from the new decision", f"{rv['supersedence_chain_length_from_new_decision']} (queried from the old decision: {rv['supersedence_chain_length_when_queried_from_old_decision']})"),
        ("Global Discovery: expected convention found on the other board", f"{sum(q['top_is_expected'] and q['found_on_other_board'] for q in gq)} of {len(gq)}; waits {', '.join(str(q['seconds_until_result']) + ' s' for q in gq)}"),
        ("Kill A: uncommitted consolidation absent after restart", "yes" if ka["uncommitted_consolidation_absent_after_restart"] else "no"),
        ("Kill A: earlier decisions still present", f"{'yes' if ka['earlier_decisions_all_present'] else 'no'} ({ka['decisions_before']} before, {ka['decisions_after']} after)"),
        ("Kill A: board accepted a new commit", f"{ka['board_accepted_a_new_commit_seconds_after_kill']} s after the kill"),
        ("Kill B: commits acknowledged before the kill", str(kb["acknowledged_before_kill"])),
        ("Kill B: acknowledged commits present after restart", f"{kb['acknowledged_and_present_after_restart']} of {kb['acknowledged_before_kill']} ({kb['acknowledged_missing_after_restart']} missing)"),
        ("Kill B: commits in flight at the kill, and how many survived", f"{kb['in_flight_at_kill']} in flight, {kb['unacknowledged_but_present']} survived"),
        ("Kill B: board accepted a new commit", f"{kb['board_accepted_a_new_commit_seconds_after_kill']} s after the kill (refusal while waiting: `{', '.join(kb['refusal_seen_while_waiting'])}`; writer lock default TTL {kb['writer_lock_default_ttl_seconds']} s)"),
        ("Health right after the Kill A restart, as returned", f"graph_state `{c['health_after_restart_as_returned']['kill_a']['graph_state']}`, overall_state `{c['health_after_restart_as_returned']['kill_a']['overall_state']}`, dead letters {c['health_after_restart_as_returned']['kill_a']['dead_letter_count']}"),
        ("Health right after the Kill B restart, as returned", f"graph_state `{c['health_after_restart_as_returned']['kill_b']['graph_state']}`, overall_state `{c['health_after_restart_as_returned']['kill_b']['overall_state']}`, dead letters {c['health_after_restart_as_returned']['kill_b']['dead_letter_count']}"),
    ]
    for name, b in nc.items():
        rows.append((f"Node counts, {name.replace('_', ' ')}: Pulse vs direct read", f"{counts(b['pulse'])} vs {counts(b['direct_read'])}; match: {'yes' if b['nodes_match'] and b['edges_match'] else 'no'}; edges {counts(b['pulse_edges'])}"))
    rows.append(("Read-only open refused", "no" if not any(b["read_only_open_refused"] for b in nc.values()) else "yes"))
    rows.append(("Data files unchanged by the direct read", "yes" if all(b["data_files_unchanged_by_read"] for b in nc.values()) else "no"))
    vo = ver["stopped_original_store"][c["backup_restore_exercised_on"]]
    vr = ver["restored_copy"][c["backup_restore_exercised_on"]]
    rows.append(("`verify` on the stopped store", f"{vo['verdict']}, {vo['findings']} findings ({vo['pages_checked']} pages, {vo['records_checked']} records, {vo['index_entries_checked']} index entries)"))
    rows.append(("`verify` on the restored copy", f"{vr['verdict']}, {vr['findings']} findings ({vr['pages_checked']} pages, {vr['records_checked']} records, {vr['index_entries_checked']} index entries)"))
    rows.append((f"Backup and restore on {linux['platform']}", f"backup {'ok' if linux['backup_ok'] else 'refused'}, restore {'ok' if linux['restore_ok'] else 'refused'}, counts match: {'yes' if linux['counts_match_original_vs_restored'] else 'no'}, same database identity: {'yes' if linux['uuid_original_equals_restored'] else 'no'}"))
    if mac:
        rows.append((f"Backup on {mac['platform']}", f"{'ok' if mac['backup_ok'] else 'refused by Grafx'}: `{mac['backup_refusal']}`" if not mac["backup_ok"] else "ok"))
    out = ["| Item | Result |", "|---|---|"] + [f"| {a} | {b} |" for a, b in rows]
    return "\n".join(out)


def render_timings(c: dict) -> str:
    t = c["step_seconds"]
    lines = ["```mermaid", MERMAID_INIT, "pie showData title Seconds per step on this machine"]
    lines += [f'    "Step {k[4:]}" : {t[k]}' for k in sorted(t, key=lambda s: int(s[4:])) if t[k] >= 1]
    lines.append("```")
    return "\n".join(lines)


def render_recall(rec: dict) -> str:
    def cell(tool: dict) -> str:
        if not tool or not tool.get("results_returned"):
            return "no result"
        return f"{'yes' if tool['top_is_expected'] else 'NO'} ({tool['top_similarity']:.2f})"
    rows = ["| # | Question | Expected decision | Similarity top 1 | Natural-language top 1 | History | Recaller chose |", "|---:|---|---|---|---|---|---|"]
    for q in rec["per_question"]:
        t = q["tools"]
        rows.append(f"| {q['q']} | {q['question']} | `{q['expected_slug']}` | {cell(t['similar'])} | {cell(t['natural'])} | "
                    f"{t['history']['results_returned']} results | {'right' if q['agent_choice']['correct'] else 'wrong'} |")
    return "\n".join(rows)


BLOCK_FILES = {"scoreboard": "docs/SCOREBOARD.md", "timings": "docs/SCOREBOARD.md", "recall": "docs/SCOREBOARD.md"}


def blocks() -> dict[str, str]:
    c = json.loads((ROOT / "demo-state" / "closeout-result.json").read_text())
    rec = json.loads((ROOT / "demo-state" / "step4" / "recall-results.json").read_text())
    return {"scoreboard": render_scoreboard(c), "timings": render_timings(c), "recall": render_recall(rec)}


def replace_block(text: str, name: str, body: str) -> tuple[str, bool]:
    start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
    if start not in text or end not in text:
        raise SystemExit(f"no {name} markers in the target file")
    head, rest = text.split(start, 1)
    current, tail = rest.split(end, 1)
    return f"{head}{start}\n{body}\n{end}{tail}", current.strip() == body.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args()
    bl = blocks()
    if not (a.write or a.check):
        for name, body in bl.items():
            print(f"<!-- {name} -->\n{body}\n")
        return 0
    texts = {f: (ROOT / f).read_text() for f in set(BLOCK_FILES.values())}
    stale = []
    for name, body in bl.items():
        f = BLOCK_FILES[name]
        texts[f], same = replace_block(texts[f], name, body)
        if not same:
            stale.append(name)
    if a.check:
        print("generated blocks match the recorded outputs" if not stale else f"blocks differ from the recorded outputs: {', '.join(stale)}. Run: python scripts/render_scoreboard.py --write")
        return 1 if stale else 0
    for f, t in texts.items():
        (ROOT / f).write_text(t)
    print("generated blocks updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())

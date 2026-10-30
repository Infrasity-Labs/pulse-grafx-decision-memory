"""Render the generated README blocks from the recorded outputs, so the README holds no hand-typed measurements.

Blocks (each sits between <!-- NAME:start --> and <!-- NAME:end -->):
  scoreboard  docs/SCOREBOARD.md  the full scoreboard table
  timings     docs/SCOREBOARD.md  a Mermaid pie of seconds per step
  recall      docs/SCOREBOARD.md  the ten recall questions, from demo-state/step4/recall-results.json
  arms        docs/SCOREBOARD.md  every arm side by side, scored by scripts/score_arms.py from demo-state/arms/*.json
  scripted    docs/SCOREBOARD.md  the scripted run (no LLM): spec-flow gate, role denials, crash recovery, from demo-state/scripted-run/
  llmruns     docs/SCOREBOARD.md  the live model runs of the latest demo-state/llm-runs/<run id>/: smoke run and variance studies
  integration docs/SCOREBOARD.md  the dated integration and Linux container runs in demo-state/integration-*/ and linux-crash-*/
  crash       docs/SCOREBOARD.md  Kill A and Kill B of every recorded run side by side

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


ARM_ROWS = [
    ("lexical-tfidf", "Lexical baseline: tf-idf, no model", "python scripts/lexical_baseline.py"),
    ("pulse-retrieval", "Pulse and Grafx retrieval, scripted client, no LLM", "python scripts/arm_pulse_retrieval.py"),
    ("llm-memory", "LLM agent with the graph (read-only Recaller)", "python scripts/run_arms.py --arms memory"),
    ("llm-no-memory", "LLM agent with the code only", "python scripts/run_arms.py --arms no-memory"),
    ("llm-code-notes", "LLM agent with the code and plain text notes", "python scripts/run_arms.py --arms code-notes"),
]


def _cell(vals: list[int], total: int) -> str:
    """One metric over the runs of an arm: 'k of T' for one run, 'mean of T (min-max, n runs)' for several. The values are counts, never pooled."""
    if not vals:
        return "not asked"
    if len(vals) == 1:
        return f"{vals[0]} of {total}"
    mean = sum(vals) / len(vals)
    return f"{mean:.1f} of {total} ({min(vals)} to {max(vals)}, n={len(vals)})"


def render_arms() -> str:
    sys.path.insert(0, str(ROOT / "scripts"))
    import corpus
    import score_arms

    splits = ("dev", "held_out", "model_authored", "legacy")
    n = {sp: len(corpus.questions(sp)) for sp in splits}
    arms = score_arms.load_arms(ROOT / "demo-state" / "arms")

    def per_run(a: dict, sp: str, key: str) -> list[int]:
        return [r["scores"][sp][key] for r in a["run_scores"] if sp in r["scores"]]

    def totals(a: dict, sp: str, key: str) -> int:
        return next((r["scores"][sp][key] for r in a["run_scores"] if sp in r["scores"]), 0)

    def over_splits(a: dict, key: str) -> list[int]:
        return [sum(r["scores"][sp][key] for sp in r["scores"]) for r in a["run_scores"]]

    def cost(a: dict) -> str:
        runs = a.get("runs")
        if not runs:
            return "no model"
        c = [r["run_stats"]["total_cost_usd"] for r in runs]
        w = [r["run_stats"]["wall_seconds"] for r in runs]
        return f"${sum(c) / len(c):.2f} and {sum(w) / len(w):.0f} s per run (n={len(runs)}, cost {min(c):.2f} to {max(c):.2f})"

    head = "| Arm | Runs | " + " | ".join(f"Right: {sp.replace('_', '-')}" for sp in splits) + " |"
    tab1 = [head, "|---|---:|" + "---|" * len(splits)]
    tab2 = ["| Arm | Abstained on unanswerable | Fabricated an answer | Graph-only reason right | Near-duplicate right | Conflict tasks: decision found | Conflict tasks: stance adapt or stop, decision found or not | Conflict tasks: decision found and stance adapt or stop | Agent-session cost and time |", "|---|---|---|---|---|---|---|---|---|"]
    for key, label, cmd in ARM_ROWS:
        a = arms.get(key)
        if a is None:
            tab1.append(f"| {label} | 0 | " + " | ".join("not run" for _ in splits) + " |")
            tab2.append(f"| {label} | not run | not run | not run | not run | not run | not run | not run (`{cmd}`) | |")
            continue
        runs = len(a["run_scores"])
        tab1.append(f"| {label} | {runs} | " + " | ".join(_cell(per_run(a, sp, "correct"), totals(a, sp, "answerable")) for sp in splits) + " |")
        tot = lambda k: sum(totals(a, sp, k) for sp in a["run_scores"][0]["scores"])  # noqa: E731
        ts = [r["task_scores"] for r in a["run_scores"]]
        stance = ts[0]["stance_recorded"] > 0 or any(t["stance_recorded"] for t in ts)
        tab2.append(f"| {label} | {_cell(over_splits(a, 'correct_abstentions'), tot('unanswerable'))} | {_cell(over_splits(a, 'fabricated'), tot('unanswerable'))} | "
                    f"{_cell(over_splits(a, 'graph_only_correct'), tot('graph_only_total'))} | {_cell(over_splits(a, 'near_duplicate_correct'), tot('near_duplicate_total'))} | "
                    f"{_cell([t['cited'] for t in ts], ts[0]['tasks'])} | " + (f"{_cell([t['stance_adapt_or_stop'] for t in ts], ts[0]['tasks'])} | {_cell([t['respected'] for t in ts], ts[0]['tasks'])}" if stance else "no stance (not an agent) | no stance (not an agent)") + f" | {cost(a)} |")
    lex = arms["lexical-tfidf"]
    leg = lex["legacy_ten_on_recorded_twelve"]
    ran = [a for k, a in arms.items() if k.startswith("llm-")]
    notes = [
        "",
        f"Corpus: 32 decisions (12 recorded, 10 code-derived, 10 graph-only with an invented reason). Questions: dev {n['dev']}, held-out {n['held_out']}, model-authored {n['model_authored']} (written by claude-haiku-5-5, scored separately), legacy {n['legacy']}. One scorer for every arm. Abstention threshold of the lexical and Pulse arms: chosen on dev, applied to the rest. The LLM arms were asked dev, held-out and model-authored, not legacy.",
        f"For comparison, the lexical baseline on the original ten questions against only the 12 recorded decisions: {leg['top1_correct']} of {leg['questions']} (misses {', '.join(leg['misses'])}).",
        ("Each LLM arm was run " + ", ".join(f"{len(a['run_scores'])}" for a in ran) + " times (memory, no-memory, code-notes). With several runs a cell is the mean count, then the lowest and highest count and n. Nothing is pooled across arms." if ran else "The LLM arms have no recorded result."),
    ]
    return "\n".join(["**Questions answered right (answerable questions only)**", ""] + tab1 + ["", "**Everything else the scorer measures**", ""] + tab2 + notes)


def latest_llm_run() -> Path | None:
    infos = sorted((ROOT / "demo-state" / "llm-runs").glob("*/run-info.json"))
    return infos[-1].parent if infos else None


def _spread_row(label: str, s: dict | None, fmt: str = "{}") -> str | None:
    if not s or not s.get("n"):
        return None
    f = lambda v: fmt.format(round(v, 2) if isinstance(v, float) else v)  # noqa: E731
    return f"| {label} | {s['n']} | {f(s['mean'])} | {f(s['min'])} | {f(s['max'])} |"


def render_llm_runs() -> str:
    d = latest_llm_run()
    if d is None:
        return "No run with a model is recorded."
    info = json.loads((d / "run-info.json").read_text())
    out = [f"Run `{info['run_id']}`. Model requested with `--model`: `{info['model_pinned_in_config']}`; models the sessions reported: {', '.join(f'`{m}`' for m in info['models_reported_by_sessions'])}. "
           f"Claude Code {info['claude_code']}, okto-pulse {info['okto_pulse']}, okto-grafx {info['okto_grafx']}, Python {info['python']}, {info['platform']}. "
           f"{info['sessions']['count']} model sessions (smoke run, variance studies and the three arms), {info['sessions']['errors']} of them reporting an error, ${info['sessions']['total_cost_usd']:.2f} in total by the result events. "
           f"Manifest: [`run-info.json`](../demo-state/llm-runs/{d.name}/run-info.json).", ""]
    for sub in sorted(d.glob("n-runs-*")):
        s = json.loads((sub / "summary.json").read_text())
        sp = s["spread"]
        name = sub.name.removeprefix("n-runs-")
        sessions = ", ".join(s["agents_with_a_model"])
        out += [f"**Variance study `{name}`: {s['runs']} runs, each on a fresh Pulse data home. Sessions with a model: {sessions}. Generated {s['generated_at']}.**", ""]
        rows = ["| Run | Decisions the Recorder recorded | Citations that hold | Reference decisions covered (of 22) | Recaller, shared scorer: answerable right dev / held-out / model-authored | Recaller: unanswerable abstained | Reviewer: target on board, supersedes edges added, contradicts edges added, old node flagged superseded | Cost USD | Wall s |",
                "|---:|---:|---:|---:|---|---|---|---:|---:|"]
        for r in s["per_run"]:
            ag = r.get("agent_runs", {})
            cost = sum(v["total_cost_usd"] or 0 for v in ag.values())
            wall = sum(v["wall_seconds"] or 0 for v in ag.values())
            rec = r.get("recaller", {}).get("scores_by_split", {})
            has_rc = "recaller" in s["agents_with_a_model"]
            right = " / ".join(f"{rec[x]['correct']}/{rec[x]['answerable']}" if x in rec else "-" for x in ("dev", "held_out", "model_authored")) if has_rc else "not run with a model"
            abst = " / ".join(f"{rec[x]['correct_abstentions']}/{rec[x]['unanswerable']}" if x in rec else "-" for x in ("dev", "held_out", "model_authored")) if has_rc else "not run with a model"
            rv = r.get("reviewer")
            rvs = f"{rv['reversal_target_present']}, {rv['supersedes_edges']}, {rv['contradicts_edges']}, {rv['old_marked_superseded']} (reported recorded: {rv.get('reviewer_reported_recorded', 'n/a')})" if rv and "supersedes_edges" in rv else "not run"
            rec_model = "recorder" in s["agents_with_a_model"]
            out_cols = f"| {r['run']} | {r['recorder']['nodes']}{'' if rec_model else ' (scripted)'} | {r['recorder']['citations_ok']} | {r['recorder']['reference_covered']} | {right} | {abst} | {rvs} | {cost:.2f} | {wall:.0f} |"
            rows.append(out_cols)
        out += rows + ["", "| Metric over the runs | n | Mean | Min | Max |", "|---|---:|---:|---:|---:|"]
        spec = [("Decisions recorded by the Recorder", "recorder.nodes", "{}"), ("Citations that hold (file, line and quote exist)", "recorder.citations_ok", "{}"),
                ("Reference decisions covered (of 22)", "recorder.reference_covered", "{}"),
                ("Recaller right, dev (of 10 answerable)", "recaller.scores_by_split.dev.correct", "{}"), ("Recaller right, held-out (of 11)", "recaller.scores_by_split.held_out.correct", "{}"),
                ("Recaller right, model-authored (of 12)", "recaller.scores_by_split.model_authored.correct", "{}"),
                ("Recaller fabricated an answer, all splits", None, "{}"),
                ("Recaller strict choice right, all 43 questions (decision named is the expected one)", "recaller.agent_choice_correct", "{}"),
                ("Answerable questions whose expected decision is on the board (of 33)", "recaller.answerable_expected_on_board", "{}"),
                ("Pulse retrieval arm on the same board, dev right (of 10)", "pulse_retrieval_arm.dev.correct", "{}"), ("Pulse retrieval arm, held-out right (of 11)", "pulse_retrieval_arm.held_out.correct", "{}"),
                ("Reviewer: reversal target on the board", "reviewer.reversal_target_present", "{}"), ("Reviewer: supersedes edges added", "reviewer.supersedes_edges", "{}"),
                ("Reviewer: contradicts edges added", "reviewer.contradicts_edges", "{}"), ("Reviewer: Pulse contradiction pairs afterwards", "reviewer.pulse_contradiction_pairs_after", "{}"),
                ("Reviewer: old decision flagged superseded (`superseded_by` set)", "reviewer.old_marked_superseded", "{}"),
                ("Recorder session cost USD", "agent_runs.recorder.total_cost_usd", "{:.2f}"), ("Recaller session cost USD", "agent_runs.recaller.total_cost_usd", "{:.2f}"), ("Reviewer session cost USD", "agent_runs.reviewer.total_cost_usd", "{:.2f}"),
                ("Recorder wall seconds", "agent_runs.recorder.wall_seconds", "{:.0f}"), ("Recaller wall seconds", "agent_runs.recaller.wall_seconds", "{:.0f}"), ("Reviewer wall seconds", "agent_runs.reviewer.wall_seconds", "{:.0f}"),
                ("Recorder output tokens", "agent_runs.recorder.output_tokens", "{:.0f}"), ("Recaller output tokens", "agent_runs.recaller.output_tokens", "{:.0f}"), ("Reviewer output tokens", "agent_runs.reviewer.output_tokens", "{:.0f}"),
                ("Recorder turns", "agent_runs.recorder.num_turns", "{:.0f}"), ("Recaller turns", "agent_runs.recaller.num_turns", "{:.0f}")]
        ag = set(s["agents_with_a_model"])
        board = "board after the Recorder: its own decisions plus the 20 scripted ones" if "recorder" in ag else "32-decision corpus board"
        spec = [(l.replace("Pulse retrieval arm on the same board,", f"Pulse retrieval arm on the {board},").replace("Pulse retrieval arm, held-out", f"Pulse retrieval arm on the {board}, held-out"), k, f_) for l, k, f_ in spec]
        spec.insert(spec.index(next(x for x in spec if x[1] == "reviewer.supersedes_edges")), ("Reviewer reported that it recorded the reversal", "reviewer.reviewer_reported_recorded", "{}"))
        for label, key, fmt in spec:
            if key and key.split(".")[0] in ("recorder", "recaller", "reviewer") and key.split(".")[0] not in ag:
                continue
            if key and key.startswith("agent_runs.") and key.split(".")[1] not in ag:
                continue
            if key is None and "recaller" not in ag:
                continue
            if key is None:
                vals = [sum(v["fabricated"] for v in r["recaller"]["scores_by_split"].values()) for r in s["per_run"] if "recaller" in r]
                from_runs = {"n": len(vals), "mean": sum(vals) / len(vals), "min": min(vals), "max": max(vals)} if vals else None
                row = _spread_row(label, from_runs, fmt)
            else:
                row = _spread_row(label, sp.get(key), fmt)
            if row:
                out.append(row)
        out.append("")
    smoke = d / "smoke"
    if (smoke / "step4" / "recall-results.json").exists():
        rec = json.loads((smoke / "step4" / "recall-results.json").read_text())["summary"]
        cit = json.loads((smoke / "step3" / "citations.json").read_text())
        st = {r: json.loads((smoke / s / "agent" / "result.json").read_text())["run_stats"] for r, s in (("Recorder", "step3"), ("Recaller", "step4"), ("Reviewer", "step5"))}
        after = json.loads((smoke / "step5" / "after.json").read_text())
        before = json.loads((smoke / "step5" / "before.json").read_text())
        sp_ = rec["scores_by_split"]
        out += ["**Smoke run: `python run_demo.py --steps 3 4 5`, one run, goal-based prompts, dev and held-out questions only.**", "",
                "| Item | Result |", "|---|---|",
                f"| Recorder | {cit['found']} decisions, {cit['citations_ok']} with a citation that holds, {cit['reference_covered']} of {cit['reference_entries']} reference decisions covered |",
                f"| Recaller, shared scorer | dev {sp_['dev']['correct']} of {sp_['dev']['answerable']} answerable, {sp_['dev']['correct_abstentions']} of {sp_['dev']['unanswerable']} abstentions; held-out {sp_['held_out']['correct']} of {sp_['held_out']['answerable']}, {sp_['held_out']['correct_abstentions']} of {sp_['held_out']['unanswerable']} abstentions |",
                f"| Recaller write probe | {rec['write_probe'][:120]} |",
                f"| Reviewer | decisions on the board {before['decisions_total']} before, {after['decisions_total']} after the Reviewer; contradicts edges {len(after['contradicts_edges'])} |",
                f"| Cost and time | " + "; ".join(f"{k} ${v['total_cost_usd']:.2f}, {v['wall_seconds']:.0f} s" for k, v in st.items()) + " |", ""]
    return "\n".join(out).rstrip()


def render_crash() -> str:
    """Kill A and Kill B in every recorded run, side by side, read from each run's step7 files. Nothing is averaged: the runs differ in kind."""
    runs = [("Agent run 1, macOS arm64 (2026-10-29)", ROOT / "demo-state" / "step7"), ("Scripted run, macOS arm64", ROOT / "demo-state" / "scripted-run" / "step7")]
    for kind, label in (("integration", "Integration run, macOS arm64"), ("linux-crash", "Linux container run, aarch64 (Docker Desktop VM)")):
        for p in sorted((ROOT / "demo-state").glob(f"{kind}-*/step7")):
            runs.append((f"{label}, `{p.parent.name}`", p))
    head = "| Run | Kill A: draft absent after restart | Kill A: earlier decisions still there | Kill A: first write accepted | Kill B: acknowledged commits present after restart | Kill B: in flight at the kill, survived | Kill B: writes accepted again | Kill B: refusal while waiting |"
    rows = [head, "|---|---|---|---|---|---|---|---|"]
    for label, p in runs:
        a, b = json.loads((p / "killA.json").read_text()), json.loads((p / "killB.json").read_text())
        wa = a.get("write_probe_after_restart") or {}
        wb = b.get("write_probe_after_restart") or {}
        miss = len(b["acknowledged_missing"]) if isinstance(b["acknowledged_missing"], list) else b["acknowledged_missing"]
        inflight = b["in_flight_at_kill"]
        n_in = len(inflight) if isinstance(inflight, list) else inflight
        n_sur = len(b["in_flight_present"]) if isinstance(b["in_flight_present"], list) else b["in_flight_present"]
        errs = sorted({x["error"] for x in wb.get("attempts", []) if x.get("error")})
        rows.append(f"| {label} | {'yes' if a['draft_absent'] else 'NO'} | {'yes' if a['earlier_decisions_all_present'] else 'NO'} ({a['decisions_before']} before, {a['decisions_after']} after) | "
                    f"{wa.get('writes_resumed_seconds_after_kill', 'n/a')} s after the kill | "
                    f"{(len(b['acknowledged_commits']) if isinstance(b['acknowledged_commits'], list) else b['acknowledged_commits']) - miss} of {len(b['acknowledged_commits']) if isinstance(b['acknowledged_commits'], list) else b['acknowledged_commits']} | "
                    f"{n_in} in flight, {n_sur} survived | {wb.get('writes_resumed_seconds_after_kill', 'n/a')} s after the kill | {', '.join(f'`{e}`' for e in errs) or 'none'} |")
    return "\n".join(rows)


def render_integration() -> str:
    rows = ["| Run | Where | Assertions | Step 9 | Started (UTC) |", "|---|---|---|---|---|"]
    for p in sorted((ROOT / "demo-state").glob("integration-*/run-info.json")) + sorted((ROOT / "demo-state").glob("linux-crash-*/run-info.json")):
        i = json.loads(p.read_text())
        a = i["assertions"]
        skipped = ", ".join(a["skipped"]) or "none"
        kind = "Linux container" if p.parent.name.startswith("linux-crash") else "macOS host, step 9 in a Linux container"
        s9 = "ran and passed" if not a["skipped"] and p.parent.name.startswith("integration") else "not part of this run"
        rows.append(f"| `{i['run_id']}` | {kind}: {i['platform']}, Python {i['python']} | {a['checks'] - a['failed']} of {a['checks']} passed, skipped: {skipped} | {s9} | {i.get('started_at', 'not recorded')} |")
    return "\n".join(rows)


def render_scripted() -> str:
    d = ROOT / "demo-state" / "scripted-run"
    sf = json.loads((d / "step3b" / "spec-flow.json").read_text())
    ro = json.loads((d / "roles" / "role-denials.json").read_text())
    ka = json.loads((d / "step7" / "killA.json").read_text())
    kb = json.loads((d / "step7" / "killB.json").read_text())
    ck = json.loads((d / "step7" / "decision-board-check.json").read_text())
    g = sf["gate"]
    rows = ["| Item | Result |", "|---|---|",
            f"| Spec gate, refusal | `{g['refusal']['error_code']}`: {g['refusal']['message']} |",
            f"| Spec gate, pass | spec status `{g['spec_status_at_end']}` after the plan was added (edition {g['spec_edition_at_end']}) |",
            f"| Decision nodes of the approved spec, before the closeout | {sf['graph_before_closeout']['decision_nodes_by_layer']}; the Recaller found {sf['graph_before_closeout']['recaller_found_a_register_decision_by_similarity']} by similarity |",
            f"| Closeout consolidation | refused first without an Alternative edge (`{sf['closeout']['refused_without_edge']['error_code']}`), then committed: {sf['closeout']['commit']['nodes_added']} nodes added, {sf['closeout']['commit']['nodes_superseded']} working nodes superseded; the Recaller then found {sf['recaller_finds_after_closeout']} |"]
    for role, s in ro["summary"].items():
        rows.append(f"| Role {role} ({s['preset']}) | {s['denied_as_expected']} of {s['denied_actions_tried']} actions outside the preset refused ({s['by_kind']['permission']} by permission, {s['by_kind']['ownership']} by session ownership); {s['controls_succeeded']} of {s['controls_tried']} own actions succeeded |")
    rows += [
        f"| Kill A, resume with a new session | draft absent after restart: {'yes' if ka['draft_absent'] else 'no'}; after replaying six decisions, each exists exactly once: {'yes' if ka['resume']['every_slug_exactly_once'] else 'no'} (hints {ka['resume']['result']['hint_operation_by_slug']}) |",
        f"| Kill B, retry of the in-flight commits | {len(kb['retry']['retried'])} retried, {len(kb['retry']['in_flight_already_present_before_retry'])} of them already present; no slug exists twice: {'yes' if kb['retry']['every_started_slug_exactly_once'] else 'no'}; superseded by another decision during the retry: {len(kb['retry']['superseded_by_another_decision'])} |",
        f"| Decision board during step 7 | {ck['decisions_before_step7']} decisions before, {ck['decisions_after_step7']} after, unchanged: {'yes' if ck['unchanged'] else 'no'} |",
    ]
    return "\n".join(rows)


BLOCK_FILES = {"scoreboard": "docs/SCOREBOARD.md", "timings": "docs/SCOREBOARD.md", "recall": "docs/SCOREBOARD.md",
               "arms": "docs/SCOREBOARD.md", "scripted": "docs/SCOREBOARD.md", "llmruns": "docs/SCOREBOARD.md", "integration": "docs/SCOREBOARD.md", "crash": "docs/SCOREBOARD.md"}


def blocks() -> dict[str, str]:
    c = json.loads((ROOT / "demo-state" / "closeout-result.json").read_text())
    rec = json.loads((ROOT / "demo-state" / "step4" / "recall-results.json").read_text())
    return {"scoreboard": render_scoreboard(c), "timings": render_timings(c), "recall": render_recall(rec), "arms": render_arms(), "scripted": render_scripted(),
            "llmruns": render_llm_runs(), "integration": render_integration(), "crash": render_crash()}


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

"""Step 9: Grafx backup and restore on a COPY of the stopped board store. Pulse must be stopped.

Procedure (documented in Grafx docs/BACKUP_RESTORE.md):
  1. copy the store folder to a work area       2. verify the original and the copy, read-only
  3. create_backup of the copy (writable open of the copy only)
  4. restore_backup to a new folder, original participants stopped (confirm_original_offline=True)
  5. verify the restored folder                  6. compare counts and the content of every Decision node (id, title, text, source
     reference, quote) between the original, the copy and the restored folder. Pulse is never pointed at the restored folder.

Grafx 0.0.8 publishes a backup directory with an atomic no-replace rename. It supports Windows and Linux and
refuses other hosts. If the host run is refused with unsupported_operation, the same procedure is repeated in a
Linux container (IMAGE, okto-grafx==0.0.8) with the original store mounted read-only.

Usage:
  python scripts/step09_backup_restore.py                       host run, then the container run if the host refuses
  python scripts/step09_backup_restore.py --store /in --lab /work/lab --out /out --label linux-container --ro-source --no-timing --no-port-check
Output in demo-state/step9/: backup-restore-<label>.json and reader-*.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from gxutil import data_file_hashes, save_json, scrub  # noqa: E402
from okto_grafx import connect  # noqa: E402
from okto_grafx.backup import create_backup, restore_backup  # noqa: E402

STATE = Path(os.environ.get("DEMO_STATE", ROOT / "demo-state"))
# python:3.12-slim pinned by the digest of its multi-platform index, read on 2026-10-30 with `docker buildx imagetools inspect python:3.12-slim`.
# That index lists python 3.12.16 on Debian trixie for linux/amd64 and linux/arm64. The recorded run of 2026-10-29 reported python 3.12.16 but
# did not record an image digest, so the recorded run cannot be tied to this digest. A re-run can.
IMAGE = "python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159"
CLI = str(ROOT / ".venv" / "bin" / "oktografx") if (ROOT / ".venv" / "bin" / "oktografx").exists() else (shutil.which("oktografx") or "oktografx")
HERE = Path(__file__).resolve().parent


def verify_cli(path: Path) -> dict:
    p = subprocess.run([CLI, "verify", str(path), "--scope", "all", "--read-only", "--json"], capture_output=True, text=True)
    try:
        body = json.loads(p.stdout)
    except json.JSONDecodeError:
        body = {"unparsed_stdout": p.stdout[:1500]}
    return {"exit_code": p.returncode, "output": body, "stderr": scrub(p.stderr[-600:])}


def counts(path: Path, out: Path) -> dict:
    subprocess.run([sys.executable, str(HERE / "read_store_counts.py"), str(path), "--out", str(out), "--decisions"], capture_output=True, text=True)
    return json.loads(out.read_text())


def decision_view(c: dict) -> list[dict]:
    """What a reader of the store sees of each decision, without the graph id, which a restore keeps but a comparison does not need."""
    return [{k: d[k] for k in ("title", "content", "source_artifact_ref", "quote")} for d in c.get("decisions", [])]


def exc_info(exc: BaseException) -> dict:
    return {"exception_type": f"{type(exc).__module__}.{type(exc).__name__}", "message": scrub(str(exc))[:1500]}


def procedure(original: Path, lab: Path, out: Path, label: str, ro_source: bool = False) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    orig_hashes = data_file_hashes(original)
    if lab.exists():
        shutil.rmtree(lab)
    lab.mkdir(parents=True)
    copy = lab / "copy"
    shutil.copytree(original, copy, symlinks=True)
    source = original
    if ro_source:
        # A Grafx read-only open still opens bootstrap/first-open.complete, which a read-only mount refuses (errno 30).
        # So verify and count an identical copy of the original. The mount itself guarantees the source is untouched.
        source = lab / "original-copy"
        shutil.copytree(original, source, symlinks=True)
    res: dict = {"label": label, "source_was_read_only_mount": ro_source, "platform": f"{platform.system()} {platform.machine()}", "python": platform.python_version(),
                 "copied_files": sum(1 for p in copy.rglob("*") if p.is_file())}
    res["verify_original"] = verify_cli(source)
    res["verify_copy_before_backup"] = verify_cli(copy)
    backup_dir, restored_dir = lab / "backup-001", lab / "restored"
    try:
        with connect(copy) as db:  # writable open of the COPY only
            rep = create_backup(db, backup_dir, capture_mode="disk")
        res["backup"] = {"ok": True, "files": rep.files, "bytes": rep.bytes, "checkpoint_lsn": str(rep.checkpoint_lsn), "database_uuid": rep.database_uuid}
    except Exception as exc:
        res["backup"] = {"ok": False, **exc_info(exc)}
    if res["backup"]["ok"]:
        try:
            rr = restore_backup(backup_dir, restored_dir, confirm_original_offline=True)
            res["restore"] = {"ok": True, "files": rr.files, "bytes": rr.bytes, "checkpoint_lsn": str(rr.checkpoint_lsn), "database_uuid": rr.database_uuid}
        except Exception as exc:
            res["restore"] = {"ok": False, **exc_info(exc)}
    else:
        res["restore"] = {"ok": False, "skipped": "no backup to restore"}
    res["verify_restored"] = verify_cli(restored_dir) if restored_dir.exists() else {"skipped": True}
    if restored_dir.exists():
        try:
            with connect(restored_dir, read_only=True) as db:
                res["verify_restored_python_all_findings"] = len(db.verify("all").findings)
        except Exception as exc:
            res["verify_restored_python_all_findings"] = f"refused: {type(exc).__name__}: {str(exc)[:300]}"
    c_orig, c_copy = counts(source, out / f"reader-{label}-original.json"), counts(copy, out / f"reader-{label}-copy.json")
    c_rest = counts(restored_dir, out / f"reader-{label}-restored.json") if restored_dir.exists() else {"opened": False}
    strip = lambda c: {"nodes": c.get("node_counts"), "rels": c.get("rel_counts")}  # noqa: E731
    res["counts"] = {"original": strip(c_orig), "copy": strip(c_copy), "restored": strip(c_rest)}
    res["counts_match"] = {"original_vs_copy": strip(c_orig) == strip(c_copy),
                           "original_vs_restored": bool(c_rest.get("opened")) and strip(c_orig) == strip(c_rest)}
    d_orig, d_copy, d_rest = decision_view(c_orig), decision_view(c_copy), decision_view(c_rest)
    res["decisions"] = {
        "original_count": len(d_orig), "restored_count": len(d_rest),
        "titles_restored": [d["title"] for d in d_rest], "source_lines_restored": [d["content"].rsplit("Source: ", 1)[-1].strip() for d in d_rest if "Source: " in (d["content"] or "")],
        "original_vs_copy": bool(d_orig) and d_orig == d_copy, "original_vs_restored": bool(d_orig) and d_orig == d_rest,
        "ids_original_vs_restored": [d["id"] for d in c_orig.get("decisions", [])] == [d["id"] for d in c_rest.get("decisions", [])],
    }
    res["original_untouched"] = data_file_hashes(original) == orig_hashes
    res["uuid_original_equals_restored"] = bool(c_rest.get("database_uuid")) and c_orig.get("database_uuid") == c_rest.get("database_uuid")
    res["note"] = "Pulse was not started against the restored folder. The restored store keeps the original database identity."
    save_json(out / f"backup-restore-{label}.json", res)
    return res


def docker_ready() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def run_in_linux_container(original: Path, out: Path) -> dict:
    cmd = ["docker", "run", "--rm", "-v", f"{original}:/in:ro", "-v", f"{HERE}:/scripts:ro", "-v", f"{ROOT / 'constraints.txt'}:/constraints.txt:ro", "-v", f"{out}:/out",
           IMAGE, "bash", "-c",
           "pip install -q --disable-pip-version-check -c /constraints.txt 'okto-grafx[accel]==0.0.8' 2>&1 | tail -2 && "
           "python /scripts/step09_backup_restore.py --store /in --lab /work/lab --out /out --label linux-container --ro-source --no-timing --no-port-check"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    print(scrub(p.stdout[-1500:]))
    if p.returncode != 0:
        print(scrub(p.stderr[-800:]), file=sys.stderr)
    f = out / "backup-restore-linux-container.json"
    return json.loads(f.read_text()) if f.exists() else {"error": "container run produced no result", "exit_code": p.returncode}


def summary(res: dict) -> str:
    return (f"[{res.get('label')}] backup_ok={res.get('backup', {}).get('ok')} restore_ok={res.get('restore', {}).get('ok')} "
            f"counts_match={res.get('counts_match')} decisions_match={ {k: v for k, v in res.get('decisions', {}).items() if k.startswith('original_vs')} } original_untouched={res.get('original_untouched')} "
            f"verify_exit original={res.get('verify_original', {}).get('exit_code')} copy={res.get('verify_copy_before_backup', {}).get('exit_code')} "
            f"restored={res.get('verify_restored', {}).get('exit_code')}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store")
    ap.add_argument("--lab")
    ap.add_argument("--out")
    ap.add_argument("--label")
    ap.add_argument("--ro-source", action="store_true", help="the source store is on a read-only mount")
    ap.add_argument("--no-timing", action="store_true")
    ap.add_argument("--no-port-check", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    out = Path(a.out) if a.out else STATE / "step9"
    if not a.no_port_check:
        api, mcp = os.environ.get("PULSE_API_PORT", "8100"), os.environ.get("PULSE_MCP_PORT", "8101")
        if subprocess.run(["lsof", f"-iTCP:{api}", f"-iTCP:{mcp}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.strip():
            print(f"Pulse is still listening on {api} or {mcp}. Stop it first (scripts/stop_pulse.sh).")
            return 2
    if a.store:
        original = Path(a.store)
    else:
        home = Path(os.environ.get("PULSE_HOME", ROOT / ".work" / "pulse-home"))
        board = json.loads((STATE / "step2" / "board.json").read_text())["board_id"]
        binding = json.loads((home / "boards" / board / "graph_backend_binding.json").read_text())
        original = home / binding["physical_path"]
    lab = Path(a.lab) if a.lab else ROOT / ".work" / "restore-lab"
    label = a.label or platform.system().lower()
    res = procedure(original, lab, out, label, ro_source=a.ro_source)
    print(summary(res))
    rc = 0
    if not a.label and not res["backup"]["ok"] and "unsupported_operation" in res["backup"].get("message", ""):
        print("Host refused the backup (platform). Repeating the same procedure in a Linux container.")
        if docker_ready():
            linux = run_in_linux_container(original, out)
            print(summary(linux))
            rc = 0 if linux.get("restore", {}).get("ok") else 1
        else:
            print("Docker is not available, so the restore could not be exercised on a supported platform.")
            rc = 1
    if not a.no_timing:
        tp = STATE / "timings.json"
        t = json.loads(tp.read_text()) if tp.exists() else {}
        t["step9"] = round(time.time() - t0, 1)
        save_json(tp, t)
    return rc


if __name__ == "__main__":
    sys.exit(main())

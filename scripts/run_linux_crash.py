"""Run the integration phases up to the crash step (Kill A, Kill B) in a Linux container. No model, no secret.

The macOS run of step 7 (recorded in demo-state/step7/ and demo-state/scripted-run/) killed Pulse on a Mac. This runs the same scripts, with the
same pins (requirements.txt and constraints.txt, installed with a CPU build of torch), inside a Linux container, so the SIGKILL and the restart
happen on a Linux kernel with the data home on the container's own filesystem. The container is a Docker Desktop VM on this machine: its kernel
is Linux and its CPU is the host's, but it is still a virtual machine and not a bare-metal Linux host.

Phases run inside: setup, memory, reversal, global, crash, read, assert (step 9 is the restore step and is not part of this run).

  python scripts/run_linux_crash.py --out DIR [--no-build] [--require-docker-config PATH]

Needs Docker. With a temporary HOME the Docker CLI context is hidden: set DOCKER_CONFIG to the real Docker config folder.
Output in DIR: container-info.txt, run-integration.log, exit-code.txt, state/ (the same layout as a normal run), logs/, linux-run-info.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE = "pgdm-linux:pins"


def docker(*args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, **kw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-build", action="store_true", help="use an image that already exists under the name pgdm-linux:pins")
    a = ap.parse_args()
    if docker("info").returncode != 0:
        print("Docker is not available (is Docker running, and is DOCKER_CONFIG set when HOME is temporary?)", file=sys.stderr)
        return 2
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not a.no_build:
        with tempfile.TemporaryDirectory() as ctx:
            for f in ("requirements.txt", "constraints.txt"):
                shutil.copy(ROOT / f, ctx)
            b = subprocess.run(["docker", "build", "-t", IMAGE, "-f", str(ROOT / "docker" / "Dockerfile.linux"), ctx])
            if b.returncode != 0:
                return b.returncode
    t0 = time.time()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rc = subprocess.call(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/src:ro", "-v", f"{out}:/out", IMAGE, "bash", "/src/scripts/linux_entry.sh"])
    seconds = round(time.time() - t0, 1)
    inner = (out / "exit-code.txt").read_text().strip() if (out / "exit-code.txt").exists() else None
    image_id = docker("image", "inspect", IMAGE, "--format", "{{.Id}}").stdout.strip()
    ver = docker("version", "--format", "{{.Server.Version}} {{.Server.Os}}/{{.Server.Arch}}").stdout.strip()
    pins = docker("run", "--rm", IMAGE, "python", "-c",
                  "import importlib.metadata as m,platform;print(__import__('json').dumps({**{p:m.version(p) for p in ('okto-pulse','okto-pulse-core','okto-grafx','sentence-transformers','torch','fastmcp')},'python':platform.python_version()}))").stdout.strip()
    info = {"what": "Integration phases setup, memory, reversal, global, crash, read and assert in a Linux container. Scripted agents, no model.",
            "started_at": started, "wall_seconds": seconds, "docker_run_exit": rc, "inner_exit": inner, "docker_server": ver, "image": IMAGE, "image_id": image_id,
            "base_image": "python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159", "packages": json.loads(pins) if pins else None}
    (out / "linux-run-info.json").write_text(json.dumps(info, indent=2) + "\n")
    print(f"container run finished: docker exit {rc}, inner exit {inner}, {seconds} s. output in {out}")
    return 0 if rc == 0 and inner == "0" else 1


if __name__ == "__main__":
    sys.exit(main())

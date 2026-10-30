#!/usr/bin/env bash
# Runs INSIDE the Linux container started by scripts/run_linux_crash.py. Do not run it on a host.
# Copies the repo (mounted read-only at /src) to /repo, points .venv at the packages installed in the image, runs the integration phases up to
# and including the crash step (Kill A and Kill B), the direct read and the assertions, then copies the state out to /out.
# Pulse's data home and the crash boards are on the container's own filesystem (/work), not on a mount from the host.
set -euo pipefail
test -d /src/scripts && test -d /out
mkdir -p /repo
(cd /src && tar --exclude=.git --exclude=.venv --exclude=.work --exclude=__pycache__ -cf - .) | tar -xf - -C /repo
cd /repo
mkdir -p .venv/bin
for b in python okto-pulse oktografx; do ln -sf "/usr/local/bin/$b" ".venv/bin/$b"; done
export PYTHONWARNINGS=ignore
{
  echo "uname: $(uname -srm)"
  echo "kernel_release: $(uname -r)"
  echo "os: $(. /etc/os-release && echo "$PRETTY_NAME")"
  echo "filesystem_of_work: $(df -T /work 2>/dev/null | tail -1 | awk '{print $2}')"
  echo "cpus: $(nproc)"
} > /out/container-info.txt
rc=0
python scripts/run_integration.py --work /work --phases setup memory reversal global crash read assert > /out/run-integration.log 2>&1 || rc=$?
mkdir -p /out/state
cp -R /work/state/. /out/state/
mkdir -p /out/logs
cp /work/logs/* /out/logs/ 2>/dev/null || true
echo "$rc" > /out/exit-code.txt
exit 0

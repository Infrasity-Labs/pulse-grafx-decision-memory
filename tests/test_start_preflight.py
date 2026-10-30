"""scripts/start_pulse.sh refuses to start on a port that is taken and leaves the other process alone."""
import socket
import subprocess
import sys

import pytest

from conftest import ROOT


@pytest.mark.skipif(sys.platform == "win32", reason="bash script")
@pytest.mark.parametrize("busy", ["api", "mcp"])
def test_busy_port_stops_the_start_and_changes_nothing(busy, tmp_path):
    api, mcp = socket.socket(), socket.socket()
    api.bind(("127.0.0.1", 0)); mcp.bind(("127.0.0.1", 0))
    for s in (api, mcp):
        s.listen(1)
    free = socket.socket(); free.bind(("127.0.0.1", 0)); free_port = free.getsockname()[1]; free.close()
    ports = {"api": api.getsockname()[1] if busy == "api" else free_port, "mcp": mcp.getsockname()[1] if busy == "mcp" else free_port}
    env = {"PATH": "/usr/bin:/bin", "PULSE_HOME": str(tmp_path / "home"), "PULSE_API_PORT": str(ports["api"]), "PULSE_MCP_PORT": str(ports["mcp"])}
    try:
        p = subprocess.run(["bash", str(ROOT / "scripts" / "start_pulse.sh")], env=env, capture_output=True, text=True, timeout=30)
    finally:
        api.close(); mcp.close()
    assert p.returncode == 3
    assert str(ports[busy]) in p.stderr and "already in use" in p.stderr and "Nothing was changed" in p.stderr
    assert not (ROOT / ".work" / f"pulse-{ports['api']}.pid").exists()
    assert not (tmp_path / "home").exists()

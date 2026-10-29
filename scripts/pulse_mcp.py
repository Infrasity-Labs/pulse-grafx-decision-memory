"""Small MCP client for the local Pulse server. Keys are read from agents/.keys.local and never printed.

Usage:
  python scripts/pulse_mcp.py ROLE tools
  python scripts/pulse_mcp.py ROLE call TOOL '{"json": "args"}'
  python scripts/pulse_mcp.py ROLE resources
  python scripts/pulse_mcp.py ROLE resource URI
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

ROOT = Path(__file__).resolve().parent.parent
KEYS = Path(os.environ.get("PULSE_KEYS_FILE", ROOT / "agents" / ".keys.local"))
MCP_URL = os.environ.get("PULSE_MCP_URL", "http://127.0.0.1:8101/mcp")


def load_key(role: str) -> str:
    for line in KEYS.read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip().upper() == role.upper():
            return value.strip()
    raise SystemExit(f"no key for role {role} in agents/.keys.local")


def client(role: str) -> Client:
    transport = StreamableHttpTransport(MCP_URL, headers={"Authorization": f"Bearer {load_key(role)}"})
    return Client(transport)


def dump(obj) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    return json.dumps(obj, indent=2, default=str)


async def main(argv: list[str]) -> int:
    role, cmd, *rest = argv
    async with client(role) as c:
        if cmd == "tools":
            for t in await c.list_tools():
                print(t.name)
        elif cmd == "describe":
            for t in await c.list_tools():
                if t.name == rest[0]:
                    print(t.description)
                    print(json.dumps(t.inputSchema, indent=2))
        elif cmd == "call":
            res = await c.call_tool(rest[0], json.loads(rest[1]) if len(rest) > 1 else {}, raise_on_error=False)
            payload = res.structured_content if res.structured_content is not None else [getattr(x, "text", str(x)) for x in res.content]
            print(json.dumps({"is_error": res.is_error, "result": payload}, indent=2, default=str))
        elif cmd == "resources":
            for r in await c.list_resources():
                print(r.uri, "|", r.name)
        elif cmd == "resource":
            for part in await c.read_resource(rest[0]):
                print(getattr(part, "text", part))
        else:
            raise SystemExit(f"unknown command {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))

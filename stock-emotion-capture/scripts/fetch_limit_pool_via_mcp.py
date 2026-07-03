#!/usr/bin/env python3
"""Call an MCP stock server and save get_limit_pool payload through the bridge."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

try:
    from scripts.bridge_limit_pool_payload import bridge_payload
except ModuleNotFoundError:  # pragma: no cover - direct script execution fallback
    from bridge_limit_pool_payload import bridge_payload


async def fetch_limit_pool(date: str, *, mcp_cwd: str, command: str) -> dict:
    params = StdioServerParameters(
        command=command,
        args=["run", "python", "-m", "mcp_stock"],
        cwd=mcp_cwd,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("get_limit_pool", {"date": date, "pool": "both"})
            if result.isError:
                raise RuntimeError(result.content)
            text_parts = [item.text for item in result.content if hasattr(item, "text")]
            if not text_parts:
                raise RuntimeError("get_limit_pool returned no text content")
            return json.loads("\n".join(text_parts))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch get_limit_pool through MCP stdio and save raw/organized JSON."
    )
    parser.add_argument("--date", required=True, help="Trading date in YYYYMMDD format.")
    parser.add_argument(
        "--mcp-cwd",
        default="/Users/didiapp/dev/mcp/mcp_stock",
        help="Directory of the mcp_stock project.",
    )
    parser.add_argument("--command", default="uv", help="Command used to launch the MCP server.")
    parser.add_argument("--include-special", action="store_true", help="Include ST and new stocks.")
    parser.add_argument("--user-text", default="", help="Original user request text.")
    parser.add_argument("--raw-output", type=Path, help="Raw payload output path.")
    parser.add_argument("--organized-output", type=Path, help="Organized JSON output path.")
    args = parser.parse_args()

    payload = asyncio.run(fetch_limit_pool(args.date, mcp_cwd=args.mcp_cwd, command=args.command))
    summary = bridge_payload(
        json.dumps(payload, ensure_ascii=False),
        date=args.date,
        include_special=args.include_special,
        user_text=args.user_text,
        raw_output=args.raw_output,
        organized_output=args.organized_output,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Separate OpenAI Agents SDK client; caller credentials never enter tool inputs."""

from __future__ import annotations

import asyncio
import json
import os

from agents import Agent, Runner, set_tracing_disabled
from agents.mcp import MCPServerStreamableHttp

from server import TOOL, local_url

set_tracing_disabled(True)


def connection(url: str, token: str | None):
    return MCPServerStreamableHttp(
        name="local-workstream-experiment", params={
            "url": local_url(url) + "/mcp",
            "headers": {"Authorization": "Bearer " + token} if token else {},
            "timeout": 15,
        }, client_session_timeout_seconds=20, max_retry_attempts=0,
        use_structured_content=True,
    )


async def main():
    async with connection(os.environ["MCP_EXPERIMENT_URL"],
                          os.environ.get("MCP_EXPERIMENT_CALLER_TOKEN")) as client:
        if os.environ.get("MCP_EXPERIMENT_MODEL"):
            # Opt-in live inference; token exists only in transport headers.
            agent = Agent(name="Profile drill", model=os.environ["MCP_EXPERIMENT_MODEL"],
                          instructions="Call workstream_profile_get once. Report its result.",
                          mcp_servers=[client])
            result = await Runner.run(agent, "Read my Workstream profile.", max_turns=3)
            print(result.final_output)
        else:
            result = await client.call_tool(TOOL, {})
            print(json.dumps(result.model_dump(mode="json")))


if __name__ == "__main__":
    asyncio.run(main())

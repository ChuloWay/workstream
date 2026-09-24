import re
from pathlib import Path

ROOT = Path("/Users/victor/Documents/FlowResearch/workstream")
MCP_DIR = ROOT / "mcp_server"

files_to_check = {
    "test_profile_flow.py": MCP_DIR / "tests/integration/test_profile_flow.py",
    "server.py": MCP_DIR / "workstream_mcp/server.py",
    "test_catalogue.py": MCP_DIR / "tests/test_catalogue.py",
    "WS-MCP-002-01.md": ROOT / ".commitrail/initiatives/WS-MCP-002/WS-MCP-002-01.md",
    "uv.lock": MCP_DIR / "uv.lock"
}

def check(file_key, expected_strings, unexpected_strings=None):
    content = files_to_check[file_key].read_text()
    for s in expected_strings:
        if s not in content:
            return f"❌ Missing expected string in {file_key}: {s}"
    if unexpected_strings:
        for s in unexpected_strings:
            if s in content:
                return f"❌ Found unexpected string in {file_key}: {s}"
    return f"✅ {file_key} is verified."

results = []

# 1. httpx.AsyncClient leak fixed (async with wrapper)
results.append(check("test_profile_flow.py", ["async with httpx.AsyncClient("]))

# 2. Overlap proof moved to backend boundary (the proxy)
results.append(check("test_profile_flow.py", ["proxy_barrier = asyncio.Barrier(2)", "if request.url.path == \"/api/v1/actors/me\""]))

# 3. Task cancellation leak fixed (disconnect_event check)
results.append(check("server.py", ["if disconnect_event.is_set():", "manager_task.cancel()"]))

# 4. Legacy initialize/2025-11-25 removed completely
results.append(check("test_catalogue.py", ["\"mcp-method\": \"server/discover\""], ["initialize", "2025-11-25"]))
results.append(check("test_profile_flow.py", ["Client("], ["ClientSession", "initialize"]))

# 5. CommitRail baseline and concurrency evidence updated
results.append(check("WS-MCP-002-01.md", ["protocol `2026-07-28`.", "sequential alternating"], ["legacy compatibility"]))

# 6. uv.lock metadata exact pin
results.append(check("uv.lock", ["{ name = \"mcp\", specifier = \"==2.2.0\" }"], ["{ name = \"mcp\", specifier = \">=2\" }"]))

for r in results:
    print(r)

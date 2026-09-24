import os
import subprocess
import re
from pathlib import Path

def check_file(path, must_contain=None, must_not_contain=None):
    with open(path, "r") as f:
        content = f.read()
    
    errors = []
    if must_contain:
        for c in must_contain:
            if c not in content:
                errors.append(f"Missing required string: {c}")
    if must_not_contain:
        for c in must_not_contain:
            if c in content:
                errors.append(f"Found forbidden string: {c}")
    return errors

def run_checks():
    ROOT = Path("/Users/victor/Documents/FlowResearch/workstream")
    MCP_DIR = ROOT / "mcp_server"
    
    results = {}
    
    # 1. pyproject.toml
    results["pyproject.toml"] = check_file(
        MCP_DIR / "pyproject.toml",
        must_contain=['"mcp==2.2.0"'],
        must_not_contain=['"mcp>=2"']
    )
    
    # 2. uv.lock
    results["uv.lock"] = check_file(
        MCP_DIR / "uv.lock",
        must_contain=['name = "mcp"', 'specifier = "==2.2.0"'],
        must_not_contain=['specifier = ">=2"']
    )
    
    # 3. Evidence file
    evidence = ROOT / ".commitrail/initiatives/WS-MCP-002/WS-MCP-002-01.md"
    results["evidence"] = check_file(
        evidence,
        must_contain=[
            "Executed baseline: MCP 2.2.0, OpenAI Agents 0.22.2, protocol `2026-07-28`.",
            "sequential alternating requests from different callers",
            "tests/integration/test_profile_flow.py::test_installed_mcp_preserves_profile_and_lifecycle_parity"
        ],
        must_not_contain=["2025-11-25", "legacy compatibility", "initialize", "ClientSession"]
    )
    
    # 4. test_catalogue.py
    results["test_catalogue"] = check_file(
        MCP_DIR / "tests/test_catalogue.py",
        must_contain=['mcp-method": "server/discover"', 'io.modelcontextprotocol/protocolVersion": "2026-07-28"'],
        must_not_contain=["2025-11-25", "initialize", "ClientSession", "legacy"]
    )
    
    # 5. test_profile_flow.py
    results["test_profile_flow"] = check_file(
        MCP_DIR / "tests/integration/test_profile_flow.py",
        must_contain=[
            'from mcp import Client',
            'async with Client(server=transport, mode="2026-07-28") as client:',
            'assert client.protocol_version == "2026-07-28"',
            'asyncio.gather(*tasks)'
        ],
        must_not_contain=["2025-11-25", "initialize", "ClientSession", "legacy"]
    )
    
    # 6. server.py (Ingress limits)
    results["server.py"] = check_file(
        MCP_DIR / "workstream_mcp/server.py",
        must_contain=[
            'class IngressTimeoutError(IngressLimitError):',
            'status_code: int = 408',
            'class IngressPayloadTooLargeError(IngressLimitError):',
            'status_code: int = 413',
            'class IngressFrameLimitError(IngressLimitError):',
            'status_code: int = 400',
            'limit_error = IngressPayloadTooLargeError()',
            'limit_error = IngressFrameLimitError()'
        ]
    )

    # 7. test_protocol.py (Ingress tests)
    results["test_protocol.py"] = check_file(
        MCP_DIR / "tests/test_protocol.py",
        must_contain=[
            'test_asgi_ingress_limits',
            'assert resp["status"] == 400',
            'assert resp["status"] == 408',
            'assert resp["status"] == 413'
        ],
        must_not_contain=["2025-11-25", "initialize", "ClientSession", "legacy"]
    )

    all_passed = True
    for name, errors in results.items():
        if errors:
            all_passed = False
            print(f"❌ {name} failed:")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"✅ {name} passed")
            
    if all_passed:
        print("\nAll file content checks passed perfectly!")

if __name__ == "__main__":
    run_checks()

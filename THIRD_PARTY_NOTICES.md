# Third-party notices

Workstream uses third-party packages installed from
[`backend/pyproject.toml`](backend/pyproject.toml) and resolved in
[`backend/uv.lock`](backend/uv.lock), and, for the independently packaged MCP
adapter, from [`mcp_server/pyproject.toml`](mcp_server/pyproject.toml) and
resolved in [`mcp_server/uv.lock`](mcp_server/uv.lock). Its wheel and container
image each carry their own resolved dependency set. Those packages are not
relicensed under
Workstream's AGPL-3.0-only license; each remains governed by its upstream
license and notices.

At the time this notice was added, the repository did not contain a dedicated
third-party or vendor directory, and a repository scan found no third-party
source or binary copied into Workstream for redistribution. Direct package URLs
in `backend/pyproject.toml` identify dependencies downloaded during environment
setup; the referenced package files are not stored in this repository.

This file is not a complete transitive dependency-license inventory. Before
distributing a built Workstream artifact, use the resolved dependency set to
identify and preserve all licenses, copyright notices, attribution files, and
source-offer obligations required by those dependencies. Any future change that
copies or modifies third-party material in the repository must add the relevant
upstream license and notice here or in a linked, package-specific notice file.

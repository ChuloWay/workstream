# Third-party notices

Workstream uses third-party packages installed from
[`backend/pyproject.toml`](backend/pyproject.toml) and resolved in
[`backend/uv.lock`](backend/uv.lock), and, for the independently packaged MCP
adapter, from [`mcp_server/pyproject.toml`](mcp_server/pyproject.toml) and
resolved in [`mcp_server/uv.lock`](mcp_server/uv.lock). Its wheel and container
image each carry their own resolved dependency set. The Rust external checkers
resolve crates from [`external_checkers/Cargo.toml`](external_checkers/Cargo.toml)
in [`external_checkers/Cargo.lock`](external_checkers/Cargo.lock), and the Go CLI
resolves modules from [`cli/go.mod`](cli/go.mod) in [`cli/go.sum`](cli/go.sum). Those packages are not
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

## Go CLI modules

The Go CLI statically links these modules into its binary. Each module's
license text is in its module source.

| Module | Version | License |
| --- | --- | --- |
| [`github.com/spf13/cobra`](https://github.com/spf13/cobra) | v1.10.2 | Apache-2.0 |
| [`github.com/spf13/pflag`](https://github.com/spf13/pflag) | v1.0.9 | BSD-3-Clause |
| [`github.com/inconshreveable/mousetrap`](https://github.com/inconshreveable/mousetrap) | v1.1.0 | Apache-2.0 |

Update this table when `cli/go.mod` changes. A distributed CLI binary must
carry these modules' license and notice texts.

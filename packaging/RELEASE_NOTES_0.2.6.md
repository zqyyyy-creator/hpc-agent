# HPC Agent 0.2.6

Release date: 2026-07-13

## Summary

HPC Agent 0.2.6 adds external MCP tools injection. HPC Agent can now act as an MCP Client, connect to third-party MCP Servers, discover allowed tools, and inject them into the local agent tool system as `external_<server>_<tool>`.

## Added

- Added `hpc-agent-mcp-client` console command.
- Added external MCP Server configuration:

```text
config/external_mcp_servers.yaml
```

- Added support for external MCP transports:

```text
stdio
streamable_http
```

- Added external MCP tools discovery and `allowed_tools` whitelist filtering.
- Added injected tool naming:

```text
external_<server>_<tool>
```

- Added CLI workflows:

```text
hpc-agent-mcp-client doctor
hpc-agent-mcp-client list-tools
hpc-agent-mcp-client call external_filesystem_read_file '{"path":"README.md"}'
```

- Added external MCP audit log:

```text
~/.local/share/hpc-agent/external_mcp_audit.jsonl
```

- Added natural-language use of injected external MCP tools through TUI / `hpc_agent_chat`.
- Added external MCP injection documentation:

```text
docs/mcp_docs/EXTERNAL_MCP_INJECTION.md
```

- Added fake stdio MCP server fixture and regression tests for config loading, list tools, whitelist filtering, tool calls, audit logging, and chat integration.

## Changed

- Updated package version to `0.2.6`.
- Updated install script to link `hpc-agent-mcp-client` into the user bin directory.
- Updated package data to include the external MCP config template and docs.
- Updated release site text for hpc-agent 0.2.6.
- Updated README and docs index for external MCP tools injection.

## Compatibility

- Required Python: 3.12+
- Main command: `hpc-agent`
- Config check command: `hpc-agent-check`
- Initializer command: `hpc-agent-init`
- MCP Server command: `hpc-agent-mcp`
- External MCP Client command: `hpc-agent-mcp-client`

## Upgrade

Anonymous public-download install:

```bash
curl -fL \
  "https://artifacts-cn-beijing.volces.com/repository/agents/models/ai-llm/hpc-agent/stable/install.sh" \
  -o /tmp/hpc-agent-install.sh

sh /tmp/hpc-agent-install.sh
```

Force reinstall:

```bash
HPC_AGENT_FORCE_REINSTALL=1 sh /tmp/hpc-agent-install.sh
```

## Verification

Verify the installed version:

```bash
"$HOME/.local/share/hpc-agent/.venv/bin/python" -c "import importlib.metadata as m; print(m.version('hpc-agent'))"
```

Expected output:

```text
0.2.6
```

Verify external MCP client CLI:

```bash
hpc-agent-mcp-client doctor
hpc-agent-mcp-client list-tools
```

Default configuration is intentionally disabled, so `list-tools` may report no injected tools until users enable an external MCP Server in `config/external_mcp_servers.yaml` or set `HPC_AGENT_EXTERNAL_MCP_CONFIG`.

## Safety Defaults

- External MCP injection is disabled by default.
- Each external server must be explicitly enabled with `enabled: true`.
- Only tools listed in `allowed_tools` are injected.
- Empty `allowed_tools` means no tools are injected.
- External MCP calls are audited with secret scrubbing.


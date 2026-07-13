# HPC Agent 0.2.5

Release date: 2026-07-13

## Summary

HPC Agent 0.2.5 adds a general MCP server interface for external AI/MCP clients, improves Slurm/VASP structured workflows, and updates the release package for anonymous public download.

## Added

- Added `hpc-agent-mcp` console command.
- Added MCP server support over STDIO and Streamable HTTP.
- Added HTTP health endpoint:

```text
/health
```

- Added primary natural-language MCP tool:

```text
hpc_agent_chat
```

- Added structured MCP tools for generic clients:

```text
hpc_generate_sbatch_structured
hpc_prepare_vasp_job_structured
vasp_generate_inputs_structured
vasp_analyze_local_result_structured
vasp_sync_output_structured
hpc_query_job_structured
hpc_prepare_cleanup_structured
```

- Added guarded MCP execution tools:

```text
hpc_submit_prepared_job
vasp_sync_output
hpc_execute_cleanup
```

- Added MCP resources for discovery and client behavior:

```text
hpc-agent://capabilities
hpc-agent://schema/tools
hpc-agent://security/policy
hpc-agent://examples
hpc-agent://deployment/status
hpc-agent://jobs/recent
hpc-agent://config/status
hpc-agent://skills
hpc-agent://cluster/info
hpc-agent://docs/user-guide
```

- Added MCP prompt templates for Slurm submit, Slurm diagnosis, VASP workflows, local VASP analysis, cleanup, natural-language use, and connection debugging.
- Added MCP audit logging with secret scrubbing.
- Added MCP Streamable HTTP startup script:

```text
scripts/start_mcp_http.sh
```

- Added user-level systemd template:

```text
packaging/systemd/hpc-agent-mcp.service
```

- Added dedicated MCP docs directory:

```text
docs/mcp_docs/
```

- Added generic MCP client guide:

```text
docs/mcp_docs/MCP_CLIENTS.md
```

- Added ChatGPT Web setup and metadata docs as client-specific examples, not as a ChatGPT-only protocol.

## Changed

- Updated package version to `0.2.5`.
- Added `mcp[cli]` dependency.
- Updated package data so MCP docs, startup script, and systemd service are included in built distributions.
- Updated install and release docs for anonymous public download. Users no longer need repository username, password, token, or `curl -u`.
- Updated release site text for hpc-agent 0.2.5.
- Updated Docker docs for hpc-agent 0.2.5.
- Improved Slurm parser compatibility for structured/labeled text such as:

```text
command: hostname
nodes: 1
time: 00:05:00
partition: amd_test
```

- Improved routing so explicit Slurm preview requests are not confused with test-file generation or parameter suggestions.
- Improved VASP local analysis path compatibility for direct output directories, `raw_output` directories, and collection directories containing multiple jobs.

## Fixed

- Fixed MCP client Slurm preview cases where the command field was not recognized.
- Fixed Streamable HTTP tunnel usage by supporting explicit allowed Host headers.
- Fixed MCP startup script `.env` loading so shell commands containing spaces do not break startup.
- Fixed VASP analysis behavior for empty or collection-style output directories by returning clearer candidate-directory guidance.

## Compatibility

- Required Python: 3.12+
- Main command: `hpc-agent`
- Config check command: `hpc-agent-check`
- Initializer command: `hpc-agent-init`
- MCP command: `hpc-agent-mcp`

## Upgrade

Anonymous public-download install:

```bash
curl -fL \
  "https://artifacts-cn-beijing.volces.com/repository/agents/models/ai-llm/hpc-agent/stable/install.sh" \
  -o /tmp/hpc-agent-install.sh

sh /tmp/hpc-agent-install.sh
```

Force reinstall the same version:

```bash
HPC_AGENT_FORCE_REINSTALL=1 sh /tmp/hpc-agent-install.sh
```

## Verification

After installation:

```bash
hpc-agent-check
hpc-agent
```

Verify the installed version:

```bash
"$HOME/.local/share/hpc-agent/.venv/bin/python" -c "import importlib.metadata as m; print(m.version('hpc-agent'))"
```

Expected output:

```text
0.2.5
```

Verify MCP startup locally:

```bash
hpc-agent-mcp --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp
```

In another terminal:

```bash
curl http://127.0.0.1:8000/health
```

Expected health response includes:

```json
{"ok": true, "service": "hpc-agent-mcp", "transport": "streamable-http", "mcp_path": "/mcp"}
```

## MCP Safety Defaults

The following actions are blocked by default:

```text
hpc_submit_prepared_job
vasp_sync_output
vasp_sync_output_structured
hpc_execute_cleanup
```

Enable submit/sync only for controlled tests:

```bash
export HPC_AGENT_MCP_ENABLE_WRITE=1
```

Enable destructive cleanup only for controlled tests:

```bash
export HPC_AGENT_MCP_ENABLE_DESTRUCTIVE=1
```

Even when enabled, clients must still pass `confirm=true`.

## Release Files

Publish these files under the `0.2.5/` release directory:

```text
install.sh
hpc_agent-0.2.5-py3-none-any.whl
hpc_agent-0.2.5.tar.gz
RELEASE_NOTES.md
SHA256SUMS
```

Update stable/latest metadata:

```text
latest.txt
latest.json
stable/install.sh
stable/hpc_agent-0.2.5-py3-none-any.whl
```

## Notes

- MCP is a general external-client interface. ChatGPT Web is only one client-specific guide.
- HPC Agent does not generate real VASP `POTCAR` files. Users must provide authorized `POTCAR` files themselves.
- WARN items from `hpc-agent-check` about `.env`, SSH keys, local paths, remote HPC paths, or VASP commands usually mean the user still needs to finish environment configuration.

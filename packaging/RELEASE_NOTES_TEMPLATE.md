# HPC Agent VERSION

Release date: YYYY-MM-DD

## Summary

- One sentence summary of the release.

## Added

- List new user-visible features.

## Changed

- List behavior changes, packaging changes, or command changes.

## Fixed

- List bug fixes.

## Compatibility

- Required Python: 3.12+
- Install command: `hpc-agent`
- Check command: `hpc-agent-check`
- Init command: `hpc-agent-init`

## Upgrade

Download the release install script and run it with the release wheel:

```bash
curl -fsSL https://your-private-server/hpc-agent/releases/VERSION/install.sh -o /tmp/hpc-agent-install.sh

HPC_AGENT_WHEEL=https://your-private-server/hpc-agent/releases/VERSION/hpc_agent-VERSION-py3-none-any.whl \
sh /tmp/hpc-agent-install.sh
```

If the wheel version did not change but the published artifact must be overwritten locally:

```bash
HPC_AGENT_WHEEL=https://your-private-server/hpc-agent/releases/VERSION/hpc_agent-VERSION-py3-none-any.whl \
HPC_AGENT_FORCE_REINSTALL=1 \
sh /tmp/hpc-agent-install.sh
```

## Verification

After installation, run:

```bash
hpc-agent-check
```

Expected result:

- Package resources are present.
- `hpc-agent` entrypoint can be imported.
- Skills can be loaded.
- RAG documents can be loaded.

WARN items about `.env`, SSH keys, local paths, or remote HPC paths mean the user still needs to finish local configuration.

## Rollback

To roll back, install the previous wheel explicitly:

```bash
HPC_AGENT_WHEEL=https://your-private-server/hpc-agent/releases/PREVIOUS_VERSION/hpc_agent-PREVIOUS_VERSION-py3-none-any.whl \
HPC_AGENT_FORCE_REINSTALL=1 \
sh /tmp/hpc-agent-install.sh
```

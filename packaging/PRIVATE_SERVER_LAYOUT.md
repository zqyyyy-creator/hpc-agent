# HPC Agent Private Server Release Layout

This document describes the recommended files to publish on the private server.

## Minimal Layout

For the simplest working release, publish only:

```text
hpc-agent/
├── install.sh
└── hpc_agent-<version>-py3-none-any.whl
```

Users install with:

```bash
curl -fsSL https://your-private-server/hpc-agent/install.sh -o /tmp/hpc-agent-install.sh
sh /tmp/hpc-agent-install.sh
```

The installer downloads `latest.json`, reads `files.wheel.path`, then downloads the matching wheel automatically. For public repositories, users do not need a username, password, token, or `-u` curl option.

## Recommended Layout

For stable release management, publish versioned releases:

```text
hpc-agent/
├── install.sh
├── latest.txt
├── latest.json
├── SHA256SUMS
├── releases/
│   └── <version>/
│       ├── install.sh
│       ├── hpc_agent-<version>-py3-none-any.whl
│       ├── hpc_agent-<version>.tar.gz
│       ├── SHA256SUMS
│       └── RELEASE_NOTES.md
└── stable/
    ├── install.sh
    └── hpc_agent-<version>-py3-none-any.whl
```

## File Purpose

- `install.sh`: The one-file installer users download and run.
- `latest.txt`: The latest stable version, for example `0.2.5`.
- `latest.json`: Machine-readable metadata for the latest release. The installer reads `files.wheel.path` from this file.
- `SHA256SUMS`: Checksums for top-level convenience files.
- `releases/<version>/`: Immutable files for one exact version.
- `releases/<version>/install.sh`: Installer snapshot for that version.
- `releases/<version>/hpc_agent-<version>-py3-none-any.whl`: The main install artifact.
- `releases/<version>/hpc_agent-<version>.tar.gz`: Source distribution for audit and fallback.
- `releases/<version>/RELEASE_NOTES.md`: Human-readable release notes.
- `stable/`: Convenience alias for the currently recommended stable release.
- `stable/install.sh`: Installer that reads `stable/latest.json` to find the current stable wheel.

## Release Steps

1. Update the project version in `pyproject.toml`.
2. Run the full source check:

```bash
.venv/bin/python tests/run_all_checks.py
```

3. Build release artifacts:

```bash
uv build --cache-dir /tmp/uv-cache
```

4. Confirm these files exist:

```text
dist/hpc_agent-<version>-py3-none-any.whl
dist/hpc_agent-<version>.tar.gz
```

5. Create release notes from `packaging/RELEASE_NOTES_TEMPLATE.md`.
6. Generate checksums:

```bash
sha256sum \
  scripts/install.sh \
  dist/hpc_agent-<version>-py3-none-any.whl \
  dist/hpc_agent-<version>.tar.gz \
  RELEASE_NOTES.md
```

7. Create `latest.json` from `packaging/latest.example.json`.
8. Upload files to:

```text
hpc-agent/releases/<version>/
```

9. Update these convenience files:

```text
hpc-agent/install.sh
hpc-agent/latest.txt
hpc-agent/latest.json
hpc-agent/SHA256SUMS
hpc-agent/stable/install.sh
hpc-agent/stable/hpc_agent-<version>-py3-none-any.whl
```

10. Test from the private server URL:

```bash
curl -fsSL https://your-private-server/hpc-agent/install.sh -o /tmp/hpc-agent-install.sh
sh /tmp/hpc-agent-install.sh
```

11. Verify the installed package:

```bash
hpc-agent-check
```

## User-Facing Install Flow

Tell users to run:

```bash
python3 --version
curl -fsSL https://your-private-server/hpc-agent/install.sh -o /tmp/hpc-agent-install.sh
sh /tmp/hpc-agent-install.sh
hpc-agent-check
hpc-agent
```

If `~/.local/bin` is not in `PATH`, users should run:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Rollback

Rollback is installing an older wheel explicitly:

```bash
HPC_AGENT_WHEEL=https://your-private-server/hpc-agent/releases/<old-version>/hpc_agent-<old-version>-py3-none-any.whl \
HPC_AGENT_FORCE_REINSTALL=1 \
sh /tmp/hpc-agent-install.sh
```

The user's configuration file is not overwritten by default.

## Notes

- Do not ask normal users to clone the source repository.
- Keep old `releases/<version>/` directories immutable.
- Prefer increasing the version for every published wheel.
- Use `HPC_AGENT_FORCE_REINSTALL=1` only when a same-version artifact must be replaced.

# Changelog

## 0.2.0 - 2026-06-18

### Added
- Added Textual TUI as the unified interactive entry point.
- Added ordinary Slurm job generation, preview, confirmed submit, query, monitor, diagnosis, and cleanup workflows.
- Added local job registry support for recent jobs, job details, VASP job listing, archive preview, archive confirmation, and archive restore.
- Added VASP fixed-directory submit workflow with local input, remote input, remote output, output sync, and one-shot analysis.
- Added VASP report generation through Claude Code with `report.md`, `paper_methods.md`, and `paper_results.md`.
- Added deterministic VASP output parsing and `report_context.md` generation from synced outputs.
- Added VASP input generation from an existing authorized `POTCAR`, including `INCAR`, `KPOINTS`, and `POSCAR`.
- Added VASP input parameter overrides for calculation type, `ENCUT`, `KPOINTS`, `NSW`, `EDIFF`, `ISMEAR`, and `SIGMA`.
- Added overwrite confirmation for existing VASP input files.
- Added repeated VASP run handling with overwrite old results, automatic new run name, or cancel options.
- Added config diagnostics and recovery suggestions for `.env`, SSH keys, local and remote directories, VASP commands, partitions, and Claude Code/API settings.
- Added unified error diagnosis with real error cases first and generic error patterns as fallback.
- Added semi-automatic real error case drafting and confirmed writes to `data/errors/real_cases.json`.
- Added `/help`, `/help job`, and `/help vasp` shortcut help entries.
- Added selectable TUI chat text and `Ctrl+Y` copy behavior for selected text or the latest Agent reply.

### Changed
- Updated user documentation and docs entry points for the current Slurm, VASP, TUI, config, and error-diagnosis workflows.
- Reworked the error knowledge base into `real_cases.json` and `generic_errors.json`.
- Hardened VASP overwrite behavior so old remote input/output and local output directories are cleared before resubmission when the user chooses overwrite.
- Improved local job lifecycle behavior, including recent job ordering and job detail presentation.
- Expanded `.gitignore` coverage for local secrets, generated job records, VASP licensed inputs, and large VASP output artifacts.

### Fixed
- Fixed VASP submit selection so an explicitly requested job name is not replaced by the most recent complete VASP directory.
- Fixed "analyze the previous job" handling so the Agent can resolve the latest relevant job record.
- Fixed recent job listing so Slurm test jobs are not hidden behind newer VASP output directory mtimes.
- Fixed VASP input overwrite confirmation so replies such as `确认覆盖` and `覆盖已有配置文件` execute the pending overwrite instead of asking again.
- Fixed remote VASP cleanup behavior and documentation so input/output cleanup semantics are explicit.

### Notes
- HPC Agent does not generate real VASP `POTCAR` files. Users must provide `POTCAR` files from a VASP pseudopotential source they are authorized to use.
- This release is intended as a source-based milestone release. Clone the repository, configure `.env`, run `uv sync`, and start with `.venv/bin/python app.py`.

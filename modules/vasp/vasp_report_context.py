import json
import re
from pathlib import Path


MAX_TEXT_CHARS = 12000
LOG_SNIPPET_CHARS = 4000
REPORT_CONTEXT_NAME = "report_context.md"


def _read_text_limited(path: Path, max_chars: int = MAX_TEXT_CHARS) -> str:
    if not path.is_file():
        return ""

    with path.open("r", encoding="utf-8", errors="replace") as file:
        return file.read(max_chars)


def _read_tail_limited(path: Path, max_chars: int = LOG_SNIPPET_CHARS) -> str:
    if not path.is_file():
        return ""

    size = path.stat().st_size

    with path.open("rb") as file:
        if size > max_chars:
            file.seek(max(0, size - max_chars))
        data = file.read(max_chars)

    return data.decode("utf-8", errors="replace")


def _load_manifest(analysis_dir: Path) -> dict:
    manifest_path = analysis_dir / "file_manifest.json"

    if not manifest_path.is_file():
        return {}

    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _file_inventory(raw_output_dir: Path) -> list[dict]:
    if not raw_output_dir.is_dir():
        return []

    files = []

    for path in sorted(raw_output_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue

        files.append({
            "name": path.name,
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "empty": path.stat().st_size == 0,
        })

    return files


def _parse_incar(raw_output_dir: Path) -> dict:
    text = _read_text_limited(raw_output_dir / "INCAR")
    params = {}

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].split("!", 1)[0].strip()

        if not line or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip().upper()
        value = value.strip()

        if key:
            params[key] = value

    return params


def _parse_kpoints(raw_output_dir: Path) -> dict:
    lines = [
        line.strip()
        for line in _read_text_limited(raw_output_dir / "KPOINTS").splitlines()
        if line.strip()
    ]
    summary = {
        "mode": "unknown",
        "mesh": None,
        "shift": None,
    }

    if len(lines) >= 4:
        summary["mode"] = lines[2]
        mesh_values = lines[3].split()

        if len(mesh_values) >= 3:
            summary["mesh"] = mesh_values[:3]

    if len(lines) >= 5:
        shift_values = lines[4].split()

        if len(shift_values) >= 3:
            summary["shift"] = shift_values[:3]

    return summary


def _parse_poscar(raw_output_dir: Path) -> dict:
    lines = [
        line.strip()
        for line in _read_text_limited(raw_output_dir / "POSCAR").splitlines()
        if line.strip()
    ]
    summary = {
        "title": lines[0] if lines else "unknown",
        "species": [],
        "counts": [],
        "num_atoms": None,
    }

    if len(lines) >= 7:
        species_line = lines[5].split()
        count_line = lines[6].split()

        if all(re.fullmatch(r"\d+", item) for item in count_line):
            summary["species"] = species_line
            summary["counts"] = [int(item) for item in count_line]
            summary["num_atoms"] = sum(summary["counts"])

    return summary


def _collect_log_snippets(raw_output_dir: Path) -> dict:
    snippets = {}

    for path in sorted(raw_output_dir.glob("*.err")) + sorted(raw_output_dir.glob("*.out")):
        text = _read_tail_limited(path)

        if text:
            snippets[path.name] = text

    vasp_out = _read_tail_limited(raw_output_dir / "vasp.out")

    if vasp_out:
        snippets["vasp.out"] = vasp_out

    return snippets


def _diagnose(raw_output_dir: Path, inventory: list[dict], snippets: dict) -> list[str]:
    issues = []
    sizes = {item["name"]: item["size_bytes"] for item in inventory}

    for name in ["OSZICAR", "CONTCAR", "XDATCAR"]:
        if sizes.get(name) == 0:
            issues.append(f"{name} is empty.")

    if 0 < sizes.get("OUTCAR", 0) < 4096:
        issues.append("OUTCAR is very small; the VASP run likely stopped before producing meaningful results.")

    if 0 < sizes.get("vasprun.xml", 0) < 4096:
        issues.append("vasprun.xml is very small; XML output is likely incomplete.")

    combined_logs = "\n".join(snippets.values()).lower()

    if "potcar" in combined_logs and "input conversion error" in combined_logs:
        issues.append("stderr reports a POTCAR input conversion error.")

    if "forrtl: severe" in combined_logs:
        issues.append("stderr contains Intel Fortran severe runtime errors.")

    if not (raw_output_dir / "POTCAR").exists():
        issues.append("POTCAR was not synchronized into raw_output; this is intentional for analysis safety.")

    if not issues:
        issues.append("No obvious failure signature was detected from the lightweight checks.")

    return issues


def _format_kv_table(items: dict) -> str:
    if not items:
        return "- unknown"

    return "\n".join(f"- {key}: {value}" for key, value in sorted(items.items()))


def _format_inventory(inventory: list[dict]) -> str:
    if not inventory:
        return "- No files found."

    return "\n".join(
        f"- {item['name']}: {item['size_bytes']} bytes"
        for item in inventory
    )


def _format_snippets(snippets: dict) -> str:
    if not snippets:
        return "No log snippets available."

    blocks = []

    for name, text in snippets.items():
        blocks.append(f"### {name}\n\n```text\n{text.strip()}\n```")

    return "\n\n".join(blocks)


def _generate_figures(job_dir: Path) -> dict:
    try:
        from modules.vasp.vasp_figures import generate_vasp_figures

        return generate_vasp_figures(job_dir)
    except Exception as error:
        return {
            "success": False,
            "error": f"{type(error).__name__}: {error}",
            "figures": [],
            "data_files": [],
        }


def _format_figure_manifest(figures_result: dict) -> str:
    if not figures_result.get("success"):
        return (
            "- Figure generation failed.\n"
            f"- Error: {figures_result.get('error', 'unknown')}\n"
            "- Source policy: figures must be regenerated from raw_output before use."
        )

    figures = figures_result.get("figures") or []
    data_files = figures_result.get("data_files") or []
    if not figures and not data_files:
        return (
            "- No figure-ready numerical series were parsed from raw_output.\n"
            "- Source policy: no report_context or LLM-derived numbers were used."
        )

    lines = [
        f"- Manifest: {figures_result.get('manifest_path', 'unknown')}",
        f"- Figures directory: {figures_result.get('figures_dir', 'unknown')}",
        f"- Data directory: {figures_result.get('data_dir', 'unknown')}",
        f"- Source policy: {figures_result.get('source_policy')}",
        "",
        "Generated figures:",
    ]

    for figure in figures:
        sources = ", ".join(figure.get("source_files") or [])
        lines.append(
            f"- {figure['description']}: {figure.get('svg_path', figure.get('path'))} "
            f"(data: {figure['data_path']}; source: raw_output/{sources}; "
            f"rows: {figure['rows']}; series: {figure.get('series_kind', 'unknown')})"
        )

    lines.append("")
    lines.append("Generated data files:")
    for data_file in data_files:
        sources = ", ".join(data_file.get("source_files") or [])
        lines.append(
            f"- {data_file['name']}: {data_file['path']} "
            f"(source: raw_output/{sources}; rows: {data_file['rows']})"
        )

    return "\n".join(lines)


def generate_vasp_report_context(local_job_dir: str | Path) -> dict:
    job_dir = Path(local_job_dir).expanduser().resolve()
    raw_output_dir = job_dir / "raw_output"
    analysis_dir = job_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    manifest = _load_manifest(analysis_dir)
    inventory = _file_inventory(raw_output_dir)
    incar = _parse_incar(raw_output_dir)
    kpoints = _parse_kpoints(raw_output_dir)
    poscar = _parse_poscar(raw_output_dir)
    snippets = _collect_log_snippets(raw_output_dir)
    issues = _diagnose(raw_output_dir, inventory, snippets)
    figures_result = _generate_figures(job_dir)

    # Parse deterministic facts from OUTCAR/OSZICAR.
    facts_block = ""
    try:
        from modules.vasp.vasp_outcar_parser import parse_vasp_results, format_facts_block

        vasp_facts = parse_vasp_results(raw_output_dir)
        facts_block = format_facts_block(vasp_facts)
    except Exception:
        facts_block = ""

    report_context_path = analysis_dir / REPORT_CONTEXT_NAME

    facts_section = ""
    if facts_block:
        facts_section = f"""

{facts_block}

"""

    context = f"""# VASP Report Context

## Job Directories

- Local job directory: {job_dir}
- Raw output directory: {raw_output_dir}
- Analysis directory: {analysis_dir}
- File manifest: {analysis_dir / "file_manifest.json"}
{facts_section}
## File Inventory

{_format_inventory(inventory)}

## Sync Manifest Summary

- Manifest present: {"yes" if manifest else "no"}
- Manifest raw_output_dir: {manifest.get("raw_output_dir", "unknown")}
- Manifest file count: {len(manifest.get("files", [])) if manifest else 0}

## INCAR Parameters

{_format_kv_table(incar)}

## KPOINTS Summary

- Mode: {kpoints.get("mode")}
- Mesh: {kpoints.get("mesh")}
- Shift: {kpoints.get("shift")}

## POSCAR Summary

- Title: {poscar.get("title")}
- Species: {poscar.get("species")}
- Counts: {poscar.get("counts")}
- Number of atoms: {poscar.get("num_atoms")}

## Lightweight Diagnosis

{chr(10).join(f"- {issue}" for issue in issues)}

## Raw-Output Figures And Plot Data

{_format_figure_manifest(figures_result)}

## Log Snippets

{_format_snippets(snippets)}

## Instructions For Claude Code

- The "VASP Deterministic Facts" section above is the **single authoritative source** for all numerical results (energies, forces, stresses, convergence status, timing, etc.).
- Any figures listed in "Raw-Output Figures And Plot Data" are generated from synchronized files under raw_output/ only. Use their CSV files and SVG paths as plot references; do not recreate or alter figure data from narrative text.
- **Never** extract numerical values from the Log Snippets section — those snippets are included only for diagnostic context (e.g., checking warnings, error messages).
- If the Deterministic Facts section says the calculation converged, report it as converged. If not, generate a failure/diagnostic report.
- Do not invent scientific results (energies, forces, band gaps, magnetic moments, exchange-correlation functional, pseudopotential type) that are not in the Deterministic Facts.
- Use "unknown" for unsupported method details.
- If the calculation failed or appears incomplete, generate a failure/diagnostic report rather than a scientific result report.
- If the context says POTCAR was not synchronized into raw_output, treat that only as "not available for local inspection"; do not claim the remote POTCAR was missing.
- Put Claude Code outputs under the analysis directory:
  - report.md
  - paper_methods.md
  - paper_results.md
"""

    report_context_path.write_text(context, encoding="utf-8")

    return {
        "success": True,
        "local_job_dir": str(job_dir),
        "raw_output_dir": str(raw_output_dir),
        "analysis_dir": str(analysis_dir),
        "report_context_path": str(report_context_path),
        "issues": issues,
        "file_count": len(inventory),
        "figures_manifest_path": figures_result.get("manifest_path"),
        "figure_count": len(figures_result.get("figures") or []),
        "data_file_count": len(figures_result.get("data_files") or []),
        "figures_error": figures_result.get("error"),
    }

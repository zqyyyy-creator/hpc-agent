import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path

from dotenv import load_dotenv

from modules.vasp.vasp_report_context import generate_vasp_report_context


load_dotenv(Path(__file__).resolve().parents[2] / ".env")

REPORT_FILES = {
    "report_md": "report.md",
    "paper_methods_md": "paper_methods.md",
    "paper_results_md": "paper_results.md",
}
DEFAULT_TIMEOUT_SECONDS = 1800
PROJECT_ROOT = Path(__file__).resolve().parents[2]
VASP_REPORT_SKILL_PATH = PROJECT_ROOT / "skills" / "vasp_report" / "SKILL.md"


def _load_vasp_report_skill() -> str:
    if not VASP_REPORT_SKILL_PATH.is_file():
        return ""

    return VASP_REPORT_SKILL_PATH.read_text(encoding="utf-8", errors="replace").strip()


def _build_prompt(report_context: str) -> str:
    skill_instructions = _load_vasp_report_skill()
    skill_section = ""

    if skill_instructions:
        skill_section = f"""Follow these vasp-report skill instructions:

```markdown
{skill_instructions}
```

"""

    return f"""You are generating a publication-oriented VASP analysis report.

{skill_section}
The report context below contains a **"VASP Deterministic Facts"** section — this is
the single authoritative source for all numerical results. It is produced by a
deterministic parser, not by an LLM reading free-text logs.

STRICT RULES:
1. Use ONLY the "VASP Deterministic Facts" section for energies, forces, stresses,
   convergence status, timing, and other numerical values.
2. The "Log Snippets" section is included ONLY for diagnostic context (warnings,
   error messages) — never extract numerical values from it.
3. Do not invent energies, forces, band gaps, magnetic moments, convergence
   status, or publication claims not in the Deterministic Facts.
4. If the Deterministic Facts say the calculation converged, report it as converged.
   If they say it did not converge, generate a failure/diagnostic report.
5. Do not infer the exchange-correlation functional, pseudopotential type,
   PAW/LDA/PBE details, or POTCAR contents unless explicitly present in the context.
   Use "unknown" for unsupported method details.
6. If the context says POTCAR was not synchronized into raw_output, treat that
   only as "not available for local inspection"; do not claim the remote POTCAR
   was missing.
7. If logs show a POTCAR input conversion error, say the remote POTCAR was
   present but unreadable, invalid, placeholder, corrupted, or incompatible
   unless more detail is known.
8. If the context lists raw-output figures or CSV plot data, you may reference
   those paths in the report. Treat them as generated from raw_output only; do
   not invent, modify, smooth, extrapolate, or recreate plotted values from
   narrative text.
9. Do not write files, use tools, or ask for write permission. Return only the
   JSON object; the Python caller writes report.md, paper_methods.md, and
   paper_results.md under analysis/.

Return only one valid JSON object. Do not wrap it in Markdown fences.
The JSON object must have exactly these string keys:
- "report_md": Chinese user-facing report.
- "paper_methods_md": English manuscript methods note. If the calculation failed,
  state that the run did not complete and the method text is not suitable as a
  final manuscript methods paragraph. For failed or incomplete calculations, keep
  this note conservative: mention only confirmed input tags/values from the
  context, and do not mention DFT, PAW, exchange-correlation functional,
  pseudopotential type, or POTCAR-derived method details unless explicitly present.
  Do not interpret VASP tag meanings beyond the literal tag/value pairs in the
  context; for example, do not name the smearing method for ISMEAR unless the
  context explicitly names it.
- "paper_results_md": English manuscript results note. If no reliable results are
  available, explicitly say no scientifically valid results were obtained.

VASP report context:

```markdown
{report_context}
```
"""


def _extract_json_object(text: str) -> dict:
    stripped = text.strip()

    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("Claude Code did not return a JSON object.")

    return json.loads(stripped[start:end + 1])


def _validate_report_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Claude Code report payload is not a JSON object.")

    validated = {}

    for key in REPORT_FILES:
        value = payload.get(key)

        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Claude Code report payload missing non-empty {key!r}.")

        validated[key] = value.strip() + "\n"

    return validated


def _write_report_files(analysis_dir: Path, payload: dict) -> dict:
    paths = {}

    for key, file_name in REPORT_FILES.items():
        path = analysis_dir / file_name
        path.write_text(payload[key], encoding="utf-8")
        paths[key.replace("_md", "_path")] = str(path)

    return paths


def _resolve_claude_command(claude_cmd: str | None) -> list[str]:
    command_text = claude_cmd or os.getenv("HPC_CLAUDE_CODE_COMMAND") or "claude"
    return shlex.split(command_text)


def _resolve_timeout(timeout_seconds: int | None) -> int:
    if timeout_seconds is not None:
        return int(timeout_seconds)

    configured = os.getenv("HPC_CLAUDE_CODE_TIMEOUT_SECONDS")

    if configured:
        try:
            return int(configured)
        except ValueError:
            return DEFAULT_TIMEOUT_SECONDS

    return DEFAULT_TIMEOUT_SECONDS


def _build_claude_env() -> dict:
    env = os.environ.copy()

    if not env.get("ANTHROPIC_BASE_URL") and env.get("PARATERA_BASE_URL"):
        env["ANTHROPIC_BASE_URL"] = env["PARATERA_BASE_URL"]

    paratera_key = env.get("PARATERA_API_KEY")

    if paratera_key:
        env["ANTHROPIC_AUTH_TOKEN"] = paratera_key
        env["ANTHROPIC_API_KEY"] = paratera_key
    elif env.get("ANTHROPIC_API_KEY") and not env.get("ANTHROPIC_AUTH_TOKEN"):
        env["ANTHROPIC_AUTH_TOKEN"] = env["ANTHROPIC_API_KEY"]

    model = (
        env.get("HPC_CLAUDE_CODE_MODEL")
        or env.get("ANTHROPIC_MODEL")
        or env.get("PARATERA_MODEL")
    )

    if not model and "paratera" in env.get("ANTHROPIC_BASE_URL", ""):
        model = "DeepSeek-V4-Pro"

    if model:
        env["ANTHROPIC_MODEL"] = model
        env.setdefault("ANTHROPIC_DEFAULT_SONNET_MODEL", model)
        env.setdefault("ANTHROPIC_DEFAULT_OPUS_MODEL", model)
        env.setdefault("ANTHROPIC_DEFAULT_HAIKU_MODEL", model)

    env.setdefault("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")
    env.setdefault("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", "1")

    return env


def generate_report_with_claude(
    local_job_dir: str | Path,
    timeout_seconds: int | None = None,
    claude_cmd: str | None = None,
    runner=None,
) -> dict:
    job_dir = Path(local_job_dir).expanduser().resolve()
    analysis_dir = job_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    report_context_path = analysis_dir / "report_context.md"

    context_result = generate_vasp_report_context(job_dir)
    report_context_path = Path(context_result["report_context_path"])

    report_context = report_context_path.read_text(encoding="utf-8", errors="replace")
    prompt = _build_prompt(report_context)
    command = _resolve_claude_command(claude_cmd) + [
        "--bare",
        "-p",
        "--output-format",
        "text",
        prompt,
    ]
    run = runner or subprocess.run
    timeout_seconds = _resolve_timeout(timeout_seconds)
    started_at = time.monotonic()

    try:
        completed = run(
            command,
            cwd=str(job_dir),
            text=True,
            capture_output=True,
            env=_build_claude_env(),
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as error:
        return {
            "success": False,
            "local_job_dir": str(job_dir),
            "analysis_dir": str(analysis_dir),
            "report_context_path": str(report_context_path),
            "error": f"Claude Code command not found: {error}",
        }
    except subprocess.TimeoutExpired as error:
        elapsed_seconds = time.monotonic() - started_at
        return {
            "success": False,
            "local_job_dir": str(job_dir),
            "analysis_dir": str(analysis_dir),
            "report_context_path": str(report_context_path),
            "elapsed_seconds": round(elapsed_seconds, 2),
            "timeout_seconds": timeout_seconds,
            "error": (
                f"Claude Code timed out after {timeout_seconds} seconds. "
                "The VASP report context remains available; retry later or increase "
                "HPC_CLAUDE_CODE_TIMEOUT_SECONDS in .env if the model gateway is slow. "
                f"Details: {error}"
            ),
        }

    elapsed_seconds = time.monotonic() - started_at
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""

    if completed.returncode != 0:
        return {
            "success": False,
            "local_job_dir": str(job_dir),
            "analysis_dir": str(analysis_dir),
            "report_context_path": str(report_context_path),
            "stdout": stdout,
            "stderr": stderr,
            "elapsed_seconds": round(elapsed_seconds, 2),
            "timeout_seconds": timeout_seconds,
            "error": f"Claude Code exited with status {completed.returncode}.",
        }

    try:
        payload = _validate_report_payload(_extract_json_object(stdout))
    except (json.JSONDecodeError, ValueError) as error:
        raw_path = analysis_dir / "claude_report_raw_output.txt"
        raw_path.write_text(stdout, encoding="utf-8")

        return {
            "success": False,
            "local_job_dir": str(job_dir),
            "analysis_dir": str(analysis_dir),
            "report_context_path": str(report_context_path),
            "raw_output_path": str(raw_path),
            "stderr": stderr,
            "elapsed_seconds": round(elapsed_seconds, 2),
            "timeout_seconds": timeout_seconds,
            "error": f"Could not parse Claude Code report JSON: {error}",
        }

    report_paths = _write_report_files(analysis_dir, payload)
    pdf_result = None
    pdf_error = None

    try:
        from modules.vasp.vasp_pdf_reporter import generate_vasp_pdf_report

        pdf_result = generate_vasp_pdf_report(job_dir)
    except Exception as error:
        pdf_error = f"{type(error).__name__}: {error}"

    result = {
        "success": True,
        "local_job_dir": str(job_dir),
        "analysis_dir": str(analysis_dir),
        "report_context_path": str(report_context_path),
        "figures_manifest_path": context_result.get("figures_manifest_path"),
        "figure_count": context_result.get("figure_count", 0),
        "data_file_count": context_result.get("data_file_count", 0),
        "figures_error": context_result.get("figures_error"),
        **report_paths,
        "stderr": stderr,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "timeout_seconds": timeout_seconds,
    }

    if pdf_result and pdf_result.get("success"):
        result["pdf_report_path"] = pdf_result.get("pdf_report_path")
    if pdf_error:
        result["pdf_error"] = pdf_error

    return result

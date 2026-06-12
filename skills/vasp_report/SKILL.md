---
name: vasp-report
description: Generate publication-oriented VASP reports from analysis/report_context.md, including user diagnostics and manuscript-safe methods/results notes without reading large raw output files.
---

# VASP Report Skill

Use this skill when generating VASP analysis reports from `analysis/report_context.md`.

## Inputs

Read only the provided report context unless the caller explicitly supplies other compact summaries.

Primary input:

```text
analysis/report_context.md
```

Do not read large raw files directly:

```text
raw_output/OUTCAR
raw_output/vasprun.xml
raw_output/WAVECAR
raw_output/CHGCAR
raw_output/AECCAR*
```

`POTCAR` may be absent from local synchronized output by design. Treat that as "not available for local inspection", not as proof that the remote file was missing.

## Required Outputs

Generate exactly three Markdown payloads:

```text
report.md
paper_methods.md
paper_results.md
```

The calling agent writes these files under `analysis/`.

## Authoritative Data Source

The "VASP Deterministic Facts" section in `report_context.md` is the **single
authoritative source** for numerical values (energies, forces, convergence
status, timing, etc.). It is produced by a deterministic parser, not an LLM.

NEVER extract numerical results from log snippets — those are included only
for diagnostic context (warnings, error messages).

## Report Rules

- Use only facts present in the "VASP Deterministic Facts" section for all
  numerical values.
- Use INCAR/POSCAR/KPOINTS sections for input parameters.
- Use the Log Snippets only for diagnostic context (warnings, errors).
- Do not invent total energy, forces, band gap, magnetic moments, convergence
  status, exchange-correlation functional, pseudopotential type, or POTCAR contents.
- Use `unknown` for unsupported method details.
- If the Deterministic Facts say the calculation converged, report it as converged.
- If the calculation failed or appears incomplete, generate a failure/diagnostic
  report, not a scientific result report.
- If logs show a POTCAR input conversion error, say the remote POTCAR was present
  but unreadable, invalid, placeholder, corrupted, or incompatible unless the
  context proves something more specific.
- Do not claim the remote POTCAR was missing merely because it was not
  synchronized locally.
- For failed/incomplete calculations, keep `paper_methods.md` conservative: list
  only confirmed input tag/value pairs and state that the text is not suitable as
  a final manuscript methods paragraph.
- For failed/incomplete calculations, `paper_results.md` must explicitly state
  that no scientifically valid results were obtained.
- Do not interpret VASP tag meanings beyond literal tag/value pairs unless the
  context explicitly provides the interpretation.

## Output Contract

When used through `ClaudeCodeReporter`, return only one valid JSON object:

```json
{
  "report_md": "...",
  "paper_methods_md": "...",
  "paper_results_md": "..."
}
```

Do not wrap the JSON in Markdown fences.

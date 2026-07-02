"""Generate VASP analysis figures from synchronized raw output files.

This module intentionally reads only ``raw_output/`` files.  The LLM-facing
report context may reference the generated figures, but the numerical data
behind every figure is parsed directly from VASP output files.
"""

from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any


FIGURES_DIR_NAME = "figures"
DATA_DIR_NAME = "data"
MANIFEST_NAME = "figures_manifest.json"


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _to_float(value: str) -> float:
    return float(value.replace("D", "E").replace("d", "E"))


def parse_oszicar_series(raw_output_dir: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Parse OSZICAR convergence series from raw output."""
    raw_dir = Path(raw_output_dir)
    text = _read_text(raw_dir / "OSZICAR")
    electronic: list[dict[str, Any]] = []
    ionic: list[dict[str, Any]] = []
    current_ionic_step = 1

    for line in text.splitlines():
        stripped = line.strip()

        electronic_match = re.match(
            r"^(DAV|RMM):\s+(\d+)\s+([+\-\d.EeDd]+)",
            stripped,
        )
        if electronic_match:
            electronic.append({
                "global_iteration": len(electronic) + 1,
                "ionic_step": current_ionic_step,
                "electronic_step": int(electronic_match.group(2)),
                "algorithm": electronic_match.group(1),
                "energy_eV": _to_float(electronic_match.group(3)),
            })
            continue

        ionic_match = re.match(
            r"^\s*(\d+)\s+F=\s*([+\-\d.EeDd]+)\s+E0=\s*([+\-\d.EeDd]+)\s+d\s*E\s*=\s*([+\-\d.EeDd]+)",
            line,
        )
        if ionic_match:
            step = int(ionic_match.group(1))
            ionic.append({
                "ionic_step": step,
                "free_energy_eV": _to_float(ionic_match.group(2)),
                "energy_sigma0_eV": _to_float(ionic_match.group(3)),
                "delta_energy_eV": _to_float(ionic_match.group(4)),
            })
            current_ionic_step = step + 1

    return {
        "electronic": electronic,
        "ionic": ionic,
    }


def parse_outcar_series(raw_output_dir: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Parse force, pressure, and volume series from OUTCAR in raw output."""
    raw_dir = Path(raw_output_dir)
    text = _read_text(raw_dir / "OUTCAR")
    if not text:
        return {"forces": [], "pressure": [], "volume": []}

    return {
        "forces": _parse_force_series(text),
        "pressure": _parse_pressure_series(text),
        "volume": _parse_volume_series(text),
    }


def _parse_force_series(outcar: str) -> list[dict[str, Any]]:
    marker = "POSITION                                       TOTAL-FORCE (eV/Angst)"
    blocks = outcar.split(marker)[1:]
    series: list[dict[str, Any]] = []

    for index, block in enumerate(blocks, 1):
        forces = []
        for line in block.splitlines():
            if "total drift" in line.lower():
                break
            parts = line.strip().split()
            if len(parts) < 6:
                continue
            try:
                values = [float(item) for item in parts[:6]]
            except ValueError:
                continue
            forces.append(values[3:6])

        if not forces:
            continue

        norms = [math.sqrt(fx * fx + fy * fy + fz * fz) for fx, fy, fz in forces]
        max_components = [max(abs(fx), abs(fy), abs(fz)) for fx, fy, fz in forces]
        series.append({
            "ionic_step": index,
            "num_ions": len(forces),
            "max_force_component_eV_A": max(max_components),
            "max_force_norm_eV_A": max(norms),
            "mean_force_norm_eV_A": sum(norms) / len(norms),
        })

    return series


def _parse_pressure_series(outcar: str) -> list[dict[str, Any]]:
    series = []
    for index, match in enumerate(
        re.finditer(r"external pressure\s*=\s*([+\-\d.EeDd]+)\s*kB", outcar),
        1,
    ):
        series.append({
            "ionic_step": index,
            "external_pressure_kB": _to_float(match.group(1)),
        })
    return series


def _parse_volume_series(outcar: str) -> list[dict[str, Any]]:
    series = []
    for index, match in enumerate(
        re.finditer(r"volume of cell\s*:\s*([+\-\d.EeDd]+)", outcar),
        1,
    ):
        series.append({
            "ionic_step": index,
            "volume_A3": _to_float(match.group(1)),
        })
    return series


def generate_vasp_figures(local_job_dir: str | Path) -> dict[str, Any]:
    """Generate CSV data and SVG figures under ``analysis/``.

    The local job directory is expected to contain ``raw_output/`` and
    ``analysis/``.  Existing figure files are overwritten deterministically.
    """
    job_dir = Path(local_job_dir).expanduser().resolve()
    raw_output_dir = job_dir / "raw_output"
    analysis_dir = job_dir / "analysis"
    figures_dir = analysis_dir / FIGURES_DIR_NAME
    data_dir = analysis_dir / DATA_DIR_NAME
    figures_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    oszicar = parse_oszicar_series(raw_output_dir)
    outcar = parse_outcar_series(raw_output_dir)
    datasets = {
        "ionic_energy": {
            "rows": oszicar["ionic"],
            "source_files": ["OSZICAR"],
            "x": "ionic_step",
            "y": "free_energy_eV",
            "title": "Ionic energy convergence",
            "x_label": "Ionic step",
            "y_label": "Free energy F (eV)",
            "csv": "ionic_energy.csv",
            "figure_base": "ionic_energy_convergence",
        },
        "electronic_energy": {
            "rows": oszicar["electronic"],
            "source_files": ["OSZICAR"],
            "x": "global_iteration",
            "y": "energy_eV",
            "title": "Electronic energy convergence",
            "x_label": "Electronic iteration",
            "y_label": "Energy (eV)",
            "csv": "electronic_energy.csv",
            "figure_base": "electronic_energy_convergence",
        },
        "max_force": {
            "rows": outcar["forces"],
            "source_files": ["OUTCAR"],
            "x": "ionic_step",
            "y": "max_force_norm_eV_A",
            "title": "Maximum force convergence",
            "x_label": "Ionic step",
            "y_label": "Max force norm (eV/A)",
            "csv": "max_force.csv",
            "figure_base": "max_force_convergence",
        },
        "pressure": {
            "rows": outcar["pressure"],
            "source_files": ["OUTCAR"],
            "x": "ionic_step",
            "y": "external_pressure_kB",
            "title": "External pressure convergence",
            "x_label": "Ionic step",
            "y_label": "External pressure (kB)",
            "csv": "pressure.csv",
            "figure_base": "pressure_convergence",
        },
        "volume": {
            "rows": outcar["volume"],
            "source_files": ["OUTCAR"],
            "x": "ionic_step",
            "y": "volume_A3",
            "title": "Cell volume convergence",
            "x_label": "Ionic step",
            "y_label": "Volume (A^3)",
            "csv": "volume.csv",
            "figure_base": "volume_convergence",
        },
    }

    figures = []
    data_files = []

    for name, spec in datasets.items():
        rows = spec["rows"]
        if not rows:
            continue

        csv_path = data_dir / spec["csv"]
        _write_csv(csv_path, rows)
        data_files.append({
            "name": name,
            "path": str(csv_path),
            "source_files": spec["source_files"],
            "rows": len(rows),
        })

        if len(rows) >= 1:
            figure_path = figures_dir / f"{spec['figure_base']}.svg"
            _write_line_chart_svg(
                figure_path,
                rows,
                x_key=spec["x"],
                y_key=spec["y"],
                title=spec["title"],
                x_label=spec["x_label"],
                y_label=spec["y_label"],
            )
            figures.append({
                "name": name,
                "path": str(figure_path),
                "svg_path": str(figure_path),
                "data_path": str(csv_path),
                "source_files": spec["source_files"],
                "x_key": spec["x"],
                "y_key": spec["y"],
                "x_label": spec["x_label"],
                "y_label": spec["y_label"],
                "title": spec["title"],
                "rows": len(rows),
                "series_kind": "single_point" if len(rows) == 1 else "convergence_series",
                "description": spec["title"],
            })

    manifest = {
        "success": True,
        "local_job_dir": str(job_dir),
        "raw_output_dir": str(raw_output_dir),
        "analysis_dir": str(analysis_dir),
        "figures_dir": str(figures_dir),
        "data_dir": str(data_dir),
        "source_policy": (
            "All plotted numerical values are parsed directly from files under raw_output/. "
            "Report context and LLM output are not used as data sources."
        ),
        "figures": figures,
        "data_files": data_files,
    }
    manifest_path = analysis_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_line_chart_svg(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    x_key: str,
    y_key: str,
    title: str,
    x_label: str,
    y_label: str,
) -> None:
    points = [
        (float(row[x_key]), float(row[y_key]))
        for row in rows
        if row.get(x_key) is not None and row.get(y_key) is not None
    ]
    svg = _line_chart_svg(points, title=title, x_label=x_label, y_label=y_label)
    path.write_text(svg, encoding="utf-8")


def _line_chart_svg(
    points: list[tuple[float, float]],
    *,
    title: str,
    x_label: str,
    y_label: str,
) -> str:
    width = 900
    height = 560
    left = 92
    right = 36
    top = 60
    bottom = 78
    plot_w = width - left - right
    plot_h = height - top - bottom
    xs = [point[0] for point in points] or [0.0]
    ys = [point[1] for point in points] or [0.0]
    x_min, x_max, y_min, y_max = _chart_bounds(xs, ys)

    def sx(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_w

    def sy(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_h

    path_points = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in points)
    circles = "\n".join(
        f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="4" fill="#1565c0" />'
        for x, y in points
    )
    x_ticks = _ticks(x_min, x_max)
    y_ticks = _ticks(y_min, y_max)
    grid = []
    labels = []

    for value in x_ticks:
        x = sx(value)
        grid.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_h}" class="grid" />')
        labels.append(f'<text x="{x:.2f}" y="{height - 45}" text-anchor="middle" class="tick">{_fmt(value)}</text>')

    for value in y_ticks:
        y = sy(value)
        grid.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" class="grid" />')
        labels.append(f'<text x="{left - 12}" y="{y + 4:.2f}" text-anchor="end" class="tick">{_fmt(value)}</text>')

    polyline = f'<polyline points="{path_points}" fill="none" stroke="#1565c0" stroke-width="3" />' if points else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{_escape(title)}">
<style>
  .title {{ font: 700 24px Arial, sans-serif; fill: #111; }}
  .axis {{ stroke: #222; stroke-width: 1.5; }}
  .grid {{ stroke: #d9d9d9; stroke-width: 1; }}
  .label {{ font: 16px Arial, sans-serif; fill: #222; }}
  .tick {{ font: 13px Arial, sans-serif; fill: #333; }}
</style>
<rect width="100%" height="100%" fill="#fff" />
<text x="{width / 2:.1f}" y="34" text-anchor="middle" class="title">{_escape(title)}</text>
{chr(10).join(grid)}
<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" class="axis" />
<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" class="axis" />
{polyline}
{circles}
{chr(10).join(labels)}
<text x="{left + plot_w / 2:.1f}" y="{height - 12}" text-anchor="middle" class="label">{_escape(x_label)}</text>
<text x="22" y="{top + plot_h / 2:.1f}" text-anchor="middle" class="label" transform="rotate(-90 22 {top + plot_h / 2:.1f})">{_escape(y_label)}</text>
</svg>
'''


def _chart_bounds(xs: list[float], ys: list[float]) -> tuple[float, float, float, float]:
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    if x_min == x_max:
        x_min -= 0.5
        x_max += 0.5
    if y_min == y_max:
        delta = abs(y_min) * 0.05 or 1.0
        y_min -= delta
        y_max += delta

    y_pad = (y_max - y_min) * 0.08
    y_min -= y_pad
    y_max += y_pad
    return x_min, x_max, y_min, y_max


def _ticks(min_value: float, max_value: float, count: int = 5) -> list[float]:
    if count <= 1:
        return [min_value]
    step = (max_value - min_value) / (count - 1)
    return [min_value + step * index for index in range(count)]


def _fmt(value: float) -> str:
    if value == 0:
        return "0"
    if abs(value) >= 1000 or abs(value) < 0.001:
        return f"{value:.2e}"
    if abs(value) >= 10:
        return f"{value:.2f}"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

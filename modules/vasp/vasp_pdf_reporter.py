from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, String

from modules.vasp.vasp_outcar_parser import parse_vasp_results


PDF_REPORT_NAME = "report.pdf"
PDF_FONT = "STSong-Light"


def generate_vasp_pdf_report(local_job_dir: str | Path) -> dict[str, Any]:
    """Generate a Chinese, beginner-friendly VASP PDF report.

    Numerical facts and plotted data are loaded from deterministic raw-output
    parsers and CSV files generated from ``raw_output/``. Existing Markdown
    reports are used as narrative input, not as numerical data sources.
    """
    job_dir = Path(local_job_dir).expanduser().resolve()
    analysis_dir = job_dir / "analysis"
    raw_output_dir = job_dir / "raw_output"
    pdf_path = analysis_dir / PDF_REPORT_NAME
    analysis_dir.mkdir(parents=True, exist_ok=True)

    pdfmetrics.registerFont(UnicodeCIDFont(PDF_FONT))
    styles = _build_styles()
    facts = parse_vasp_results(raw_output_dir)
    manifest = _load_json(analysis_dir / "figures_manifest.json")
    figures = manifest.get("figures") or []

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=1.7 * cm,
        leftMargin=1.7 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title="VASP 分析报告",
        author="HPC Agent",
    )

    story = []
    story.extend(_cover_section(job_dir, facts, styles))
    story.extend(_calculation_info_section(raw_output_dir, styles))
    story.extend(_convergence_section(facts, figures, styles))
    story.extend(_energy_electronic_section(facts, styles))
    story.extend(_mechanics_performance_section(facts, styles))
    story.extend(_figure_sections(figures, styles))
    story.append(PageBreak())
    story.extend(_data_source_section(raw_output_dir, analysis_dir, manifest, styles))
    story.append(PageBreak())
    story.extend(_markdown_section("详细用户报告", analysis_dir / "report.md", styles))
    story.extend(_markdown_section("论文方法备注", analysis_dir / "paper_methods.md", styles))
    story.extend(_markdown_section("论文结果备注", analysis_dir / "paper_results.md", styles))

    doc.build(story)
    return {
        "success": True,
        "pdf_report_path": str(pdf_path),
        "figure_count": len(figures),
        "raw_output_dir": str(raw_output_dir),
        "analysis_dir": str(analysis_dir),
    }


def _build_styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    normal = ParagraphStyle(
        "CNNormal",
        parent=sample["Normal"],
        fontName=PDF_FONT,
        fontSize=10.5,
        leading=16,
        spaceAfter=6,
    )
    return {
        "title": ParagraphStyle(
            "CNTitle",
            parent=normal,
            fontSize=24,
            leading=30,
            alignment=TA_LEFT,
            spaceAfter=18,
            textColor=colors.HexColor("#172033"),
        ),
        "subtitle": ParagraphStyle("CNSubtitle", parent=normal, fontSize=12, leading=16, textColor=colors.HexColor("#5b6475")),
        "h1": ParagraphStyle("CNH1", parent=normal, fontSize=16, leading=21, spaceBefore=18, spaceAfter=8, textColor=colors.HexColor("#172033")),
        "h2": ParagraphStyle("CNH2", parent=normal, fontSize=13, leading=18, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#172033")),
        "normal": normal,
        "small": ParagraphStyle("CNSmall", parent=normal, fontSize=8.5, leading=12, textColor=colors.HexColor("#555555")),
        "card_label": ParagraphStyle("CNCardLabel", parent=normal, fontSize=9.5, leading=12, textColor=colors.HexColor("#5b6475")),
        "card_value": ParagraphStyle("CNCardValue", parent=normal, fontSize=14, leading=18, textColor=colors.HexColor("#172033")),
        "code": ParagraphStyle(
            "CNCode",
            parent=normal,
            fontSize=8.5,
            leading=11,
            leftIndent=10,
            textColor=colors.HexColor("#333333"),
        ),
    }


def _cover_section(job_dir: Path, facts: dict, styles: dict[str, ParagraphStyle]) -> list:
    convergence = facts.get("convergence") or {}
    energy = facts.get("energy") or {}
    forces = facts.get("forces") or {}
    status = "Converged" if convergence.get("converged") else "Not confirmed"
    toten = _fmt_num(energy.get("toten"), 6) or "unknown"
    max_force = _fmt_num(forces.get("max_force_eV_A"), 6) or "unknown"

    return [
        Paragraph("VASP Analysis Report", styles["title"]),
        Paragraph(f"{_escape(job_dir.name)}  |  beginner-friendly scientific summary", styles["subtitle"]),
        HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1f78b4"), spaceBefore=6, spaceAfter=14),
        _status_card_table([
            ("Status", status, colors.HexColor("#e8f7ef"), colors.HexColor("#1b7f4a")),
            ("TOTEN", f"{toten} eV" if toten != "unknown" else "unknown", colors.HexColor("#eef5ff"), colors.HexColor("#1f5fae")),
            ("Max force", f"{max_force} eV/A" if max_force != "unknown" else "unknown", colors.HexColor("#fff7e8"), colors.HexColor("#9a6412")),
        ], styles),
        Spacer(1, 8),
    ]


def _status_card_table(cards: list[tuple[str, str, colors.Color, colors.Color]], styles: dict[str, ParagraphStyle]) -> Table:
    data = []
    row = []
    for label, value, _, value_color in cards:
        value_style = ParagraphStyle(f"CardValue{label}", parent=styles["card_value"], textColor=value_color)
        row.append([
            Paragraph(_escape(label), styles["card_label"]),
            Paragraph(_escape(value), value_style),
        ])
    data.append(row)
    table = Table(data, colWidths=[5.0 * cm, 5.0 * cm, 5.0 * cm], rowHeights=[1.65 * cm])
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0, colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]
    for index, (_, _, bg, _) in enumerate(cards):
        style.extend([
            ("BACKGROUND", (index, 0), (index, 0), bg),
            ("BOX", (index, 0), (index, 0), 0.4, colors.HexColor("#d7dce8")),
        ])
    table.setStyle(TableStyle(style))
    return table


def _data_source_section(
    raw_output_dir: Path,
    analysis_dir: Path,
    manifest: dict,
    styles: dict[str, ParagraphStyle],
) -> list:
    lines = [
        Paragraph("数据来源与可靠性声明", styles["h1"]),
        Paragraph(
            "PDF 中的数值和图表只来自 raw_output/ 原始输出的确定性解析，以及由这些原始输出生成的 CSV 图表数据。"
            "LLM 生成的 Markdown 报告只作为叙述材料，不作为数值来源。",
            styles["normal"],
        ),
        _kv_table([
            ("原始输出目录", str(raw_output_dir)),
            ("分析目录", str(analysis_dir)),
            ("图像清单", str(analysis_dir / "figures_manifest.json")),
            ("图像目录", str(manifest.get("figures_dir") or analysis_dir / "figures")),
        ], styles),
    ]
    return lines


def _calculation_info_section(raw_output_dir: Path, styles: dict[str, ParagraphStyle]) -> list:
    incar = _parse_incar(raw_output_dir)
    kpoints = _parse_kpoints(raw_output_dir)
    poscar = _parse_poscar(raw_output_dir)
    rows = [
        ("体系", _system_summary(poscar)),
        ("平面波截断能 / 精度", f"{incar.get('ENCUT', 'unknown')} eV / {incar.get('PREC', 'unknown')}"),
        ("K 点网格", kpoints),
        ("电子收敛判据", f"EDIFF = {incar.get('EDIFF', 'unknown')}"),
    ]
    return [
        Paragraph("1. 计算基本信息", styles["h1"]),
        Paragraph("下表由 raw_output 中的 INCAR、KPOINTS、POSCAR/CONTCAR 解析得到，用于说明本次 VASP 作业的基本设置。", styles["subtitle"]),
        _info_table(rows, styles),
    ]


def _summary_points(facts: dict, figures: list[dict[str, Any]]) -> list[str]:
    points = []
    convergence = facts.get("convergence") or {}
    if convergence:
        state = "已收敛" if convergence.get("converged") else "未确认收敛"
        points.append(f"计算收敛判断：{state}；依据：{convergence.get('converged_reason', 'unknown')}。")

    energy = facts.get("energy") or {}
    if energy.get("toten") is not None:
        points.append(f"最终自由能 TOTEN = {energy['toten']:.8f} eV。")

    forces = facts.get("forces") or {}
    if forces.get("max_force_eV_A") is not None:
        points.append(f"最终最大力约为 {forces['max_force_eV_A']:.6f} eV/A；用于判断结构优化是否足够稳定。")

    band = facts.get("band_structure") or {}
    if band.get("band_gap_eV") is not None:
        points.append(f"解析到 Gamma 点附近带隙约 {band['band_gap_eV']:.4f} eV；完整能带/DOS 仍需专门计算文件支持。")

    if figures:
        points.append(f"报告包含 {len(figures)} 张由 raw_output 解析数据生成的分析图像，并附带逐图解释。")

    if not points:
        points.append("当前 raw_output 中可解析的确定性结果有限，建议检查 OUTCAR/OSZICAR 是否完整同步。")
    return points


def _convergence_section(facts: dict, figures: list[dict[str, Any]], styles: dict[str, ParagraphStyle]) -> list:
    convergence = facts.get("convergence") or {}
    oszicar = facts.get("oszicar") or {}
    rows = [
        ("收敛状态", "已收敛" if convergence.get("converged") else "未确认收敛"),
        ("判断依据", convergence.get("converged_reason", "unknown")),
        ("电子迭代次数", str(oszicar.get("iterations", "unknown"))),
        ("电子能量变化范围", f"{oszicar.get('energy_range_eV')} eV" if oszicar.get("energy_range_eV") is not None else "unknown"),
        ("生成图像", f"{len(figures)} 张 SVG 图，数据来自 raw_output 解析得到的 CSV"),
    ]
    beginner_text = (
        "电子 SCF 循环可以理解为 VASP 反复调整电子密度直到稳定。若电子步收敛，说明在当前结构和参数下，电子结构已经满足给定精度。"
        "如果这是静态单点计算，ionic energy、force、pressure、volume 图可能只有一个点或一条水平线；这不是错误，而是说明没有完整的离子结构优化轨迹。"
    )
    return [
        Paragraph("2. 收敛状态与结果解释", styles["h1"]),
        _info_box("新手提示", beginner_text, styles),
        _info_table(rows, styles),
    ]


def _energy_electronic_section(facts: dict, styles: dict[str, ParagraphStyle]) -> list:
    energy = facts.get("energy") or {}
    oszicar = facts.get("oszicar") or {}
    electronic = facts.get("electronic") or {}
    band = facts.get("band_structure") or {}
    rows = [
        ("自由能 TOTEN", _with_unit(_fmt_num(energy.get("toten"), 8), "eV")),
        ("无熵修正能量", _with_unit(_fmt_num(energy.get("energy_without_entropy"), 8), "eV")),
        ("sigma->0 外推能量", _with_unit(_fmt_num(energy.get("energy_sigma0"), 8), "eV")),
        ("最终 SCF 步", _final_scf_summary(oszicar)),
        ("费米能级", _with_unit(_fmt_num(electronic.get("efermi"), 4), "eV")),
        ("电子结构备注", _band_gap_note(band, electronic)),
    ]
    return [
        Paragraph("3. 能量与电子结构", styles["h1"]),
        _info_table([(key, value) for key, value in rows if value and value != "unknown"], styles),
    ]


def _mechanics_performance_section(facts: dict, styles: dict[str, ParagraphStyle]) -> list:
    stress = facts.get("stress") or {}
    forces = facts.get("forces") or {}
    timing = facts.get("timing") or {}
    cell = facts.get("cell") or {}
    rows = [
        ("应力张量 XX / YY / ZZ", _stress_summary(stress, 0, 3)),
        ("应力张量 XY / YZ / ZX", _stress_summary(stress, 3, 6)),
        ("外部压力", _with_unit(_fmt_num(stress.get("external_pressure_kB"), 4), "kB")),
        ("最大 / 平均原子受力", _force_summary(forces)),
        ("晶胞体积", _with_unit(_fmt_num(cell.get("volume"), 4), "A^3")),
        ("CPU / 实际耗时", _time_summary(timing)),
        ("最大内存占用", _memory_summary(timing)),
    ]
    return [
        Paragraph("4. 力学量与计算性能", styles["h1"]),
        _info_table([(key, value) for key, value in rows if value and value != "unknown"], styles),
    ]


def _parse_incar(raw_output_dir: Path) -> dict[str, str]:
    path = raw_output_dir / "INCAR"
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.split("#", 1)[0].split("!", 1)[0].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().upper()
        value = value.strip().rstrip(";")
        if key:
            result[key] = value
    return result


def _parse_kpoints(raw_output_dir: Path) -> str:
    path = raw_output_dir / "KPOINTS"
    if not path.is_file():
        return "unknown"
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    if len(lines) >= 4:
        mode = lines[2]
        grid = lines[3]
        return f"{mode}: {grid}"
    return " / ".join(lines[:4]) if lines else "unknown"


def _parse_poscar(raw_output_dir: Path) -> dict[str, Any]:
    path = raw_output_dir / "CONTCAR"
    if not path.is_file():
        path = raw_output_dir / "POSCAR"
    if not path.is_file():
        return {}
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    if not lines:
        return {}
    result: dict[str, Any] = {"title": lines[0]}
    if len(lines) >= 7:
        species_line = lines[5].split()
        counts_line = lines[6].split()
        try:
            counts = [int(value) for value in counts_line]
        except ValueError:
            counts = []
        if counts and len(species_line) == len(counts):
            result["species"] = species_line
            result["counts"] = counts
            result["num_atoms"] = sum(counts)
        elif counts:
            result["counts"] = counts
            result["num_atoms"] = sum(counts)
    return result


def _system_summary(poscar: dict[str, Any]) -> str:
    title = poscar.get("title") or "unknown"
    species = poscar.get("species") or []
    counts = poscar.get("counts") or []
    atoms = poscar.get("num_atoms")
    if species and counts:
        composition = ", ".join(f"{element}{count}" for element, count in zip(species, counts))
        return f"{title}; composition: {composition}; atoms: {atoms}"
    if atoms is not None:
        return f"{title}; atoms: {atoms}"
    return str(title)


def _with_unit(value: str | None, unit: str) -> str:
    if value is None:
        return "unknown"
    return f"{value} {unit}"


def _final_scf_summary(oszicar: dict[str, Any]) -> str:
    parts = []
    if oszicar.get("F") is not None:
        parts.append(f"F = {_fmt_num(oszicar.get('F'), 8)} eV")
    if oszicar.get("E0") is not None:
        parts.append(f"E0 = {_fmt_num(oszicar.get('E0'), 8)} eV")
    if oszicar.get("dE") is not None:
        parts.append(f"dE = {_fmt_num(oszicar.get('dE'), 8)} eV")
    return "; ".join(parts) if parts else "unknown"


def _band_gap_note(band: dict[str, Any], electronic: dict[str, Any]) -> str:
    gap = band.get("band_gap_eV")
    if gap is None:
        ismear = electronic.get("ismear")
        if ismear is not None and ismear > 0:
            return "未解析到可靠带隙；金属展宽计算中的小能隙不应直接解释为真实半导体带隙。"
        return "未从 raw_output 中解析到可报告的带隙。"
    vbm = _fmt_num(band.get("vbm_eV"), 4)
    cbm = _fmt_num(band.get("cbm_eV"), 4)
    return f"Gamma 点附近 band gap = {_fmt_num(gap, 4)} eV; VBM = {vbm} eV; CBM = {cbm} eV。"


def _stress_summary(stress: dict[str, Any], start: int, end: int) -> str:
    values = stress.get("stress_kB")
    if not isinstance(values, list) or len(values) < end:
        return "unknown"
    return " / ".join(f"{value:.2f}" for value in values[start:end]) + " kB"


def _force_summary(forces: dict[str, Any]) -> str:
    max_force = _fmt_num(forces.get("max_force_eV_A"), 6)
    mean_force = _fmt_num(forces.get("mean_force_norm_eV_A"), 6)
    if max_force is None and mean_force is None:
        return "unknown"
    return f"max = {max_force or 'unknown'} eV/A; mean = {mean_force or 'unknown'} eV/A"


def _time_summary(timing: dict[str, Any]) -> str:
    cpu = _fmt_num(timing.get("total_cpu_time_sec"), 2)
    elapsed = _fmt_num(timing.get("elapsed_time_sec"), 2)
    if cpu is None and elapsed is None:
        return "unknown"
    return f"CPU = {cpu or 'unknown'} s; elapsed = {elapsed or 'unknown'} s"


def _memory_summary(timing: dict[str, Any]) -> str:
    memory_kb = timing.get("max_memory_kb")
    if memory_kb is None:
        return "unknown"
    try:
        memory_mb = float(memory_kb) / 1024
    except (TypeError, ValueError):
        return f"{memory_kb} kB"
    return f"{memory_kb:.0f} kB (~{memory_mb:.0f} MB)"


def _info_table(rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    if not rows:
        rows = [("状态", "raw_output 中没有解析到可显示条目")]
    data = [[Paragraph("项目", styles["small"]), Paragraph("数值 / 解释", styles["small"])]]
    for key, value in rows:
        data.append([Paragraph(_escape(str(key)), styles["small"]), Paragraph(_escape(str(value)), styles["small"])])
    table = Table(data, colWidths=[4.8 * cm, 10.4 * cm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), PDF_FONT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#172033")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f4f7fb")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8dee9")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _info_box(title: str, text: str, styles: dict[str, ParagraphStyle]) -> Table:
    data = [[
        Paragraph(f"<b>{_escape(title)}</b>", styles["normal"]),
        Paragraph(_escape(text), styles["small"]),
    ]]
    table = Table(data, colWidths=[3.2 * cm, 12.0 * cm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef6ff")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#9ec9ef")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def _figure_card(title: str, figure: dict[str, Any], rows: list[dict[str, Any]], styles: dict[str, ParagraphStyle]) -> list:
    chart = _chart_drawing(rows, figure, width=455, height=235)
    explanation = Paragraph(_escape(_figure_explanation(figure, rows)), styles["small"])
    source = Paragraph(
        f"数据文件：{_escape(_display_path(figure.get('data_path', 'unknown')))}<br/>"
        f"SVG 图像：{_escape(_display_path(figure.get('svg_path') or figure.get('path') or 'unknown'))}",
        styles["small"],
    )
    card = Table(
        [[chart], [explanation], [source]],
        colWidths=[16.6 * cm],
        hAlign="LEFT",
    )
    card.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fbfcfe")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8dee9")),
        ("LINEABOVE", (0, 1), (-1, 1), 0.35, colors.HexColor("#e3e8f0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [
        Paragraph(_escape(title), styles["h2"]),
        card,
        Spacer(1, 10),
    ]


def _display_path(value: Any) -> str:
    text = str(value)
    marker = "/analysis/"
    if marker in text:
        return "analysis/" + text.split(marker, 1)[1]
    return text


def _facts_section(facts: dict, styles: dict[str, ParagraphStyle]) -> list:
    rows = []
    _append_fact(rows, "Converged", (facts.get("convergence") or {}).get("converged"))
    _append_fact(rows, "Convergence reason", (facts.get("convergence") or {}).get("converged_reason"))
    _append_fact(rows, "TOTEN (eV)", _fmt_num((facts.get("energy") or {}).get("toten"), 8))
    _append_fact(rows, "E-fermi (eV)", _fmt_num((facts.get("electronic") or {}).get("efermi"), 4))
    _append_fact(rows, "Max force (eV/A)", _fmt_num((facts.get("forces") or {}).get("max_force_eV_A"), 6))
    _append_fact(rows, "Mean force norm (eV/A)", _fmt_num((facts.get("forces") or {}).get("mean_force_norm_eV_A"), 6))
    _append_fact(rows, "External pressure (kB)", _fmt_num((facts.get("stress") or {}).get("external_pressure_kB"), 4))
    _append_fact(rows, "Volume (A^3)", _fmt_num((facts.get("cell") or {}).get("volume"), 4))
    _append_fact(rows, "Band gap (eV)", _fmt_num((facts.get("band_structure") or {}).get("band_gap_eV"), 4))
    _append_fact(rows, "Elapsed time (s)", _fmt_num((facts.get("timing") or {}).get("elapsed_time_sec"), 2))

    story = [
        Paragraph("关键确定性结果", styles["h1"]),
        Paragraph("下表只列出确定性解析器从 raw_output/OUTCAR 与 raw_output/OSZICAR 中提取到的结果。", styles["normal"]),
    ]
    if rows:
        story.append(_kv_table(rows, styles))
    else:
        story.append(Paragraph("当前 raw_output 中没有解析到可列入表格的关键结果。", styles["normal"]))
    return story


def _append_fact(rows: list[tuple[str, str]], key: str, value: Any) -> None:
    if value is not None and value != "":
        rows.append((key, str(value)))


def _figure_sections(figures: list[dict[str, Any]], styles: dict[str, ParagraphStyle]) -> list:
    story = [Paragraph("5. 分析图像与逐图解释", styles["h1"])]
    if not figures:
        story.append(Paragraph("未从 raw_output 中解析到可绘制的图表序列。", styles["normal"]))
        return story

    for index, figure in enumerate(figures, 1):
        rows = _read_csv_rows(Path(figure.get("data_path", "")))
        title = f"图 {index}. {figure.get('description') or figure.get('name') or 'Analysis figure'}"
        story.append(KeepTogether(_figure_card(title, figure, rows, styles)))
    return story


def _chart_drawing(rows: list[dict[str, Any]], figure: dict[str, Any], width: int = 470, height: int = 245) -> Drawing:
    left = 48 if width < 350 else 58
    right = 14 if width < 350 else 18
    top = 24 if height < 220 else 28
    bottom = 36 if height < 220 else 42
    plot_w = width - left - right
    plot_h = height - top - bottom
    drawing = Drawing(width, height)

    x_key = figure.get("x_key") or _infer_x_key(rows)
    y_key = figure.get("y_key") or _infer_y_key(rows)
    points = [
        (float(row[x_key]), float(row[y_key]))
        for row in rows
        if x_key in row and y_key in row and _is_number(row[x_key]) and _is_number(row[y_key])
    ]
    if not points:
        drawing.add(String(left, height / 2, "No plottable data", fontName=PDF_FONT, fontSize=10, fillColor=colors.grey))
        return drawing

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_min, x_max, y_min, y_max = _chart_bounds(xs, ys)

    def sx(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_w

    def sy(value: float) -> float:
        return bottom + (value - y_min) / (y_max - y_min) * plot_h

    for tick in _ticks(x_min, x_max):
        x = sx(tick)
        drawing.add(Line(x, bottom, x, bottom + plot_h, strokeColor=colors.HexColor("#dddddd"), strokeWidth=0.5))
        drawing.add(String(x - 8, 14, _short_num(tick), fontName=PDF_FONT, fontSize=7, fillColor=colors.HexColor("#333333")))

    for tick in _ticks(y_min, y_max):
        y = sy(tick)
        drawing.add(Line(left, y, left + plot_w, y, strokeColor=colors.HexColor("#dddddd"), strokeWidth=0.5))
        drawing.add(String(4, y - 3, _short_num(tick), fontName=PDF_FONT, fontSize=7, fillColor=colors.HexColor("#333333")))

    drawing.add(Line(left, bottom, left + plot_w, bottom, strokeColor=colors.black, strokeWidth=1))
    drawing.add(Line(left, bottom, left, bottom + plot_h, strokeColor=colors.black, strokeWidth=1))
    drawing.add(String(left + plot_w / 2 - 30, 0, figure.get("x_label") or x_key, fontName=PDF_FONT, fontSize=7.5))
    drawing.add(String(0, height - 12, figure.get("y_label") or y_key, fontName=PDF_FONT, fontSize=7.5))

    pdf_points = [(sx(x), sy(y)) for x, y in points]
    if len(pdf_points) > 1:
        drawing.add(PolyLine(pdf_points, strokeColor=colors.HexColor("#1565c0"), strokeWidth=1.8))
    for x, y in pdf_points:
        drawing.add(Circle(x, y, 2.8, fillColor=colors.HexColor("#1565c0"), strokeColor=colors.HexColor("#1565c0")))
    return drawing


def _figure_explanation(figure: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    name = figure.get("name", "")
    y_key = figure.get("y_key") or _infer_y_key(rows)
    values = [float(row[y_key]) for row in rows if y_key in row and _is_number(row[y_key])]
    row_count = len(values)
    if row_count == 0:
        return "这张图没有可解释的数值点。请检查对应 CSV 是否完整。"

    if row_count == 1:
        base = f"这张图只有 1 个数据点，说明该作业在这个量上只记录到一个离子步/采样点。"
        if name in {"ionic_energy", "max_force", "pressure", "volume"}:
            base += " 这通常见于静态计算，或结构优化只完成/输出了一个 ionic step；因此它不能被解读为完整收敛趋势。"
        return base + f" 当前值为 {values[0]:.6g}。"

    delta = values[-1] - values[0]
    direction = "下降" if delta < 0 else "上升" if delta > 0 else "基本不变"
    base = (
        f"该图包含 {row_count} 个数据点，初值 {values[0]:.6g}，末值 {values[-1]:.6g}，"
        f"总体变化 {delta:.6g}，趋势为{direction}。"
    )
    if name == "electronic_energy":
        return base + " 对新手来说，电子步能量如果逐渐稳定，通常表示自洽迭代正在接近稳定解；若明显振荡，则需要关注混合参数、结构或初始电荷。"
    if name == "ionic_energy":
        return base + " 离子步能量用于观察结构优化过程；持续下降并逐步平缓通常更接近稳定结构。"
    if name == "max_force":
        return base + " 最大力越小，结构越接近力收敛；是否达标还要和 INCAR 中的力收敛阈值比较。"
    if name == "pressure":
        return base + " 外压用于判断晶胞应力状态；若做晶胞优化，压力趋近目标值更有意义。"
    if name == "volume":
        return base + " 体积变化反映晶胞是否在优化中调整；静态计算中体积保持不变是正常现象。"
    return base


def _markdown_section(title: str, path: Path, styles: dict[str, ParagraphStyle]) -> list:
    story = [Paragraph(_escape(title), styles["h1"])]
    if not path.is_file():
        story.append(Paragraph(f"未找到文件：{_escape(str(path))}", styles["normal"]))
        return story
    story.extend(_markdown_to_flowables(path.read_text(encoding="utf-8", errors="replace"), styles))
    return story


def _markdown_to_flowables(text: str, styles: dict[str, ParagraphStyle]) -> list:
    story = []
    in_code = False
    code_lines = []
    paragraph_lines = []
    table_lines = []

    def flush_paragraph():
        if paragraph_lines:
            story.append(Paragraph(_escape(" ".join(paragraph_lines)), styles["normal"]))
            paragraph_lines.clear()

    def flush_code():
        if code_lines:
            story.append(Paragraph("<br/>".join(_escape(line) for line in code_lines), styles["code"]))
            code_lines.clear()

    def flush_table():
        if table_lines:
            parsed = _parse_markdown_table(table_lines)
            if parsed:
                story.append(_markdown_table(parsed, styles))
            else:
                story.append(Paragraph(_escape(" ".join(table_lines)), styles["normal"]))
            table_lines.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                flush_paragraph()
                flush_table()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_table()
            continue
        if _is_markdown_table_line(stripped):
            flush_paragraph()
            table_lines.append(stripped)
            continue
        flush_table()
        if stripped.startswith("# "):
            flush_paragraph()
            story.append(Paragraph(_escape(stripped[2:].strip()), styles["h2"]))
        elif stripped.startswith("## "):
            flush_paragraph()
            story.append(Paragraph(_escape(stripped[3:].strip()), styles["h2"]))
        elif stripped.startswith(("- ", "* ")):
            flush_paragraph()
            story.append(Paragraph(f"• {_escape(stripped[2:].strip())}", styles["normal"]))
        else:
            paragraph_lines.append(_strip_markdown(stripped))
    flush_paragraph()
    flush_table()
    flush_code()
    return story


def _is_markdown_table_line(line: str) -> bool:
    return line.startswith("|") and line.endswith("|") and line.count("|") >= 2


def _parse_markdown_table(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells:
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
            continue
        rows.append([_strip_markdown(cell) for cell in cells])
    if len(rows) < 1:
        return []
    width = max(len(row) for row in rows)
    return [row + [""] * (width - len(row)) for row in rows]


def _markdown_table(rows: list[list[str]], styles: dict[str, ParagraphStyle]) -> Table:
    usable_width = 15.2 * cm
    col_count = max(1, len(rows[0]))
    col_widths = [usable_width / col_count] * col_count
    data = [
        [Paragraph(_escape(cell), styles["small"]) for cell in row]
        for row in rows
    ]
    table = Table(data, colWidths=col_widths, hAlign="LEFT", repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), PDF_FONT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#172033")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8dee9")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _kv_table(rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    if not rows:
        rows = [("状态", "无可显示条目")]
    data = [
        [Paragraph(_escape(str(key)), styles["small"]), Paragraph(_escape(str(value)), styles["small"])]
        for key, value in rows
    ]
    table = Table(data, colWidths=[4.2 * cm, 11.0 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), PDF_FONT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f6f8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _infer_x_key(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "x"
    for key in ("ionic_step", "global_iteration", "electronic_step"):
        if key in rows[0]:
            return key
    return next(iter(rows[0]))


def _infer_y_key(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "y"
    candidates = [key for key in rows[0] if key not in {"ionic_step", "global_iteration", "electronic_step", "algorithm"}]
    return candidates[0] if candidates else next(iter(rows[0]))


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
    return x_min, x_max, y_min - y_pad, y_max + y_pad


def _ticks(min_value: float, max_value: float, count: int = 5) -> list[float]:
    step = (max_value - min_value) / max(1, count - 1)
    return [min_value + step * index for index in range(count)]


def _fmt_num(value: Any, digits: int) -> str | None:
    if value is None:
        return None
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _short_num(value: float) -> str:
    if value == 0:
        return "0"
    if abs(value) >= 1000 or abs(value) < 0.001:
        return f"{value:.1e}"
    if abs(value) >= 10:
        return f"{value:.2f}"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _strip_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

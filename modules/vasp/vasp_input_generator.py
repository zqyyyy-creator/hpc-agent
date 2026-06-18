from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from modules.core.hpc_config import VASP_LOCAL_JOBS_DIR


@dataclass(frozen=True)
class PotcarEntry:
    label: str
    element: str
    titel: str
    enmax: float | None = None
    zval: float | None = None


@dataclass(frozen=True)
class VaspInputOptions:
    calculation: str = "static"
    encut: int | None = None
    kpoints: tuple[int, int, int] = (6, 6, 6)
    nsw: int | None = None
    ediff: float | None = None
    ismear: int | None = None
    sigma: float | None = None
    overwrite: bool = False


DEFAULT_LATTICE_CONSTANTS = {
    ("Al",): 4.05,
    ("Si",): 5.43,
    ("Mg", "O"): 4.21,
    ("Na", "Cl"): 5.64,
}

METALLIC_ELEMENTS = {
    "Li", "Na", "K", "Rb", "Cs", "Fr",
    "Be", "Mg", "Ca", "Sr", "Ba", "Ra",
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd",
    "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Al", "Ga", "In", "Tl", "Sn", "Pb", "Bi",
}


def generate_vasp_inputs_from_potcar_request(
    text: str,
    *,
    jobs_dir: str = VASP_LOCAL_JOBS_DIR,
) -> dict:
    job_dir = resolve_vasp_input_generation_dir(text, jobs_dir=jobs_dir)
    if not job_dir:
        return {
            "success": False,
            "message": (
                "没有找到要生成配置文件的 VASP 作业目录。\n\n"
                f"请把作业目录放在本地 VASP 输入根目录下: {Path(jobs_dir).expanduser().resolve()}\n"
                "示例：帮我生成我的 VASP 作业 Al_test 的配置文件"
            ),
        }

    result = generate_vasp_inputs_from_potcar(job_dir, user_request=text)
    return result


def resolve_vasp_input_generation_dir(
    text: str,
    *,
    jobs_dir: str = VASP_LOCAL_JOBS_DIR,
) -> Path | None:
    selector = extract_vasp_input_generation_selector(text)
    root = Path(jobs_dir).expanduser()

    if selector:
        path = Path(selector).expanduser()
        if path.is_absolute():
            return path
        return root / selector

    if not root.is_dir():
        return None

    candidates = [
        path
        for path in root.iterdir()
        if path.is_dir() and (path / "POTCAR").is_file()
    ]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def extract_vasp_input_generation_selector(text: str) -> str | None:
    path_match = re.search(r"(/[^\s，,。]+)", text)
    if path_match:
        return path_match.group(1)

    patterns = [
        r"(?:作业目录|子目录|目录名|路径|dir|directory)\s*[:：=]?\s*([A-Za-z0-9_.~/-]+)",
        r"生成\s*([A-Za-z0-9_.-]+)\s*的\s*(?:vasp|VASP)\s*(?:输入|输入文件|配置|配置文件)",
        r"(?:vasp|VASP)?\s*作业\s*([A-Za-z0-9_.-]+)",
        r"(?:vasp|VASP)\s*(?:输入|输入文件|配置|配置文件)\s*([A-Za-z0-9_.-]+)",
        r"(?:job|作业名)\s*[:：=]?\s*([A-Za-z0-9_.-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if value.lower() not in {"vasp", "job", "作业", "配置文件"}:
                return value

    return None


def generate_vasp_inputs_from_potcar(
    job_dir: str | Path,
    *,
    user_request: str = "",
) -> dict:
    job_path = Path(job_dir).expanduser()
    potcar_path = job_path / "POTCAR"

    if not job_path.is_dir():
        return {
            "success": False,
            "message": f"VASP 作业目录不存在: {job_path}",
            "job_dir": str(job_path),
        }

    if not potcar_path.is_file():
        return {
            "success": False,
            "message": f"没有找到 POTCAR: {potcar_path}\n请先把真实合法的 POTCAR 放入该作业目录。",
            "job_dir": str(job_path),
        }

    potcar_text = potcar_path.read_text(encoding="utf-8", errors="ignore")
    entries = parse_potcar_entries(potcar_text)

    if not entries:
        return {
            "success": False,
            "message": (
                "读取 POTCAR 失败：没有解析到 TITEL/元素信息。\n"
                "请确认 POTCAR 是真实 VASP 赝势文件，不是空文件或占位文件。"
            ),
            "job_dir": str(job_path),
        }

    elements = [entry.element for entry in entries]
    options, option_errors = parse_vasp_input_options(user_request)
    if option_errors:
        return {
            "success": False,
            "message": (
                "VASP 输入参数不合法，未写入文件。\n\n"
                + "\n".join(f"- {error}" for error in option_errors)
            ),
            "job_dir": str(job_path),
            "elements": elements,
            "option_errors": option_errors,
        }

    if len(entries) > 2 and _lacks_structure_details(user_request):
        return {
            "success": False,
            "message": (
                "已读取 POTCAR，但当前包含 3 个及以上赝势段。\n\n"
                f"元素顺序: {' '.join(elements)}\n\n"
                "仅凭 POTCAR 无法可靠猜出晶体结构、化学计量比和原子坐标。"
                "请补充结构类型、晶格常数或直接提供 POSCAR。"
            ),
            "job_dir": str(job_path),
            "elements": elements,
        }

    recommended = recommended_encut(entries)
    encut = options.encut if options.encut is not None else recommended
    encut_source = "用户参数" if options.encut is not None else "POTCAR ENMAX 推荐"
    incar = build_incar(entries, options=options, encut=encut)
    kpoints = build_kpoints(options.kpoints)
    poscar = build_default_poscar(entries)

    files = {
        "INCAR": incar,
        "KPOINTS": kpoints,
        "POSCAR": poscar,
    }

    existing_files = [
        name
        for name in files
        if (job_path / name).exists()
    ]
    if existing_files and not options.overwrite:
        return {
            "success": False,
            "message": (
                "没有写入文件，因为作业目录中已经存在 VASP 配置文件。\n\n"
                f"作业目录: {job_path}\n"
                f"已存在: {', '.join(existing_files)}\n\n"
                "如果确认要重新生成并覆盖，请明确说“覆盖已有配置文件”。"
            ),
            "job_dir": str(job_path),
            "elements": elements,
            "existing_files": existing_files,
        }

    written = []
    for name, content in files.items():
        path = job_path / name
        path.write_text(content, encoding="utf-8")
        written.append(str(path))

    warning = _smoke_test_warning()
    message = (
        "已根据该目录中的 POTCAR 生成 VASP 配置文件。\n\n"
        f"作业目录: {job_path}\n"
        f"元素顺序: {' '.join(elements)}\n"
        f"POTCAR 标题: {', '.join(entry.titel for entry in entries)}\n"
        f"ENCUT: {encut} eV（来源: {encut_source}）\n"
        f"KPOINTS: {' '.join(str(value) for value in options.kpoints)}\n"
        f"计算类型: {options.calculation}\n"
        f"覆盖已有文件: {'是' if options.overwrite else '否'}\n\n"
        "已写入:\n"
        + "\n".join(f"- {path}" for path in written)
        + "\n\n"
        + warning
    )

    return {
        "success": True,
        "message": message,
        "job_dir": str(job_path),
        "elements": elements,
        "entries": [entry.__dict__ for entry in entries],
        "encut": encut,
        "encut_source": encut_source,
        "calculation": options.calculation,
        "options": options.__dict__,
        "written_files": written,
        "smoke_test": _lacks_structure_details(user_request),
    }


def parse_potcar_entries(text: str) -> list[PotcarEntry]:
    titel_matches = list(re.finditer(r"^\s*TITEL\s*=\s*(.+?)\s*$", text, re.MULTILINE))

    if not titel_matches:
        return []

    entries = []
    for index, match in enumerate(titel_matches):
        start = match.start()
        end = titel_matches[index + 1].start() if index + 1 < len(titel_matches) else len(text)
        block = text[start:end]
        titel = match.group(1).strip()
        label = _label_from_titel(titel)
        entries.append(
            PotcarEntry(
                label=label,
                element=_element_from_label(label),
                titel=titel,
                enmax=_extract_float(block, r"ENMAX\s*=\s*([0-9.]+)"),
                zval=_extract_float(block, r"ZVAL\s*=\s*([0-9.]+)"),
            )
        )

    return entries


def recommended_encut(entries: list[PotcarEntry]) -> int:
    enmax_values = [entry.enmax for entry in entries if entry.enmax is not None]
    if not enmax_values:
        return 520
    return int(math.ceil(max(enmax_values) * 1.3 / 10.0) * 10)


def parse_vasp_input_options(text: str) -> tuple[VaspInputOptions, list[str]]:
    calculation = _extract_calculation_type(text)
    encut = _extract_int_option(text, ["encut"], r"(?:ENCUT|encut)\s*[=:：]?\s*(\d+)")
    kpoints = _extract_kpoints(text)
    nsw = _extract_int_option(text, ["nsw"], r"(?:NSW|nsw)\s*[=:：]?\s*(\d+)")
    ediff = _extract_float_option(text, ["ediff"], r"(?:EDIFF|ediff)\s*[=:：]?\s*([0-9.eE+-]+)")
    ismear = _extract_int_option(text, ["ismear"], r"(?:ISMEAR|ismear)\s*[=:：]?\s*(-?\d+)")
    sigma = _extract_float_option(text, ["sigma"], r"(?:SIGMA|sigma)\s*[=:：]?\s*([0-9.eE+-]+)")
    overwrite = _allows_overwrite(text)

    options = VaspInputOptions(
        calculation=calculation,
        encut=encut,
        kpoints=kpoints or (6, 6, 6),
        nsw=nsw,
        ediff=ediff,
        ismear=ismear,
        sigma=sigma,
        overwrite=overwrite,
    )
    return options, validate_vasp_input_options(options)


def validate_vasp_input_options(options: VaspInputOptions) -> list[str]:
    errors: list[str] = []

    if options.calculation not in {"static", "relax"}:
        errors.append("计算类型只支持 static 或 relax。")

    if options.encut is not None and not 100 <= options.encut <= 2000:
        errors.append("ENCUT 建议在 100 到 2000 eV 之间。")

    if any(value <= 0 or value > 60 for value in options.kpoints):
        errors.append("KPOINTS 网格必须是 1 到 60 之间的三个正整数。")

    if options.nsw is not None and not 0 <= options.nsw <= 10000:
        errors.append("NSW 必须是 0 到 10000 之间的整数。")

    if options.ediff is not None and options.ediff <= 0:
        errors.append("EDIFF 必须是正数。")

    if options.ismear is not None and not -5 <= options.ismear <= 5:
        errors.append("ISMEAR 建议在 -5 到 5 之间。")

    if options.sigma is not None and not 0 <= options.sigma <= 5:
        errors.append("SIGMA 建议在 0 到 5 之间。")

    return errors


def _extract_cli_option(text: str, names: list[str]) -> str | None:
    for name in names:
        match = re.search(rf"--{re.escape(name)}(?:=|\s+)([^\s，,。]+)", text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_int_option(text: str, names: list[str], pattern: str) -> int | None:
    value = _extract_cli_option(text, names)
    if value is None:
        match = re.search(pattern, text)
        value = match.group(1) if match else None
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _extract_float_option(text: str, names: list[str], pattern: str) -> float | None:
    value = _extract_cli_option(text, names)
    if value is None:
        match = re.search(pattern, text)
        value = match.group(1) if match else None
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _extract_kpoints(text: str) -> tuple[int, int, int] | None:
    cli_match = re.search(
        r"--kpoints(?:=|\s+)(\d+)[xX*，,\s]+(\d+)[xX*，,\s]+(\d+)",
        text,
        re.IGNORECASE,
    )
    if cli_match:
        return tuple(int(cli_match.group(index)) for index in (1, 2, 3))

    patterns = [
        r"(?:KPOINTS|kpoints|k点|K点)\s*[=:：]?\s*(\d+)\s*[xX*]\s*(\d+)\s*[xX*]\s*(\d+)",
        r"(?:KPOINTS|kpoints|k点|K点)\s*[=:：]?\s*(\d+)\s+(\d+)\s+(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return tuple(int(match.group(index)) for index in (1, 2, 3))

    return None


def build_incar(
    entries: list[PotcarEntry],
    *,
    options: VaspInputOptions | None = None,
    encut: int = 520,
) -> str:
    options = options or VaspInputOptions()
    elements = [entry.element for entry in entries]
    is_metal = len(elements) == 1 and elements[0] in METALLIC_ELEMENTS
    ediff = options.ediff if options.ediff is not None else 1e-5
    ismear = options.ismear
    sigma = options.sigma

    lines = [
        "SYSTEM = smoke_test_from_potcar",
        "PREC = Accurate",
        f"ENCUT = {encut}",
        f"EDIFF = {_format_vasp_float(ediff)}",
    ]

    if ismear is None:
        ismear = 1 if is_metal else 0
    if sigma is None:
        sigma = 0.2 if is_metal else 0.05

    lines.extend([f"ISMEAR = {ismear}", f"SIGMA = {_format_vasp_float(sigma)}"])

    if options.calculation == "relax":
        nsw = options.nsw if options.nsw is not None else 40
        lines.extend([
            "IBRION = 2",
            f"NSW = {nsw}",
            "ISIF = 2",
        ])
    else:
        nsw = options.nsw if options.nsw is not None else 0
        lines.extend([
            "IBRION = -1",
            f"NSW = {nsw}",
            "ISIF = 2",
        ])

    lines.extend([
        "LREAL = Auto",
        "LWAVE = .FALSE.",
        "LCHARG = .FALSE.",
        "",
    ])
    return "\n".join(lines)


def build_kpoints(mesh: tuple[int, int, int] = (6, 6, 6)) -> str:
    return "\n".join([
        "Automatic mesh",
        "0",
        "Gamma",
        f"{mesh[0]} {mesh[1]} {mesh[2]}",
        "0 0 0",
        "",
    ])


def build_default_poscar(entries: list[PotcarEntry]) -> str:
    elements = tuple(entry.element for entry in entries)
    lattice = DEFAULT_LATTICE_CONSTANTS.get(elements, 4.20)

    if len(entries) == 1 and elements == ("Si",):
        return _diamond_poscar(elements[0], lattice)

    if len(entries) == 1:
        return _fcc_single_poscar(elements[0], lattice)

    if len(entries) == 2:
        return _rocksalt_poscar(elements[0], elements[1], lattice)

    raise ValueError("默认 POSCAR 只支持 1 个或 2 个 POTCAR 赝势段。")


def _fcc_single_poscar(element: str, lattice: float) -> str:
    half = lattice / 2
    return "\n".join([
        f"{element} fcc smoke test",
        "1.0",
        f"0.000000 {half:.6f} {half:.6f}",
        f"{half:.6f} 0.000000 {half:.6f}",
        f"{half:.6f} {half:.6f} 0.000000",
        element,
        "1",
        "Direct",
        "0.000000 0.000000 0.000000",
        "",
    ])


def _diamond_poscar(element: str, lattice: float) -> str:
    half = lattice / 2
    return "\n".join([
        f"{element} diamond smoke test",
        "1.0",
        f"0.000000 {half:.6f} {half:.6f}",
        f"{half:.6f} 0.000000 {half:.6f}",
        f"{half:.6f} {half:.6f} 0.000000",
        element,
        "2",
        "Direct",
        "0.000000 0.000000 0.000000",
        "0.250000 0.250000 0.250000",
        "",
    ])


def _rocksalt_poscar(element_a: str, element_b: str, lattice: float) -> str:
    half = lattice / 2
    return "\n".join([
        f"{element_a}{element_b} rocksalt smoke test",
        "1.0",
        f"0.000000 {half:.6f} {half:.6f}",
        f"{half:.6f} 0.000000 {half:.6f}",
        f"{half:.6f} {half:.6f} 0.000000",
        f"{element_a} {element_b}",
        "1 1",
        "Direct",
        "0.000000 0.000000 0.000000",
        "0.500000 0.500000 0.500000",
        "",
    ])


def _extract_calculation_type(text: str) -> str:
    lowered = text.lower()
    cli_type = _extract_cli_option(text, ["type", "calculation"])
    if cli_type:
        value = cli_type.lower()
        if value in {"relax", "opt", "optimization"}:
            return "relax"
        if value in {"static", "scf"}:
            return "static"

    if any(keyword in lowered for keyword in ("relax", "opt", "弛豫", "结构优化", "优化")):
        return "relax"
    return "static"


def _lacks_structure_details(text: str) -> bool:
    lowered = text.lower()
    structure_keywords = [
        "晶格", "晶胞", "结构", "坐标", "poscar", "fcc", "bcc", "diamond",
        "rocksalt", "岩盐", "a=", "angstrom", "å",
    ]
    return not any(keyword in lowered for keyword in structure_keywords)


def _allows_overwrite(text: str) -> bool:
    return any(keyword in text.lower() for keyword in ("覆盖", "重新生成", "overwrite", "regenerate"))


def _label_from_titel(titel: str) -> str:
    parts = titel.split()
    for part in parts:
        if part.startswith("PAW"):
            continue
        if re.match(r"^[A-Z][a-z]?(?:_[A-Za-z0-9]+)?$", part):
            return part
    return parts[-2] if len(parts) >= 2 else titel


def _element_from_label(label: str) -> str:
    match = re.match(r"([A-Z][a-z]?)", label)
    return match.group(1) if match else label


def _extract_float(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return float(match.group(1))


def _format_vasp_float(value: float) -> str:
    if value == 0:
        return "0"
    if abs(value) < 1e-3 or abs(value) >= 1e4:
        return f"{value:.0E}".replace("E-0", "E-").replace("E+0", "E+")
    return f"{value:g}"


def _smoke_test_warning() -> str:
    return (
        "强提醒：你没有提供晶体结构、晶格常数或原子坐标时，Agent 生成的是默认 smoke test "
        "结构，只用于测试 VASP 能否启动、POTCAR 是否可读、提交流程是否正常；"
        "它不代表真实材料结构，不能直接用于正式科研结论。"
    )

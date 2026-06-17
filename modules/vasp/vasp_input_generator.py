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
        r"(?:vasp|VASP)?\s*作业\s*([A-Za-z0-9_.-]+)",
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

    calculation = _extract_calculation_type(user_request)
    encut = recommended_encut(entries)
    incar = build_incar(entries, calculation=calculation, encut=encut)
    kpoints = build_kpoints()
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
    if existing_files and not _allows_overwrite(user_request):
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
        f"推荐 ENCUT: {encut} eV\n"
        f"计算类型: {calculation}\n\n"
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
        "calculation": calculation,
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


def build_incar(
    entries: list[PotcarEntry],
    *,
    calculation: str = "static",
    encut: int = 520,
) -> str:
    elements = [entry.element for entry in entries]
    is_metal = len(elements) == 1 and elements[0] in METALLIC_ELEMENTS

    lines = [
        "SYSTEM = smoke_test_from_potcar",
        "PREC = Accurate",
        f"ENCUT = {encut}",
        "EDIFF = 1E-5",
    ]

    if is_metal:
        lines.extend(["ISMEAR = 1", "SIGMA = 0.2"])
    else:
        lines.extend(["ISMEAR = 0", "SIGMA = 0.05"])

    if calculation == "relax":
        lines.extend([
            "IBRION = 2",
            "NSW = 40",
            "ISIF = 2",
        ])
    else:
        lines.extend([
            "IBRION = -1",
            "NSW = 0",
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


def _smoke_test_warning() -> str:
    return (
        "强提醒：你没有提供晶体结构、晶格常数或原子坐标时，Agent 生成的是默认 smoke test "
        "结构，只用于测试 VASP 能否启动、POTCAR 是否可读、提交流程是否正常；"
        "它不代表真实材料结构，不能直接用于正式科研结论。"
    )

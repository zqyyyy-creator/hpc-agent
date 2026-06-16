import re
import shlex


VASP_KEY_FILES = [
    "INCAR",
    "POSCAR",
    "KPOINTS",
    "OUTCAR",
    "OSZICAR",
    "vasprun.xml",
    "vasp.out",
    "CONTCAR",
    "XDATCAR",
]


ERROR_RULES = [
    {
        "id": "potcar_input_conversion",
        "match": "all",
        "patterns": ["input conversion error", "unit 10", "potcar"],
        "summary": "POTCAR 读取失败，VASP 在启动阶段发生输入转换错误。",
        "recommendation": "检查 POTCAR 是否为空、损坏、占位文件，或与当前 VASP 版本/元素不兼容；替换为有效赝势后重新提交。",
    },
    {
        "id": "fortran_severe",
        "patterns": ["forrtl: severe", "severe ("],
        "summary": "检测到 Fortran 运行时严重错误。",
        "recommendation": "优先查看 stderr/OUTCAR 中的文件名和 unit 编号，确认输入文件格式、编码和完整性。",
    },
    {
        "id": "out_of_memory",
        "patterns": ["out of memory", "oom-kill", "cannot allocate memory"],
        "summary": "作业疑似内存不足。",
        "recommendation": "提高内存申请、减少并行规模，或检查体系规模、KPOINTS/ENCUT/NBANDS 是否过大。",
    },
    {
        "id": "segmentation_fault",
        "patterns": ["segmentation fault", "sigsegv"],
        "summary": "检测到段错误。",
        "recommendation": "检查输入文件完整性、并行参数和 VASP 编译环境；必要时换节点或减少并行度复现。",
    },
    {
        "id": "disk_full",
        "patterns": ["no space left on device", "disk quota exceeded", "quota exceeded"],
        "summary": "远端磁盘空间或配额不足。",
        "recommendation": "清理输出目录或调整任务输出策略，确认 WAVECAR/CHGCAR 等大文件写入位置。",
    },
    {
        "id": "permission_denied",
        "patterns": ["permission denied"],
        "summary": "检测到权限错误。",
        "recommendation": "检查作业目录、输入文件和输出文件的读写权限。",
    },
    {
        "id": "walltime",
        "patterns": ["time limit", "cancelled at", "due to time limit", "walltime"],
        "summary": "作业可能因运行时间限制被终止。",
        "recommendation": "增加 Slurm time limit，或先用较小体系/较松收敛条件估算运行时间。",
    },
]


WARNING_RULES = [
    {
        "id": "brmix",
        "patterns": ["brmix: very serious problems", "brmix"],
        "summary": "检测到 BRMIX 混合警告，电子步可能不稳定。",
        "recommendation": "考虑调整 AMIX/BMIX、ALGO、ISMEAR/SIGMA，或从更合理初始结构/电荷密度开始。",
    },
    {
        "id": "zbrent",
        "patterns": ["zbrent: fatal error", "zbrent"],
        "summary": "检测到 ZBRENT 相关收敛异常。",
        "recommendation": "检查结构是否过近接触，适当降低步长或更换离子优化参数。",
    },
    {
        "id": "electronic_not_converged",
        "patterns": ["edddav: call to zhegv failed", "davidson", "rmm-diis"],
        "summary": "电子步求解器出现异常或收敛困难信号。",
        "recommendation": "尝试调整 ALGO/NELM、初始磁矩、混合参数，或检查结构和赝势是否合理。",
    },
]


def _build_remote_probe_command(remote_workdir: str) -> str:
    safe_dir = shlex.quote(remote_workdir)
    key_files = " ".join(shlex.quote(name) for name in VASP_KEY_FILES + ["POTCAR"])

    return (
        f"cd {safe_dir} && "
        "{ "
        f"for f in {key_files}; do "
        "if [ -e \"$f\" ]; then stat -c 'FILE\t%n\t%s\t%Y' \"$f\"; fi; "
        "done; "
        "find . -maxdepth 1 -type f \\( -name '*.out' -o -name '*.err' \\) "
        "-printf 'FILE\t%f\t%s\t%T@\\n'; "
        "echo '__TAIL_OSZICAR__'; tail -n 30 OSZICAR 2>/dev/null || true; "
        "echo '__TAIL_OUTCAR__'; tail -n 60 OUTCAR 2>/dev/null || true; "
        "echo '__TAIL_VASP_OUT__'; tail -n 60 vasp.out 2>/dev/null || true; "
        "echo '__TAIL_ERR__'; "
        "for f in *.err; do [ -f \"$f\" ] && { echo \"--- $f ---\"; tail -n 60 \"$f\"; }; done; "
        "}"
    )


def _parse_probe_output(output: str):
    files = []
    text_lines = []

    for line in output.splitlines():
        if line.startswith("FILE\t"):
            parts = line.split("\t")
            if len(parts) >= 4:
                try:
                    size = int(float(parts[2]))
                except ValueError:
                    size = 0
                files.append({
                    "name": parts[1].lstrip("./"),
                    "size_bytes": size,
                    "mtime": parts[3],
                })
            continue

        text_lines.append(line)

    return files, "\n".join(text_lines)


def _contains_all(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return all(pattern.lower() in lowered for pattern in patterns)


def _contains_any(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def _add_issue(issues, severity, rule):
    issues.append({
        "severity": severity,
        "id": rule["id"],
        "summary": rule["summary"],
        "recommendation": rule["recommendation"],
    })


def _rule_matches(text: str, rule: dict) -> bool:
    if rule.get("match") == "all":
        return _contains_all(text, rule["patterns"])

    return _contains_any(text, rule["patterns"])


def _deduplicate_files(files):
    by_name = {}
    for file_info in files:
        name = file_info["name"]
        current = by_name.get(name)
        if current is None or file_info["size_bytes"] > current["size_bytes"]:
            by_name[name] = file_info
    return sorted(by_name.values(), key=lambda item: item["name"])


def diagnose_remote_vasp_job(
    remote_workdir: str | None,
    log_output: str = "",
    log_error: str = "",
    run_remote_command=None,
):
    diagnosis = {
        "is_vasp": False,
        "severity": "unknown",
        "summary": "尚未识别到 VASP 输出文件。",
        "issues": [],
        "evidence": [],
        "recommendations": [],
        "remote_files": [],
        "probe_error": "",
    }

    if not remote_workdir or run_remote_command is None:
        return diagnosis

    output, error = run_remote_command(_build_remote_probe_command(remote_workdir))
    files, probe_text = _parse_probe_output(output)
    files = _deduplicate_files(files)
    combined_text = "\n".join([log_output, log_error, probe_text, error])
    file_names = {file_info["name"] for file_info in files}
    has_vasp_files = bool(file_names & set(VASP_KEY_FILES + ["POTCAR"]))
    has_vasp_text = _contains_any(combined_text, ["vasp", "oszicar", "potcar", "incar", "poscar"])

    diagnosis["remote_files"] = files
    diagnosis["probe_error"] = error.strip()
    diagnosis["is_vasp"] = has_vasp_files or has_vasp_text

    if not diagnosis["is_vasp"]:
        return diagnosis

    for file_info in files:
        name = file_info["name"]
        if name in {"OUTCAR", "OSZICAR", "vasprun.xml", "CONTCAR", "XDATCAR"}:
            diagnosis["evidence"].append(f"{name}: {file_info['size_bytes']} bytes")

    if diagnosis["probe_error"]:
        diagnosis["evidence"].append(f"远端探测 stderr: {diagnosis['probe_error'][:160]}")

    for rule in ERROR_RULES:
        if _rule_matches(combined_text, rule):
            _add_issue(diagnosis["issues"], "error", rule)

    for rule in WARNING_RULES:
        if _contains_any(combined_text, rule["patterns"]):
            _add_issue(diagnosis["issues"], "warning", rule)

    size_by_name = {file_info["name"]: file_info["size_bytes"] for file_info in files}
    outcar_size = size_by_name.get("OUTCAR")
    oszicar_size = size_by_name.get("OSZICAR")
    vasprun_size = size_by_name.get("vasprun.xml")

    if outcar_size is not None and outcar_size < 2048:
        diagnosis["issues"].append({
            "severity": "warning",
            "id": "outcar_too_small",
            "summary": "OUTCAR 很小，VASP 可能还未进入有效计算阶段或已提前退出。",
            "recommendation": "结合 stderr/vasp.out 查看启动阶段报错；若 OSZICAR 也为空，优先检查 INCAR/POSCAR/KPOINTS/POTCAR。",
        })

    if oszicar_size == 0:
        diagnosis["issues"].append({
            "severity": "warning",
            "id": "empty_oszicar",
            "summary": "OSZICAR 为空，尚未记录电子步或离子步。",
            "recommendation": "这通常说明 VASP 尚未开始自洽迭代；先检查启动日志和输入文件。",
        })

    if vasprun_size is not None and vasprun_size < 2048:
        diagnosis["issues"].append({
            "severity": "warning",
            "id": "vasprun_too_small",
            "summary": "vasprun.xml 很小，XML 输出可能不完整。",
            "recommendation": "不要直接用于论文数据提取；等待任务完成或先修复导致提前退出的问题。",
        })

    if _contains_any(combined_text, ["reached required accuracy", "voluntary context switches"]):
        diagnosis["summary"] = "检测到 VASP 完成或接近完成的输出信号。"
        diagnosis["severity"] = "ok"
    else:
        diagnosis["summary"] = "检测到 VASP 输出，正在持续观察运行状态。"
        diagnosis["severity"] = "ok"

    if any(issue["severity"] == "error" for issue in diagnosis["issues"]):
        diagnosis["severity"] = "error"
        diagnosis["summary"] = diagnosis["issues"][0]["summary"]
    elif diagnosis["issues"]:
        diagnosis["severity"] = "warning"
        diagnosis["summary"] = diagnosis["issues"][0]["summary"]

    seen_recommendations = set()
    for issue in diagnosis["issues"]:
        recommendation = issue["recommendation"]
        if recommendation not in seen_recommendations:
            diagnosis["recommendations"].append(recommendation)
            seen_recommendations.add(recommendation)

    if not diagnosis["evidence"]:
        short_text = re.sub(r"\s+", " ", combined_text).strip()
        if short_text:
            diagnosis["evidence"].append(short_text[:180])

    return diagnosis

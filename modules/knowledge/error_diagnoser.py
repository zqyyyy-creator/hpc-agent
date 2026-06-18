import json
import re
from pathlib import Path


class ErrorDiagnoser:
    def __init__(
        self,
        db_path: str = "data/errors/generic_errors.json",
        real_cases_path: str = "data/errors/real_cases.json",
    ):
        self.db_path = Path(db_path)
        self.real_cases_path = Path(real_cases_path)
        self.error_db = self.load_error_db()
        self.real_cases = self.load_real_cases()

    def load_error_db(self):
        db_path = self.db_path
        if not db_path.exists() and db_path.name == "generic_errors.json":
            legacy_path = db_path.with_name("errors_db.json")
            if legacy_path.exists():
                db_path = legacy_path

        if not db_path.exists():
            raise FileNotFoundError(f"通用错误库不存在: {self.db_path}")

        with open(db_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_real_cases(self):
        if not self.real_cases_path.exists():
            return []

        with open(self.real_cases_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def diagnose(self, log_text: str):
        results = []

        for case in self.real_cases:
            matched_patterns = []

            for pattern in case["patterns"]:
                if re.search(pattern, log_text, re.IGNORECASE | re.MULTILINE):
                    matched_patterns.append(pattern)

            if matched_patterns:
                results.append({
                    "source": "real_case",
                    "id": case["id"],
                    "category": case["domain"],
                    "name": case["title"],
                    "severity": case.get("severity", "warning"),
                    "matched_patterns": matched_patterns,
                    "evidence": case.get("evidence", []),
                    "reason": case["reason"],
                    "solution": "；".join(case.get("suggestions", [])),
                    "suggestions": case.get("suggestions", []),
                    "commands": case.get("commands", []),
                    "prevention": case.get("prevention", ""),
                    "score": len(matched_patterns) + 100
                })

        for case in self.error_db:
            matched_patterns = []

            for pattern in case["patterns"]:
                if re.search(pattern, log_text, re.IGNORECASE):
                    matched_patterns.append(pattern)

            if matched_patterns:
                results.append({
                    "source": "generic_error",
                    "id": case["id"],
                    "category": case["category"],
                    "name": case["name"],
                    "matched_patterns": matched_patterns,
                    "reason": case["reason"],
                    "solution": case["solution"],
                    "fix": case.get("fix"),
                    "score": len(matched_patterns)
                })

        results.sort(key=lambda item: item["score"], reverse=True)
        return results

    def _is_unsafe_related_command(self, command: str):
        return re.search(r"\brm\s+-[^\n;]*r[^\n;]*f\b", command, re.IGNORECASE)

    def _is_cluster_specific_directive(self, directive: str):
        return (
            "#SBATCH --partition" in directive
            or "#SBATCH --account" in directive
        )

    def _is_slurm_directive(self, directive: str):
        return directive.strip().startswith("#SBATCH")
    
    def format_results(self, results):
        if not results:
            return "没有匹配到已知错误。请提供更完整的日志，并检查是否包含 Error、Failed、Killed、Denied、OOM 等关键词。"

        lines = ["诊断结果："]

        for index, result in enumerate(results, 1):
            lines.append("")
            if result.get("source") == "real_case":
                lines.extend(self._format_real_case_result(index, result))
                continue

            lines.append(f"{index}. {result['name']}")
            lines.append(f"   类型: {result['category']}")
            lines.append(f"   匹配关键词: {', '.join(result['matched_patterns'])}")
            lines.append(f"   可能原因: {result['reason']}")
            lines.append(f"   解决方案: {result['solution']}")
            if result.get("fix"):
                fix = result["fix"]

                lines.append("   自动修复建议:")

                if fix.get("suggested_directives"):
                    safe_items = [
                        directive
                        for directive in fix["suggested_directives"]
                        if not self._is_cluster_specific_directive(directive)
                    ]
                    slurm_directives = [
                        item
                        for item in safe_items
                        if self._is_slurm_directive(item)
                    ]
                    environment_fixes = [
                        item
                        for item in safe_items
                        if not self._is_slurm_directive(item)
                    ]

                    if slurm_directives:
                        lines.append("     推荐 Slurm 参数/配置:")

                        for directive in slurm_directives:
                            lines.append(f"       - {directive}")

                    if environment_fixes:
                        lines.append("     推荐环境修复:")

                        for command in environment_fixes:
                            lines.append(f"       - {command}")

                    if len(safe_items) < len(fix["suggested_directives"]):
                        lines.append("     集群相关参数:")
                        lines.append("       - partition/account 需要以当前超算的 sinfo 或管理员说明为准，不要直接套用示例名称。")

                if fix.get("related_commands"):
                    safe_commands = [
                        command
                        for command in fix["related_commands"]
                        if not self._is_unsafe_related_command(command)
                    ]

                    if safe_commands:
                        lines.append("     推荐排查命令:")

                        for command in safe_commands:
                            lines.append(f"       - {command}")

                    if len(safe_commands) < len(fix["related_commands"]):
                        lines.append("     清理建议:")
                        lines.append("       - 检查并确认无用文件后再清理，避免直接执行危险删除命令。")

                if fix.get("explanation"):
                    lines.append(f"     修复说明: {fix['explanation']}")

        return "\n".join(lines)

    def _format_real_case_result(self, index: int, result: dict):
        lines = [
            f"{index}. 真实案例: {result['name']}",
            f"   类型: {result['category']}",
            f"   严重级别: {result.get('severity', 'warning')}",
            f"   匹配关键词: {', '.join(result['matched_patterns'])}",
        ]

        if result.get("evidence"):
            lines.append("   证据:")
            lines.extend(f"     - {item}" for item in result["evidence"])

        lines.append(f"   可能原因: {result['reason']}")

        if result.get("suggestions"):
            lines.append("   修复建议:")
            lines.extend(f"     - {item}" for item in result["suggestions"])

        safe_commands = [
            command
            for command in result.get("commands", [])
            if not self._is_unsafe_related_command(command)
        ]
        if safe_commands:
            lines.append("   推荐排查命令:")
            lines.extend(f"     - {command}" for command in safe_commands)

        if len(safe_commands) < len(result.get("commands", [])):
            lines.append("   清理建议:")
            lines.append("     - 检查并确认无用文件后再清理，避免直接执行危险删除命令。")

        if result.get("prevention"):
            lines.append(f"   下次避免: {result['prevention']}")

        return lines
    
    def _replace_or_add_directive(self, script: str, option: str, new_line: str):
        lines = script.splitlines()
        new_lines = []
        replaced = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("#SBATCH") and option in stripped:
                new_lines.append(new_line)
                replaced = True
            else:
                new_lines.append(line)

        if not replaced:
            insert_index = 1 if new_lines and new_lines[0].startswith("#!") else 0
            new_lines.insert(insert_index, new_line)

        return "\n".join(new_lines)
    
    def fix_sbatch_script(self, sbatch_script: str, results):
        if not results:
            return sbatch_script

        fixed_script = sbatch_script

        for result in results:
            error_id = result["id"]

            if error_id == "OOM_001":
                fixed_script = self._replace_or_add_directive(
                    fixed_script,
                    "--mem",
                    "#SBATCH --mem=16G"
                )

            elif error_id == "TIME_001":
                fixed_script = self._replace_or_add_directive(
                    fixed_script,
                    "--time",
                    "#SBATCH --time=04:00:00"
                )

            elif error_id == "TIME_002":
                fixed_script = self._replace_or_add_directive(
                    fixed_script,
                    "--time",
                    "#SBATCH --time=02:00:00"
                )

            elif error_id == "SLURM_001":
                fixed_script = self._replace_or_add_directive(
                    fixed_script,
                    "--partition",
                    "#SBATCH --partition=general"
                )

            elif error_id == "SLURM_004":
                fixed_script = self._replace_or_add_directive(
                    fixed_script,
                    "--nodes",
                    "#SBATCH --nodes=1"
                )
                fixed_script = self._replace_or_add_directive(
                    fixed_script,
                    "--cpus-per-task",
                    "#SBATCH --cpus-per-task=4"
                )

            elif error_id == "SLURM_005":
                fixed_script = self._replace_or_add_directive(
                    fixed_script,
                    "--time",
                    "#SBATCH --time=02:00:00"
                )

            elif error_id == "GPU_001":
                fixed_script = self._replace_or_add_directive(
                    fixed_script,
                    "--gres",
                    "#SBATCH --gres=gpu:1"
                )
                fixed_script = self._replace_or_add_directive(
                    fixed_script,
                    "--mem",
                    "#SBATCH --mem=32G"
                )

            elif error_id == "GPU_002":
                fixed_script = self._replace_or_add_directive(
                    fixed_script,
                    "--gres",
                    "#SBATCH --gres=gpu:1"
                )

                if "module load cuda" not in fixed_script:
                    fixed_script = fixed_script + "\nmodule load cuda\n"

        return fixed_script


if __name__ == "__main__":
    diagnoser = ErrorDiagnoser()

    test_log = """
    slurmstepd: error: Detected 1 oom-kill event
    Some of your processes may have been killed by the cgroup out-of-memory handler.
    """

    results = diagnoser.diagnose(test_log)
    print(diagnoser.format_results(results))

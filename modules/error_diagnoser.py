import json
import re
from pathlib import Path


class ErrorDiagnoser:
    def __init__(self, db_path: str = "data/errors/errors_db.json"):
        self.db_path = Path(db_path)
        self.error_db = self.load_error_db()

    def load_error_db(self):
        if not self.db_path.exists():
            raise FileNotFoundError(f"错误案例库不存在: {self.db_path}")

        with open(self.db_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def diagnose(self, log_text: str):
        results = []

        for case in self.error_db:
            matched_patterns = []

            for pattern in case["patterns"]:
                if re.search(pattern, log_text, re.IGNORECASE):
                    matched_patterns.append(pattern)

            if matched_patterns:
                results.append({
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

    def diagnose_file(self, log_file_path: str):
        path = Path(log_file_path)

        if not path.exists():
            return f"日志文件不存在: {path}"

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            log_text = f.read()

        return self.diagnose(log_text)
    
    def format_results(self, results):
        if not results:
            return "没有匹配到已知错误。请检查日志里是否有 Error、Failed、Killed、Denied、OOM 等关键词。"

        lines = ["诊断结果："]

        for index, result in enumerate(results, 1):
            lines.append("")
            lines.append(f"{index}. {result['name']}")
            lines.append(f"   类型: {result['category']}")
            lines.append(f"   匹配关键词: {', '.join(result['matched_patterns'])}")
            lines.append(f"   可能原因: {result['reason']}")
            lines.append(f"   解决方案: {result['solution']}")
            if result.get("fix"):
                fix = result["fix"]

                lines.append("   自动修复建议:")

                if fix.get("suggested_directives"):
                    lines.append("     推荐 Slurm 参数/配置:")

                    for directive in fix["suggested_directives"]:
                        lines.append(f"       - {directive}")

                if fix.get("related_commands"):
                    lines.append("     推荐排查命令:")

                    for command in fix["related_commands"]:
                        lines.append(f"       - {command}")

                if fix.get("explanation"):
                    lines.append(f"     修复说明: {fix['explanation']}")

        return "\n".join(lines)
    
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

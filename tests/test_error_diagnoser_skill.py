import _bootstrap  # noqa: F401

from modules.error_diagnoser import ErrorDiagnoser
from modules.router import detect_intent


def assert_contains(text: str, expected: str):
    if expected not in text:
        raise AssertionError(f"Expected to find {expected!r} in:\n{text}")


def assert_not_contains(text: str, unexpected: str):
    if unexpected in text:
        raise AssertionError(f"Did not expect to find {unexpected!r} in:\n{text}")


def diagnose_text(log_text: str):
    diagnoser = ErrorDiagnoser()
    return diagnoser.format_results(diagnoser.diagnose(log_text))


def test_oom_log_matches_skill_output():
    log = """
    slurmstepd: error: Detected 1 oom-kill event.
    Some processes may have been killed by the cgroup out-of-memory handler.
    """
    answer = diagnose_text(log)

    assert_contains(answer, "诊断结果：")
    assert_contains(answer, "Out of Memory")
    assert_contains(answer, "类型: memory")
    assert_contains(answer, "可能原因:")
    assert_contains(answer, "解决方案:")
    assert_contains(answer, "推荐排查命令:")


def test_python_module_not_found_log():
    log = "Traceback: ModuleNotFoundError: No module named torch"
    answer = diagnose_text(log)

    assert detect_intent(log) == "diagnose_error"
    assert_contains(answer, "Module Not Found")
    assert_contains(answer, "类型: python")
    assert_contains(answer, "推荐环境修复:")
    assert_contains(answer, "which python")
    assert_not_contains(answer, "推荐 Slurm 参数/配置:")


def test_invalid_partition_does_not_invent_cluster_name():
    log = "sbatch: error: Batch job submission failed: Invalid partition name specified"
    answer = diagnose_text(log)

    assert_contains(answer, "Invalid Partition")
    assert_contains(answer, "集群相关参数:")
    assert_contains(answer, "partition/account 需要以当前超算")
    assert_not_contains(answer, "#SBATCH --partition=general")
    assert_not_contains(answer, "#SBATCH --partition=gpu")


def test_disk_quota_does_not_recommend_rm_rf():
    log = "OSError: Disk quota exceeded"
    answer = diagnose_text(log)

    assert_contains(answer, "Disk Quota Exceeded")
    assert_contains(answer, "清理建议:")
    assert_not_contains(answer, "rm -rf")


def test_unknown_log_asks_for_more_complete_logs():
    answer = diagnose_text("the program stopped and I do not know why")

    assert_contains(answer, "没有匹配到已知错误")
    assert_contains(answer, "请提供更完整的日志")


if __name__ == "__main__":
    test_oom_log_matches_skill_output()
    test_python_module_not_found_log()
    test_invalid_partition_does_not_invent_cluster_name()
    test_disk_quota_does_not_recommend_rm_rf()
    test_unknown_log_asks_for_more_complete_logs()
    print("All error diagnoser skill checks passed.")

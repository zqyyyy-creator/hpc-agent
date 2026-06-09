def detect_intent(question: str) -> str:
    q = question.lower()
    q_no_space = q.replace(" ", "")

    error_keywords = [
        "error", "failed", "traceback", "exception",
        "报错", "错误日志", "运行失败", "提交失败",
        "permission denied", "out of memory", "oom",
        "time limit", "segmentation fault",
        "not found"
    ]

    sbatch_keywords = [
        "生成脚本", "写脚本", "写一个sbatch",
        "帮我写sbatch", "sbatch脚本",
        "作业脚本", "帮我生成",
        "提交一个", "提交作业",
        "createansbatch", "generateansbatch",
        "createsbatch", "generatesbatch",
        "sbatchscript", "slurmscript",
        "jobscript"
    ]

    param_keywords = [
        "参数建议", "资源建议",
        "多少内存", "多少cpu", "多少gpu",
        "需要几个节点", "需要多少资源",
        "cpus-per-task", "gres", "nodes", "ntasks"
    ]

    troubleshoot_keywords = [
        "一直不运行", "一直pending", "pending",
        "卡住", "没有开始", "排队很久"
    ]

    if any(k in q for k in error_keywords):
        return "diagnose_error"

    if any(k in q_no_space for k in sbatch_keywords):
        return "generate_sbatch"

    if any(k in q for k in troubleshoot_keywords):
        return "troubleshoot_job"

    if any(k in q_no_space for k in param_keywords):
        return "suggest_params"

    return "rag_qa"

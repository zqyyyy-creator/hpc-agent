def detect_intent(question: str) -> str:
    q = question.lower()
    q_no_space = q.replace(" ", "")
    has_job_id = any(char.isdigit() for char in q)

    error_keywords = [
        "error", "failed", "traceback", "exception",
        "报错", "错误日志", "运行失败", "提交失败",
        "permission denied", "out of memory", "oom",
        "time limit", "segmentation fault",
        "not found"
    ]

    submit_keywords = [
        "提交作业", "提交一个作业", "帮我提交",
        "提交到超算", "运行到超算",
        "submitjob", "submitasbatch", "submittohpc",
        "runonhpc"
    ]

    job_status_keywords = [
        "查看状态", "查询状态", "作业状态",
        "任务状态", "jobstatus", "checkjob",
        "squeue"
    ]

    job_output_keywords = [
        "读取输出", "查看输出", "标准输出",
        "输出结果", "stdout", "joboutput"
    ]

    job_error_keywords = [
        "读取错误日志", "查看错误日志", "错误日志",
        "stderr", "joberror"
    ]

    sbatch_keywords = [
        "生成脚本", "写脚本", "写一个sbatch",
        "帮我写sbatch", "sbatch脚本",
        "作业脚本", "帮我生成",
        "我想提交",
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

    if any(k in q_no_space for k in submit_keywords):
        return "submit_job"

    if has_job_id and "状态" in q:
        return "job_status"

    if has_job_id and "输出" in q:
        return "job_output"

    if has_job_id and "错误日志" in q:
        return "job_error"

    if any(k in q_no_space for k in job_status_keywords):
        return "job_status"

    if any(k in q_no_space for k in job_output_keywords):
        return "job_output"

    if any(k in q_no_space for k in job_error_keywords):
        return "job_error"

    if any(k in q for k in error_keywords):
        return "diagnose_error"

    if any(k in q_no_space for k in sbatch_keywords):
        return "generate_sbatch"

    if any(k in q for k in troubleshoot_keywords):
        return "troubleshoot_job"

    if any(k in q_no_space for k in param_keywords):
        return "suggest_params"

    return "rag_qa"

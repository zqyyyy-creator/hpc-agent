import re


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
        "提交一个", "提交任务", "提交并分析",
        "运行并分析",
        "跑到超算", "放到超算跑", "帮我跑",
        "帮我运行", "启动作业", "启动任务",
        "跑任务", "运行任务",
        "submitjob", "submitasbatch", "submittohpc",
        "runonhpc", "launchjob", "startjob"
    ]

    job_status_keywords = [
        "查看状态", "查询状态", "作业状态",
        "任务状态", "jobstatus", "checkjob",
        "算完没", "跑完没", "还在跑吗",
        "运行到哪", "进度怎么样", "现在怎么样",
        "squeue"
    ]

    job_output_keywords = [
        "读取输出", "查看输出", "标准输出",
        "输出结果", "看输出", "看看输出",
        "运行结果", "结果文件", "stdout", "joboutput"
    ]

    job_error_keywords = [
        "读取错误日志", "查看错误日志", "错误日志",
        "看错误", "看看错误", "失败日志",
        "报错日志", "stderr", "joberror"
    ]

    sbatch_keywords = [
        "生成脚本", "写脚本", "写一个sbatch",
        "帮我写sbatch", "sbatch脚本",
        "作业脚本", "帮我生成",
        "我想提交", "先生成脚本", "只生成脚本",
        "给我脚本", "预览脚本",
        "createansbatch", "generateansbatch",
        "createsbatch", "generatesbatch",
        "sbatchscript", "slurmscript",
        "jobscript"
    ]

    vasp_keywords = [
        "vasp", "incar", "poscar", "potcar", "kpoints",
        "outcar", "oszicar", "contcar", "vasprun.xml",
        "vasp_std", "vasp_gam", "vasp_ncl",
        "结构优化", "静态计算", "能带", "态密度",
        "第一性原理", "dft", "材料计算", "赝势",
        "自洽", "非自洽", "弛豫", "几何优化"
    ]

    param_keywords = [
        "参数建议", "资源建议",
        "多少内存", "多少cpu", "多少gpu",
        "需要几个节点", "需要多少资源",
        "怎么申请资源", "资源怎么填",
        "该用多少核", "申请多少核", "申请多久",
        "跑多久", "用多少核",
        "cpus-per-task", "gres", "nodes", "ntasks"
    ]

    troubleshoot_keywords = [
        "一直不运行", "一直pending", "pending",
        "卡住", "没有开始", "排队很久",
        "为什么不跑", "为什么没开始",
        "一直排队", "没动静", "没反应"
    ]

    list_remote_job_keywords = [
        "列出任务编号", "列出作业编号",
        "查看任务编号", "查看作业编号",
        "有哪些任务编号", "有哪些作业编号",
        "远端任务编号", "远端作业编号",
        "远程任务编号", "远程作业编号",
        "列一下远端作业", "远端有哪些作业",
        "远端目录有什么", "远端有什么任务",
        "hpc-agent-jobs", "hpcagentjobs",
        "listjobs", "listremotejobs",
    ]

    cleanup_keywords = [
        "清理", "删除", "移除", "cleanup", "clean",
        "remove", "delete", "删掉", "删一下",
        "清掉", "清空", "释放空间",
    ]
    cleanup_all_keywords = [
        "全部", "所有", "一键", "清空", "全部清理",
        "清理全部", "所有作业", "all",
    ]

    is_vasp_request = any(k in q_no_space for k in vasp_keywords)

    if is_vasp_request and any(k in q_no_space for k in list_remote_job_keywords + ["列出", "查看", "有哪些", "有什么"]):
        return "list_remote_vasp_jobs"

    if is_vasp_request and any(k in q_no_space for k in cleanup_keywords):
        if any(k in q_no_space for k in cleanup_all_keywords):
            return "cleanup_all_remote_vasp_jobs"

        if has_job_id or "作业名" in q_no_space or "目录名" in q_no_space or "job" in q_no_space:
            return "cleanup_remote_vasp_job"

        return "cleanup_remote_vasp_job"

    if any(k in q_no_space for k in cleanup_keywords):
        if any(k in q_no_space for k in cleanup_all_keywords):
            return "cleanup_all_remote_jobs"

        if has_job_id:
            return "cleanup_remote_job"

    if any(k in q_no_space for k in list_remote_job_keywords):
        return "list_remote_jobs"
    register_vasp_job_keywords = [
        "登记vasp作业", "记录vasp作业",
        "注册vasp作业", "关联vasp作业",
        "导入vasp作业", "把vasp作业记下来",
        "绑定vasp作业",
        "registervaspjob"
    ]
    register_vasp_loose_keywords = [
        "登记", "记录", "注册", "关联", "绑定",
        "导入", "记下来", "保存记录",
    ]
    vasp_report_keywords = [
        "报告", "分析报告", "论文报告",
        "生成报告", "生成分析", "生成论文",
        "写报告", "整理报告", "论文格式",
        "methods", "results", "方法部分", "结果部分",
        "report", "analysisreport",
    ]
    analyze_vasp_keywords = [
        "一键分析", "完整分析", "分析vasp作业",
        "分析vasp任务", "分析vasp计算",
        "帮我分析", "自动分析", "跑完分析",
        "运行并分析", "提交并分析",
        "analyzevasp", "analysevasp",
    ]
    sync_vasp_action_keywords = ["同步", "拉取", "下载", "拿回", "取回", "拷回", "sync", "fetch"]
    sync_vasp_target_keywords = ["输出", "结果", "文件", "output", "result"]

    if (
        is_vasp_request
        and has_job_id
        and any(k in q_no_space for k in sync_vasp_action_keywords)
        and any(k in q_no_space for k in sync_vasp_target_keywords)
    ):
        return "sync_vasp_output"

    if is_vasp_request and (
        any(k in q_no_space for k in register_vasp_job_keywords)
        or (has_job_id and any(k in q_no_space for k in register_vasp_loose_keywords))
    ):
        return "register_vasp_job"

    if is_vasp_request and any(k in q_no_space for k in vasp_report_keywords):
        return "generate_vasp_report"

    if is_vasp_request and any(k in q_no_space for k in submit_keywords):
        return "submit_vasp_job"

    if is_vasp_request and any(k in q_no_space for k in analyze_vasp_keywords):
        return "analyze_vasp_job"

    if is_vasp_request and any(k in q_no_space for k in sbatch_keywords):
        return "generate_vasp_job"

    if is_vasp_request:
        return "generate_vasp_job"

    explicit_sbatch_keywords = [
        keyword for keyword in sbatch_keywords
        if keyword != "我想提交"
    ]

    if any(k in q_no_space for k in explicit_sbatch_keywords):
        return "generate_sbatch"

    file_run_pattern = r"(跑|运行|执行|提交|submit|run).{0,40}[A-Za-z0-9_./~-]+\.(py|sh|slurm|sbatch)"
    file_run_pattern_reversed = r"[A-Za-z0-9_./~-]+\.(py|sh|slurm|sbatch).{0,40}(跑|运行|执行|提交|submit|run)"

    if re.search(file_run_pattern, q_no_space) or re.search(file_run_pattern_reversed, q_no_space):
        return "submit_job"

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

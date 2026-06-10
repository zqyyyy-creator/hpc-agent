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

    vasp_keywords = [
        "vasp", "incar", "poscar", "potcar", "kpoints",
        "outcar", "oszicar", "contcar", "vasprun.xml",
        "vasp_std", "vasp_gam", "vasp_ncl",
        "结构优化", "静态计算", "能带", "态密度"
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

    list_remote_job_keywords = [
        "列出任务编号", "列出作业编号",
        "查看任务编号", "查看作业编号",
        "有哪些任务编号", "有哪些作业编号",
        "远端任务编号", "远端作业编号",
        "远程任务编号", "远程作业编号",
        "hpc-agent-jobs", "hpcagentjobs",
        "listjobs", "listremotejobs",
    ]

    cleanup_keywords = [
        "清理", "删除", "移除", "cleanup", "clean",
        "remove", "delete",
    ]
    cleanup_all_keywords = [
        "全部", "所有", "一键", "清空", "全部清理",
        "清理全部", "所有作业", "all",
    ]

    if any(k in q_no_space for k in cleanup_keywords):
        if any(k in q_no_space for k in cleanup_all_keywords):
            return "cleanup_all_remote_jobs"

        if has_job_id:
            return "cleanup_remote_job"

    if any(k in q_no_space for k in list_remote_job_keywords):
        return "list_remote_jobs"

    is_vasp_request = any(k in q_no_space for k in vasp_keywords)
    create_vasp_input_keywords = [
        "生成vasp输入文件", "创建vasp输入文件",
        "写入vasp输入文件", "保存vasp输入文件",
        "生成四个文件", "创建四个文件",
        "写这四个文件", "保存这四个文件",
        "createvaspinputs", "writevaspinputs",
        "savevaspinputs"
    ]
    import_vasp_input_keywords = [
        "导入vasp输入文件", "从目录导入",
        "导入四个文件", "复制vasp输入文件",
        "importvaspinputs"
    ]
    assist_vasp_input_keywords = [
        "辅助生成vasp输入文件", "agent辅助生成",
        "自动生成vasp输入模板", "生成vasp模板",
        "生成incar", "生成kpoints",
        "generatevasptemplate"
    ]
    register_vasp_job_keywords = [
        "登记vasp作业", "记录vasp作业",
        "注册vasp作业", "关联vasp作业",
        "registervaspjob"
    ]

    if is_vasp_request and any(k in q_no_space for k in register_vasp_job_keywords):
        return "register_vasp_job"

    if is_vasp_request and any(k in q_no_space for k in import_vasp_input_keywords):
        return "import_vasp_inputs"

    if is_vasp_request and any(k in q_no_space for k in assist_vasp_input_keywords):
        return "assist_vasp_inputs"

    if is_vasp_request and any(k in q_no_space for k in create_vasp_input_keywords):
        return "create_vasp_inputs"

    if is_vasp_request and any(k in q_no_space for k in submit_keywords):
        return "submit_vasp_job"

    if is_vasp_request and any(k in q_no_space for k in sbatch_keywords):
        return "generate_vasp_job"

    if is_vasp_request:
        return "generate_vasp_job"

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

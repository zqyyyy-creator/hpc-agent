import re
from dataclasses import dataclass, field
from typing import Callable

from modules.slurm.hpc_test_files import is_test_file_request


@dataclass
class RouteDecision:
    intent: str
    risk: str
    reason: str
    matched_keywords: list[str] = field(default_factory=list)
    skipped_rules: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification: str | None = None


@dataclass
class RoutePlanStep:
    index: int
    text: str
    route_text: str
    intent: str
    risk: str
    condition: str | None = None
    needs_clarification: bool = False
    clarification: str | None = None


@dataclass
class RoutePlan:
    steps: list[RoutePlanStep]
    is_conditional: bool = False
    risk: str = "none"


@dataclass(frozen=True)
class RouteContext:
    question: str
    q: str
    q_no_space: str
    q_normalized: str
    has_job_id: bool
    is_howto_or_concept: bool
    is_vasp_request: bool
    negated_vasp: bool
    negated_cleanup: bool
    negated_submit: bool

    def match_any(self, keywords: list[str] | tuple[str, ...]) -> bool:
        return _match_any(keywords, self.q_no_space, self.q_normalized)

    def raw_match_any(self, keywords: list[str] | tuple[str, ...]) -> bool:
        return any(keyword in self.q_no_space for keyword in keywords)


@dataclass(frozen=True)
class RouteRule:
    name: str
    intent: str
    predicate: Callable[[RouteContext], bool]


# Chinese particles / quantifiers / modal markers that frequently appear
# between verbs and objects and break substring keyword matching.
_NORMALIZE_PARTICLES = [
    "一下", "一个", "个", "下", "吗", "呢", "吧", "啊", "呀", "哦", "嘛", "咯",
    "能不能", "可以不可以",
]


KEYWORDS: dict[str, list[str]] = {
    "error": [
        "error", "failed", "traceback", "exception",
        "报错", "错误日志", "运行失败", "提交失败",
        "permission denied", "out of memory", "oom",
        "time limit", "segmentation fault", "not found",
    ],
    "prepare_error_case": [
        "把这个错误整理成案例", "把这个报错整理成案例",
        "生成案例草稿", "加入错误案例库", "添加到错误案例库",
        "收录错误", "收录这个错误", "整理成错误案例",
        "整理成案例", "errorcase", "add error case",
    ],
    "shortcut_help": [
        "/help", "help", "帮助", "快捷命令", "命令帮助",
        "slashcommand", "slashcommands",
    ],
    "project_doctor": [
        "/doctor", "doctor", "总体体检", "项目体检",
        "系统体检", "健康检查", "项目健康检查",
        "检查整个项目", "检查agent", "检查 agent",
        "agent doctor", "health check", "project doctor",
    ],
    "local_resources": [
        "检查本机可用资源", "查看本机可用资源", "本机可用资源",
        "检查本地资源", "查看本地资源", "本地资源",
        "当前机器", "当前环境", "当前系统",
        "可用资源", "系统资源", "检测资源", "检查资源",
        "本机有多少cpu", "本机有多少gpu", "有没有gpu", "有没有 gpu",
        "available resources", "local resources", "check resources",
        "detect resources", "system resources",
        "availableresources", "localresources", "checkresources",
        "detectresources", "detectavailableresources", "systemresources",
    ],
    "submit": [
        "提交作业", "提交到超算", "运行到超算",
        "提交任务", "提交并分析", "运行并分析",
        "跑到超算", "放到超算跑",
        "启动作业", "启动任务",
        "提交脚本", "提交文件", "提交程序",
        "帮我提交", "帮我跑", "帮我运行",
        "跑任务", "运行任务", "运行脚本", "跑脚本", "跑程序",
        "提交任务", "提交作业", "提交",
        "submitjob", "submitasbatch", "submittohpc",
        "runonhpc", "launchjob", "startjob",
    ],
    "job_status": [
        "查看状态", "查询状态", "作业状态", "任务状态",
        "查看作业", "查询作业", "看看作业",
        "算完没", "跑完没", "还在跑吗",
        "运行到哪", "进度怎么样", "现在怎么样",
        "查状态", "查作业", "看状态", "看作业", "看怎么样",
        "查进度", "看进度",
        "jobstatus", "checkjob", "squeue",
    ],
    "recent_jobs": [
        "查看最近作业", "列出最近作业", "最近作业",
        "我的最近作业", "查看我的作业", "列出我的作业",
        "最近提交的作业", "最近跑的作业",
    ],
    "job_record_status": [
        "查看本地作业记录状态", "本地作业记录状态",
        "查看jobregistry状态", "jobregistry状态",
        "本地记录有多少作业", "本地作业记录有多少",
        "查看本地记录状态", "本地记录状态",
    ],
    "preview_archive_job_records": [
        "预览归档本地作业记录", "预览归档作业记录",
        "归档本地作业记录预览", "本地作业记录归档预览",
        "只保留最近", "保留最近",
    ],
    "list_job_record_archives": [
        "查看本地作业记录归档", "列出本地作业记录归档",
        "查看归档文件", "列出归档文件", "本地归档有哪些",
        "查看jobregistry归档", "jobregistry归档",
        "查看归档记录", "列出归档记录", "归档记录",
        "查看作业归档", "列出作业归档", "作业归档",
        "有哪些归档记录", "归档有哪些",
    ],
    "preview_restore_job_records": [
        "预览恢复本地作业记录归档", "恢复本地作业记录归档预览",
        "预览恢复归档文件", "恢复最近一次本地作业记录归档",
        "预览恢复最近一次", "恢复归档记录",
        "预览恢复归档记录", "恢复作业归档",
        "恢复本地归档", "恢复最近归档", "恢复最近一次归档",
    ],
    "job_detail": [
        "查看作业详情", "作业详情", "任务详情",
        "查看任务详情", "详情", "详细信息",
        "这个作业详情", "那个作业详情",
    ],
    "list_local_vasp_jobs": [
        "列出vasp作业", "查看vasp作业", "我的vasp作业",
        "本地vasp作业", "列出本地vasp作业",
        "已经记录的vasp作业", "vasp作业列表",
    ],
    "job_output": [
        "读取输出", "查看输出", "标准输出",
        "输出结果", "看输出", "看看输出",
        "运行结果", "结果文件",
        "看结果", "查输出", "查结果", "读输出", "读结果",
        "查看结果", "读取结果",
        "作业输出", "作业结果",
        "stdout", "joboutput",
    ],
    "job_error": [
        "读取错误日志", "查看错误日志", "错误日志",
        "看错误", "看看错误", "失败日志", "报错日志",
        "看报错", "查错误", "查报错", "读错误", "读取错误",
        "stderr", "joberror",
    ],
    "diagnose_job": [
        "诊断作业", "诊断任务", "诊断这个作业", "诊断那个作业",
        "帮我诊断作业", "帮我诊断任务", "排查作业", "排查任务",
        "分析作业失败", "分析任务失败", "诊断", "排查", "diagnosejob",
    ],
    "sbatch": [
        "生成脚本", "写脚本", "写一个sbatch",
        "帮我写sbatch", "sbatch脚本",
        "作业脚本", "帮我生成",
        "我想提交", "先生成脚本", "只生成脚本",
        "给我脚本", "预览脚本",
        "写sbatch", "生成sbatch", "创建脚本", "创建sbatch",
        "帮我写", "给写", "给生成",
        "createansbatch", "generateansbatch",
        "createsbatch", "generatesbatch",
        "sbatchscript", "slurmscript", "jobscript",
    ],
    "vasp": [
        "vasp", "incar", "poscar", "potcar", "kpoints",
        "outcar", "oszicar", "contcar", "vasprun.xml",
        "vasp_std", "vasp_gam", "vasp_ncl",
        "结构优化", "静态计算", "能带", "态密度",
        "第一性原理", "dft", "材料计算", "赝势",
        "自洽", "非自洽", "弛豫", "几何优化",
    ],
    "params": [
        "参数建议", "资源建议",
        "多少内存", "多少cpu", "多少gpu",
        "需要几个节点", "需要多少资源",
        "怎么申请资源", "资源怎么填",
        "该用多少核", "申请多少核", "申请多久",
        "跑多久", "用多少核",
        "推荐参数", "建议参数", "推荐资源", "建议资源",
        "参数怎么填", "需要多少核", "需要多少内存",
        "推荐sbatch", "建议sbatch", "看看需要",
        "cpus-per-task", "gres", "nodes", "ntasks",
    ],
    "current_config": [
        "查看当前模型", "当前模型", "查看模型", "模型配置",
        "查看当前配置", "当前配置", "查看环境配置", "当前环境",
    ],
    "hpc_config_check": [
        "检查我的超算配置", "检查超算配置", "超算配置体检",
        "配置体检", "检查环境配置", "检查hpc配置", "检查ssh配置",
    ],
    "hpc_submission_test": [
        "一键测试超算提交流程", "测试超算提交流程", "测试提交作业流程",
        "测试提交流程", "测试超算能不能提交作业", "测试这个超算能不能正常提交作业",
        "一键测试提交", "一键最小验证流程",
    ],
    "troubleshoot": [
        "一直不运行", "一直pending", "pending",
        "卡住", "没有开始", "排队很久",
        "为什么不跑", "为什么没开始",
        "一直排队", "没动静", "没反应",
        "排查", "排查作业", "为什么不运行", "为什么卡住",
        "不运行", "看pending",
    ],
    "list_remote_job": [
        "列出任务编号", "列出作业编号",
        "查看任务编号", "查看作业编号",
        "有哪些任务编号", "有哪些作业编号",
        "远端任务编号", "远端作业编号",
        "远程任务编号", "远程作业编号",
        "列一下远端作业", "远端有哪些作业",
        "远端目录有什么", "远端有什么任务",
        "列远端", "看远端", "远端作业", "有哪些作业",
        "远端有啥", "远端有什么",
        "hpc-agent-jobs", "hpcagentjobs",
        "listjobs", "listremotejobs",
    ],
    "cleanup": [
        "清理", "删除", "移除", "cleanup", "clean",
        "remove", "delete", "删掉", "删一下",
        "清掉", "清空", "释放空间", "清理远程",
    ],
    "cleanup_all": [
        "全部", "所有", "一键", "清空", "全部清理",
        "清理全部", "所有作业", "all",
    ],
    "last_job_reference": [
        "刚才", "上一个", "上个", "最近", "它", "这个作业", "那个作业",
        "刚提交", "刚运行", "上次", "last", "previous",
        "前一个", "前面一个", "之前那个", "之前的作业", "之前",
    ],
    "sequential_markers": ["先", "然后", "再", "接着", "随后", "最后"],
    "conditional_markers": ["如果", "若", "跑完", "完成后", "结束后", "成功后"],
    "register_vasp": [
        "登记vasp作业", "记录vasp作业", "注册vasp作业", "关联vasp作业",
        "导入vasp作业", "把vasp作业记下来", "绑定vasp作业",
        "registervaspjob",
    ],
    "register_vasp_loose": [
        "登记", "记录", "注册", "关联", "绑定",
        "导入", "记下来", "保存记录",
    ],
    "vasp_report": [
        "报告", "分析报告", "论文报告",
        "生成报告", "生成分析", "生成论文",
        "写报告", "整理报告", "论文格式",
        "methods", "results", "方法部分", "结果部分",
        "report", "analysisreport",
    ],
    "vasp_input_generation": [
        "配置文件", "输入文件", "生成incar", "生成poscar", "生成kpoints",
        "生成其他三个文件", "生成其它三个文件", "生成三个文件",
        "生成vasp输入", "生成vasp配置",
    ],
    "analyze_vasp": [
        "一键分析", "完整分析", "分析vasp作业",
        "分析vasp任务", "分析vasp计算",
        "帮我分析", "自动分析", "跑完分析",
        "运行并分析", "提交并分析",
        "analyzevasp", "analysevasp",
    ],
    "sync_vasp_action": ["同步", "拉取", "下载", "拿回", "取回", "拷回", "sync", "fetch"],
    "sync_vasp_target": ["输出", "结果", "文件", "output", "result"],
    "howto_or_concept": [
        "怎么", "如何", "怎样", "为什么", "为啥",
        "是什么", "什么意思", "啥意思", "区别", "介绍",
        "教程", "说明", "文档",
    ],
    "negated_vasp": ["不是vasp", "非vasp", "不要vasp"],
    "negated_cleanup": ["不要清理", "别清理", "不要删除", "别删除", "不要删", "别删"],
    "negated_submit": ["不要提交", "别提交", "不要运行", "别运行", "不要跑", "别跑"],
}


EXPLANATION_KEYWORDS: dict[str, list[str]] = {
    "project_doctor": ["总体体检", "项目体检", "健康检查", "doctor"],
    "suggest_params": ["资源怎么填", "申请多少核", "需要多少核", "需要多少资源", "多少内存"],
    "check_local_resources": ["本机资源", "本地资源", "当前机器", "当前环境", "available resources"],
    "current_config": ["当前模型", "当前配置", "模型配置"],
    "check_hpc_config": ["检查", "配置", "超算"],
    "test_hpc_submission": ["测试", "提交", "超算"],
    "troubleshoot_job": ["pending", "为什么没开始", "一直不运行", "卡住", "没有开始"],
    "generate_sbatch": ["生成脚本", "写脚本", "sbatch", "只生成脚本"],
    "submit_job": ["提交", "运行", "跑到超算", ".py", ".sh"],
    "submit_vasp_job": ["提交", "运行", "vasp", "第一性原理", "dft"],
    "generate_vasp_job": ["vasp", "dft", "结构优化", "弛豫", "生成脚本"],
    "generate_vasp_inputs": ["vasp", "potcar", "incar", "poscar", "kpoints", "配置文件"],
    "generate_test_file": ["测试", "sleep", "hostname", "mpirun", "srun"],
    "job_status": ["状态", "算完没", "跑完没", "进度", "刚才"],
    "recent_jobs": ["最近作业", "我的作业", "最近提交"],
    "job_record_status": ["本地作业记录", "jobregistry", "本地记录"],
    "preview_archive_job_records": ["预览", "归档", "保留最近"],
    "list_job_record_archives": ["归档", "归档文件"],
    "preview_restore_job_records": ["预览", "恢复", "归档"],
    "job_detail": ["详情", "详细信息", "作业详情"],
    "list_local_vasp_jobs": ["vasp", "本地", "记录", "列表"],
    "job_output": ["输出", "结果", "stdout", "它"],
    "job_error": ["错误日志", "报错", "stderr"],
    "cleanup_remote_job": ["清理", "删除", "删掉"],
    "cleanup_all_remote_jobs": ["清理", "全部", "所有"],
    "cleanup_remote_vasp_job": ["vasp", "清理", "删除", "input", "output"],
    "cleanup_all_remote_vasp_jobs": ["vasp", "清理", "全部", "所有", "input", "output"],
    "list_remote_jobs": ["列", "远端", "作业"],
    "list_remote_vasp_jobs": ["vasp", "远端", "目录"],
    "register_vasp_job": ["登记", "记录", "注册", "记下来"],
    "sync_vasp_output": ["同步", "拉取", "拿回", "结果", "输出"],
    "generate_vasp_report": ["报告", "论文格式", "methods", "results"],
    "analyze_vasp_job": ["分析", "一键分析", "自动分析"],
    "diagnose_error": ["error", "failed", "traceback", "报错", "oom"],
    "prepare_error_case": ["错误案例", "案例草稿", "加入错误案例库"],
    "diagnose_job": ["诊断", "排查", "作业", "任务"],
    "clarify": ["缺少文件/命令/job_id"],
    "rag_qa": ["fallback"],
}


INTENT_RISKS = {
    "rag_qa": "none",
    "clarify": "clarify_required",
    "shortcut_help": "read_only",
    "project_doctor": "read_only",
    "suggest_params": "none",
    "check_local_resources": "read_only",
    "current_config": "read_only",
    "check_hpc_config": "read_only",
    "test_hpc_submission": "confirm_required",
    "diagnose_error": "read_only",
    "prepare_error_case": "confirm_required",
    "diagnose_job": "read_only",
    "troubleshoot_job": "read_only",
    "job_status": "read_only",
    "job_output": "read_only",
    "job_error": "read_only",
    "recent_jobs": "read_only",
    "job_record_status": "read_only",
    "preview_archive_job_records": "read_only",
    "list_job_record_archives": "read_only",
    "preview_restore_job_records": "read_only",
    "job_detail": "read_only",
    "list_local_vasp_jobs": "read_only",
    "list_remote_jobs": "read_only",
    "list_remote_vasp_jobs": "read_only",
    "generate_sbatch": "generate_only",
    "generate_test_file": "generate_or_confirm_required",
    "generate_vasp_job": "generate_only",
    "generate_vasp_inputs": "generate_only",
    "generate_vasp_report": "read_only",
    "analyze_vasp_job": "read_only",
    "register_vasp_job": "read_only",
    "sync_vasp_output": "read_only",
    "submit_job": "confirm_required",
    "submit_vasp_job": "confirm_required",
    "cleanup_remote_job": "destructive_confirm_required",
    "cleanup_all_remote_jobs": "destructive_confirm_required",
    "cleanup_remote_vasp_job": "destructive_confirm_required",
    "cleanup_all_remote_vasp_jobs": "destructive_confirm_required",
}


def _normalize_chinese(text: str) -> str:
    for particle in _NORMALIZE_PARTICLES:
        text = text.replace(particle, "")
    return text


def _match_any(keywords, q_no_space, q_normalized):
    return any(kw in q_no_space or kw in q_normalized for kw in keywords)


def _is_howto_or_concept_question(q_no_space: str) -> bool:
    return any(marker in q_no_space for marker in KEYWORDS["howto_or_concept"])


def _is_negated_vasp_request(q_no_space: str) -> bool:
    return any(marker in q_no_space for marker in KEYWORDS["negated_vasp"])


def _has_negated_cleanup(q_no_space: str) -> bool:
    return any(marker in q_no_space for marker in KEYWORDS["negated_cleanup"])


def _has_negated_submit(q_no_space: str) -> bool:
    return any(marker in q_no_space for marker in KEYWORDS["negated_submit"])


def expand_shortcut_command(question: str) -> str:
    text = question.strip()
    if not text.startswith("/"):
        return question

    parts = text.split()
    command = parts[0].lower()
    args = parts[1:]

    if command == "/help":
        return question

    if command == "/model":
        return "查看当前模型"

    if command == "/resources":
        return "检查本机可用资源"

    if command == "/doctor":
        return "总体体检"

    if command == "/config":
        if args and args[0].lower() == "check":
            return "检查我的超算配置"
        return "查看当前模型"

    if command == "/job":
        subcommand = args[0].lower() if args else ""
        value = args[1] if len(args) > 1 else ""
        if subcommand == "recent":
            return "查看最近作业"
        if subcommand == "status" and value:
            return f"查看 {value} 的状态"
        if subcommand == "out" and value:
            return f"读取 {value} 的输出"
        if subcommand == "err" and value:
            return f"读取 {value} 的错误日志"
        if subcommand == "detail" and value:
            return f"查看作业详情 {value}"
        if subcommand == "diagnose" and value:
            return f"诊断作业 {value}"
        if subcommand == "monitor" and value:
            return f"监控 {value}"
        if subcommand in {"stop-monitor", "unmonitor", "cancel-monitor"} and value:
            return f"取消监控 {value}"
        if subcommand == "records":
            return "查看本地作业记录状态"
        if subcommand == "archive":
            keep_count = _extract_keep_count_arg(args[1:])
            if keep_count:
                return f"预览归档本地作业记录，只保留最近 {keep_count} 个"
        if subcommand == "archives":
            return "查看归档记录"
        if subcommand == "restore":
            return "预览恢复最近一次本地作业记录归档"

    if command == "/vasp":
        subcommand = args[0].lower() if args else ""
        value = args[1] if len(args) > 1 else ""
        if subcommand in {"list", "jobs"}:
            return "列出 VASP 作业"
        if subcommand in {"gen", "inputs"} and value:
            extra = " ".join(args[2:])
            suffix = f"，参数 {extra}" if extra else ""
            return f"帮我生成我的 VASP 作业 {value} 的配置文件{suffix}"
        if subcommand == "submit" and value:
            return f"帮我提交 VASP 作业 {value}"
        if subcommand == "sync" and value:
            return f"同步 VASP 作业 {value} 输出到本地"
        if subcommand == "analyze" and value:
            return f"帮我分析 VASP 作业 {value}"
        if subcommand == "report" and value:
            return f"生成 VASP 作业 {value} 报告"
        if subcommand == "remote":
            return "远端 VASP 目录有什么"
        if subcommand == "clean" and value:
            return f"清理远端 VASP 作业 {value} 的文件"

    if command == "/clean":
        subcommand = args[0].lower() if args else ""
        value = args[1] if len(args) > 1 else ""
        if subcommand == "job" and value:
            return f"清理远端作业 {value} 的文件"
        if subcommand == "jobs":
            return "清理远端普通作业目录下所有作业文件"
        if subcommand == "vasp-all":
            return "清理全部远端 VASP 作业文件"
        if subcommand == "vasp" and value:
            return f"清理远端 VASP 作业 {value} 的文件"

    return question


def _extract_keep_count_arg(args: list[str]) -> str | None:
    for index, arg in enumerate(args):
        if arg.startswith("--keep="):
            return arg.split("=", 1)[1]
        if arg == "--keep" and index + 1 < len(args):
            return args[index + 1]
    return None


def _looks_like_clarify_request(q_no_space: str, q_normalized: str) -> str | None:
    if q_normalized in {"帮我跑", "跑", "运行", "提交", "提交这个", "提交这", "运行这个", "运行这", "跑这个", "跑这"}:
        return "你想提交哪个文件或运行哪条命令？请补充文件路径、命令和资源需求。"

    if q_normalized in {"看结果", "看看结果", "看输出", "看看输出", "查结果", "查输出"}:
        return "你想查看哪个 Job ID 的输出？也可以先提交/登记作业后说“刚才那个”。"

    if q_normalized in {"看状态", "查状态", "查看状态", "查询状态", "看作业", "查作业"}:
        return "你想查看哪个 Job ID 的状态？也可以先提交/登记作业后再说“刚才那个”。"

    return None


def _build_context(question: str) -> RouteContext:
    question = expand_shortcut_command(question)
    q = question.lower()
    q_no_space = q.replace(" ", "")
    q_normalized = _normalize_chinese(q_no_space)
    negated_vasp = _is_negated_vasp_request(q_no_space)

    return RouteContext(
        question=question,
        q=q,
        q_no_space=q_no_space,
        q_normalized=q_normalized,
        has_job_id=any(char.isdigit() for char in q),
        is_howto_or_concept=_is_howto_or_concept_question(q_no_space),
        is_vasp_request=_match_any(KEYWORDS["vasp"], q_no_space, q_normalized) and not negated_vasp,
        negated_vasp=negated_vasp,
        negated_cleanup=_has_negated_cleanup(q_no_space),
        negated_submit=_has_negated_submit(q_no_space),
    )


def _file_submit_request(ctx: RouteContext) -> bool:
    if _explicit_sbatch_request(ctx) or _preview_only_submit_request(ctx):
        return False

    file_run_pattern = r"(跑|运行|执行|提交|submit|run).{0,40}[A-Za-z0-9_./~-]+\.(py|sh|slurm|sbatch)"
    file_run_pattern_reversed = r"[A-Za-z0-9_./~-]+\.(py|sh|slurm|sbatch).{0,40}(跑|运行|执行|提交|submit|run)"
    return bool(
        re.search(file_run_pattern, ctx.q_no_space)
        or re.search(file_run_pattern_reversed, ctx.q_no_space)
    )


def _explicit_sbatch_request(ctx: RouteContext) -> bool:
    return ctx.match_any([kw for kw in KEYWORDS["sbatch"] if kw != "我想提交"])


def _explicit_vasp_job_generation_request(ctx: RouteContext) -> bool:
    if not ctx.is_vasp_request:
        return False

    generation_markers = [
        "生成", "写", "创建", "预览",
        "帮我生成", "帮我写", "给我", "给我一个",
        "只生成", "先生成",
    ]
    script_markers = [
        "脚本", "运行脚本", "作业脚本", "sbatch", "slurm",
    ]
    return ctx.match_any(generation_markers) and ctx.match_any(script_markers)


def _preview_only_submit_request(ctx: RouteContext) -> bool:
    if not ctx.match_any(KEYWORDS["submit"]):
        return False

    return any(
        marker in ctx.q_no_space
        for marker in (
            "先别运行", "先不要运行", "别运行", "不要运行",
            "先别跑", "先不要跑", "别跑", "不要跑",
            "只生成脚本", "只预览", "先预览",
            "不要真的提交", "别真的提交",
        )
    )


def _local_resource_check_request(ctx: RouteContext) -> bool:
    if not ctx.match_any(KEYWORDS["local_resources"]):
        return False

    remote_terms = [
        "超算", "远端", "远程", "hpc", "slurm", "sinfo",
        "partition", "队列", "分区", "节点",
        "bscc-a", "amd_test", "amd_256",
    ]
    return not ctx.match_any(remote_terms)


def _job_id_status_request(ctx: RouteContext) -> bool:
    return ctx.has_job_id and "状态" in ctx.q


def _job_id_output_request(ctx: RouteContext) -> bool:
    return ctx.has_job_id and "输出" in ctx.q


def _job_id_error_request(ctx: RouteContext) -> bool:
    return ctx.has_job_id and "错误日志" in ctx.q


def _last_job_reference(ctx: RouteContext) -> bool:
    return ctx.raw_match_any(KEYWORDS["last_job_reference"])


def _local_vasp_job_list_request(ctx: RouteContext) -> bool:
    if not ctx.is_vasp_request:
        return False
    if ctx.match_any(["远端", "远程", "hpc", "input", "output"]):
        return False
    if ctx.match_any(KEYWORDS["vasp_input_generation"] + KEYWORDS["submit"] + KEYWORDS["sbatch"]):
        return False
    return ctx.match_any(KEYWORDS["list_local_vasp_jobs"]) and ctx.match_any(["列出", "查看", "看看", "有哪些", "列表"])


def _generic_vasp_directory_cleanup_request(ctx: RouteContext) -> bool:
    if not (ctx.is_vasp_request and ctx.match_any(KEYWORDS["cleanup"])):
        return False

    if ctx.has_job_id:
        return False

    if any(marker in ctx.q_no_space for marker in ("目录名", "作业名", "jobname")):
        return False

    return any(
        marker in ctx.q_no_space
        for marker in (
            "远端vasp作业目录",
            "清理远端vasp作业目录",
            "删除远端vasp作业目录",
            "vasp作业目录",
        )
    )


def _vasp_input_generation_request(ctx: RouteContext) -> bool:
    if not ctx.is_vasp_request:
        return False
    if ctx.match_any(KEYWORDS["vasp_input_generation"]):
        return True
    return "生成" in ctx.q_no_space and any(keyword in ctx.q_no_space for keyword in ("输入", "input"))


def _extract_first_job_id(text: str) -> str | None:
    match = re.search(r"(?<!\d)(\d{4,})(?!\d)", text)

    if match:
        return match.group(1)

    return None


def _route_to_vasp_analysis_by_reference(ctx: RouteContext) -> bool:
    if "分析" not in ctx.question:
        return False

    reference = _extract_first_job_id(ctx.question)

    if not reference and not _last_job_reference(ctx):
        return False

    from modules.core.conversation_state import GLOBAL_CONVERSATION_STATE
    from modules.slurm.job_registry import get_job

    job_id = reference

    if not job_id and _last_job_reference(ctx):
        job_id = GLOBAL_CONVERSATION_STATE.resolve_vasp_job_id("刚才那个 VASP 作业")

    if not job_id:
        return False

    job = get_job(job_id)

    if job and str(job.get("type", "")).lower() == "vasp":
        return True

    recent_vasp = GLOBAL_CONVERSATION_STATE.get_recent_job(kind="vasp")
    return bool(recent_vasp and str(recent_vasp.get("job_id")) == str(job_id))


def _cluster_partition_qa_request(ctx: RouteContext) -> bool:
    cluster_terms = [
        "amd_test", "amd_256", "bscc-a", "partition",
        "sinfo", "队列", "分区",
    ]
    time_or_choice_terms = [
        "能跑多久", "跑多久", "最长", "时间限制", "timelimit",
        "max_time", "maxtime", "用哪个", "哪个分区", "哪个队列",
        "哪个partition", "提交到哪个", "应该提交到哪个",
        "正式作业", "正式vasp作业",
    ]

    if ctx.match_any(cluster_terms) and ctx.match_any(time_or_choice_terms):
        return True

    return (
        ctx.match_any(["all"])
        and ctx.match_any(["inactive", "inact", "可用", "能不能用", "能用吗"])
    )


ROUTE_RULES: tuple[RouteRule, ...] = (
    RouteRule("negated_cleanup_howto", "rag_qa", lambda ctx: ctx.negated_cleanup and ctx.is_howto_or_concept),
    RouteRule("resource_howto", "rag_qa", lambda ctx: ctx.is_howto_or_concept and ctx.match_any(KEYWORDS["params"])),
    RouteRule("cluster_partition_qa", "rag_qa", _cluster_partition_qa_request),
    RouteRule("vasp_howto_or_concept", "rag_qa", lambda ctx: ctx.is_vasp_request and ctx.is_howto_or_concept and not ctx.match_any(KEYWORDS["params"])),
    RouteRule("vasp_file_catalog_howto", "rag_qa", lambda ctx: ctx.is_vasp_request and "有哪些" in ctx.q_no_space and not ctx.match_any(["远端", "远程", "目录"])),
    RouteRule("check_local_resources", "check_local_resources", _local_resource_check_request),
    RouteRule("project_doctor", "project_doctor", lambda ctx: ctx.match_any(KEYWORDS["project_doctor"])),
    RouteRule("vasp_params", "suggest_params", lambda ctx: ctx.is_vasp_request and ctx.match_any(KEYWORDS["params"])),
    RouteRule("current_config", "current_config", lambda ctx: ctx.match_any(KEYWORDS["current_config"])),
    RouteRule("check_hpc_config", "check_hpc_config", lambda ctx: ctx.match_any(KEYWORDS["hpc_config_check"])),
    RouteRule("test_hpc_submission", "test_hpc_submission", lambda ctx: ctx.match_any(KEYWORDS["hpc_submission_test"])),
    RouteRule("job_record_status", "job_record_status", lambda ctx: ctx.match_any(KEYWORDS["job_record_status"])),
    RouteRule("preview_restore_job_records", "preview_restore_job_records", lambda ctx: ctx.match_any(KEYWORDS["preview_restore_job_records"]) and ctx.match_any(["恢复", "归档"])),
    RouteRule("list_job_record_archives", "list_job_record_archives", lambda ctx: ctx.match_any(KEYWORDS["list_job_record_archives"])),
    RouteRule("preview_archive_job_records", "preview_archive_job_records", lambda ctx: ctx.match_any(KEYWORDS["preview_archive_job_records"]) and ctx.match_any(["归档", "保留"])),
    RouteRule("recent_jobs", "recent_jobs", lambda ctx: ctx.match_any(KEYWORDS["recent_jobs"])),
    RouteRule("job_detail", "job_detail", lambda ctx: ctx.match_any(KEYWORDS["job_detail"])),
    RouteRule("list_local_vasp_jobs", "list_local_vasp_jobs", _local_vasp_job_list_request),
    RouteRule("sync_vasp_output", "sync_vasp_output", lambda ctx: ctx.is_vasp_request and (ctx.has_job_id or _last_job_reference(ctx)) and ctx.match_any(KEYWORDS["sync_vasp_action"]) and ctx.match_any(KEYWORDS["sync_vasp_target"])),
    RouteRule("vasp_job_output", "job_output", lambda ctx: ctx.is_vasp_request and (ctx.has_job_id or _last_job_reference(ctx)) and ctx.match_any(KEYWORDS["job_output"] + ["输出", "结果"])),
    RouteRule("vasp_job_error", "job_error", lambda ctx: ctx.is_vasp_request and (ctx.has_job_id or _last_job_reference(ctx)) and ctx.match_any(KEYWORDS["job_error"] + ["错误", "报错", "日志"])),
    RouteRule("vasp_job_status", "job_status", lambda ctx: ctx.is_vasp_request and (ctx.has_job_id or _last_job_reference(ctx)) and ctx.match_any(KEYWORDS["job_status"] + ["状态", "跑完没", "算完没", "进度"])),
    RouteRule("diagnose_job", "diagnose_job", lambda ctx: (ctx.has_job_id or _last_job_reference(ctx)) and ctx.match_any(KEYWORDS["diagnose_job"])),
    RouteRule("vasp_list_remote", "list_remote_vasp_jobs", lambda ctx: ctx.is_vasp_request and ctx.match_any(KEYWORDS["list_remote_job"] + ["列出", "查看", "有哪些", "有什么"])),
    RouteRule("vasp_cleanup_directory_root", "cleanup_all_remote_vasp_jobs", _generic_vasp_directory_cleanup_request),
    RouteRule("vasp_cleanup_all", "cleanup_all_remote_vasp_jobs", lambda ctx: ctx.is_vasp_request and ctx.match_any(KEYWORDS["cleanup"]) and ctx.match_any(KEYWORDS["cleanup_all"])),
    RouteRule("vasp_cleanup_single", "cleanup_remote_vasp_job", lambda ctx: ctx.is_vasp_request and ctx.match_any(KEYWORDS["cleanup"])),
    RouteRule("cleanup_howto", "rag_qa", lambda ctx: ctx.negated_cleanup and ctx.is_howto_or_concept),
    RouteRule("cleanup_all", "cleanup_all_remote_jobs", lambda ctx: ctx.match_any(KEYWORDS["cleanup"]) and ctx.match_any(KEYWORDS["cleanup_all"])),
    RouteRule("cleanup_single", "cleanup_remote_job", lambda ctx: ctx.match_any(KEYWORDS["cleanup"]) and ctx.has_job_id),
    RouteRule("list_remote", "list_remote_jobs", lambda ctx: ctx.match_any(KEYWORDS["list_remote_job"])),
    RouteRule("register_vasp_job", "register_vasp_job", lambda ctx: ctx.is_vasp_request and (ctx.match_any(KEYWORDS["register_vasp"]) or (ctx.has_job_id and ctx.match_any(KEYWORDS["register_vasp_loose"])))),
    RouteRule("generate_vasp_report", "generate_vasp_report", lambda ctx: ctx.is_vasp_request and ctx.match_any(KEYWORDS["vasp_report"])),
    RouteRule("generate_vasp_inputs", "generate_vasp_inputs", _vasp_input_generation_request),
    RouteRule("generate_vasp_job_explicit", "generate_vasp_job", _explicit_vasp_job_generation_request),
    RouteRule("submit_vasp_job", "submit_vasp_job", lambda ctx: ctx.is_vasp_request and ctx.match_any(KEYWORDS["submit"])),
    RouteRule("analyze_vasp_job_by_reference", "analyze_vasp_job", _route_to_vasp_analysis_by_reference),
    RouteRule("analyze_vasp_job", "analyze_vasp_job", lambda ctx: ctx.is_vasp_request and ctx.match_any(KEYWORDS["analyze_vasp"])),
    RouteRule("generate_vasp_job", "generate_vasp_job", lambda ctx: ctx.is_vasp_request and ctx.match_any(KEYWORDS["sbatch"])),
    RouteRule("vasp_fallback", "generate_vasp_job", lambda ctx: ctx.is_vasp_request),
    RouteRule("troubleshoot_job", "troubleshoot_job", lambda ctx: ctx.match_any(KEYWORDS["troubleshoot"])),
    RouteRule("suggest_params", "suggest_params", lambda ctx: ctx.match_any(KEYWORDS["params"])),
    RouteRule("howto_or_concept", "rag_qa", lambda ctx: ctx.is_howto_or_concept),
    RouteRule("negated_submit_howto", "rag_qa", lambda ctx: ctx.negated_submit and ctx.is_howto_or_concept),
    RouteRule("preview_only_submit", "generate_sbatch", _preview_only_submit_request),
    RouteRule("file_submit", "submit_job", _file_submit_request),
    RouteRule("generate_test_file", "generate_test_file", lambda ctx: is_test_file_request(ctx.question)),
    RouteRule("generate_sbatch", "generate_sbatch", _explicit_sbatch_request),
    RouteRule("submit_job", "submit_job", lambda ctx: ctx.match_any(KEYWORDS["submit"])),
    RouteRule("explicit_job_output", "job_output", lambda ctx: ctx.match_any(["作业输出", "作业结果"])),
    RouteRule("last_job_output", "job_output", lambda ctx: _last_job_reference(ctx) and ctx.match_any(KEYWORDS["job_output"] + ["输出", "结果"])),
    RouteRule("last_job_error", "job_error", lambda ctx: _last_job_reference(ctx) and ctx.match_any(KEYWORDS["job_error"] + ["错误", "报错", "日志"])),
    RouteRule("last_job_status", "job_status", lambda ctx: _last_job_reference(ctx) and ctx.match_any(KEYWORDS["job_status"] + ["查看", "查询", "状态", "作业", "任务"])),
    RouteRule("job_id_status", "job_status", _job_id_status_request),
    RouteRule("job_id_output", "job_output", _job_id_output_request),
    RouteRule("job_id_error", "job_error", _job_id_error_request),
    RouteRule("job_status", "job_status", lambda ctx: ctx.match_any(KEYWORDS["job_status"])),
    RouteRule("job_output", "job_output", lambda ctx: ctx.match_any(KEYWORDS["job_output"])),
    RouteRule("job_error", "job_error", lambda ctx: ctx.match_any(KEYWORDS["job_error"])),
    RouteRule("prepare_error_case", "prepare_error_case", lambda ctx: ctx.match_any(KEYWORDS["prepare_error_case"])),
    RouteRule("diagnose_error", "diagnose_error", lambda ctx: any(keyword in ctx.q for keyword in KEYWORDS["error"])),
    RouteRule("generate_sbatch_second_chance", "generate_sbatch", lambda ctx: ctx.match_any(KEYWORDS["sbatch"])),
)


def _detect_intent_only(question: str) -> str:
    ctx = _build_context(question)

    if _shortcut_help_request(ctx):
        return "shortcut_help"

    if _looks_like_clarify_request(ctx.q_no_space, ctx.q_normalized):
        return "clarify"

    for rule in ROUTE_RULES:
        if rule.predicate(ctx):
            return rule.intent

    return "rag_qa"


def _shortcut_help_request(ctx: RouteContext) -> bool:
    stripped = ctx.question.strip().lower()
    compact = stripped.replace(" ", "")
    return (
        stripped in {"/help", "/help job", "/help vasp", "/help cleanup", "/help config", "/help skill"}
        or compact in {"/helpjob", "/helpvasp", "/helpcleanup", "/helpconfig", "/helpskill", "/skilllist"}
        or stripped.startswith("/skill route ")
        or compact in {"帮助", "快捷命令", "命令帮助"}
    )


def get_intent_risk(intent: str) -> str:
    return INTENT_RISKS.get(intent, "unknown")


def _combine_plan_risk(steps: list[RoutePlanStep]) -> str:
    risks = [step.risk for step in steps]
    if "destructive_confirm_required" in risks:
        return "destructive_confirm_required"
    if "confirm_required" in risks:
        return "confirm_required"
    if "generate_or_confirm_required" in risks:
        return "generate_or_confirm_required"
    if "clarify_required" in risks:
        return "clarify_required"
    if "generate_only" in risks:
        return "generate_only"
    if "read_only" in risks:
        return "read_only"
    return "none"


def _has_plan_markers(question: str) -> bool:
    normalized = question.lower().replace(" ", "")
    if "提交并分析" in normalized or "运行并分析" in normalized:
        return False
    return (
        sum(marker in normalized for marker in KEYWORDS["sequential_markers"]) >= 2
        or any(marker in normalized for marker in KEYWORDS["conditional_markers"])
        or bool(re.search(r"(先.+(然后|再|接着|随后|最后))", normalized))
    )


def _split_plan_segments(question: str) -> list[tuple[str, str | None]]:
    text = re.sub(r"[；;。]", "，", question.strip())
    parts = [part.strip(" ，,") for part in re.split(r"[，,]", text) if part.strip(" ，,")]
    segments: list[tuple[str, str | None]] = []
    pending_condition: str | None = None

    for part in parts:
        part = re.sub(r"^(先|然后|再|接着|随后|最后)", "", part).strip()
        if not part:
            continue

        conditional_match = None
        if "跑完没" not in part and "算完没" not in part:
            conditional_match = re.match(r"^(如果|若)?(.{0,24}?(?:跑完|完成|结束|成功)了?|跑完了|完成后|结束后|成功后)(.*)$", part)
        if conditional_match:
            condition = conditional_match.group(2).strip()
            remainder = conditional_match.group(3).strip()
            pending_condition = condition or "前一步完成后"
            if not remainder:
                continue
            part = remainder

        subparts = [
            item.strip(" ，,")
            for item in re.split(r"(?:并且|并|然后|再|接着|随后|最后)", part)
            if item.strip(" ，,")
        ]
        for subpart in subparts:
            segments.append((subpart, pending_condition))
            pending_condition = None

    return segments


def _route_followup_to_previous_job(text: str, previous_steps: list[RoutePlanStep]) -> str:
    if not previous_steps:
        return text

    previous_action = previous_steps[-1].intent
    if previous_action not in {"submit_job", "submit_vasp_job", "generate_test_file"}:
        return text

    ctx = _build_context(text)
    if ctx.has_job_id or _last_job_reference(ctx):
        return text

    if ctx.match_any(KEYWORDS["job_output"] + ["输出", "结果"]):
        return f"刚才那个作业{text}"

    if ctx.match_any(KEYWORDS["job_error"] + ["错误", "报错", "日志"]):
        return f"刚才那个作业{text}"

    if ctx.match_any(KEYWORDS["job_status"] + ["状态", "作业", "任务"]):
        return f"刚才那个作业{text}"

    return text


def analyze_plan(question: str) -> RoutePlan | None:
    if not _has_plan_markers(question):
        return None

    raw_segments = _split_plan_segments(question)
    steps: list[RoutePlanStep] = []

    full_context = _build_context(question)

    for text, condition in raw_segments:
        segment_text = text
        if full_context.is_vasp_request and not _build_context(segment_text).is_vasp_request:
            segment_text = f"上次 VASP 作业 {segment_text}"
        else:
            segment_text = _route_followup_to_previous_job(segment_text, steps)

        decision = analyze_intent(segment_text)
        if decision.intent == "rag_qa" and len(text) <= 4:
            continue
        steps.append(
            RoutePlanStep(
                index=len(steps) + 1,
                text=text,
                route_text=segment_text,
                intent=decision.intent,
                risk=decision.risk,
                condition=condition,
                needs_clarification=decision.needs_clarification,
                clarification=decision.clarification,
            )
        )

    actionable_steps = [step for step in steps if step.intent not in {"rag_qa"}]
    if len(actionable_steps) < 2:
        return None

    return RoutePlan(
        steps=steps,
        is_conditional=any(step.condition for step in steps),
        risk=_combine_plan_risk(steps),
    )


def serialize_route_plan(plan: RoutePlan) -> dict:
    return {
        "is_conditional": plan.is_conditional,
        "risk": plan.risk,
        "steps": [
            {
                "index": step.index,
                "text": step.text,
                "route_text": step.route_text,
                "intent": step.intent,
                "risk": step.risk,
                "condition": step.condition,
                "needs_clarification": step.needs_clarification,
                "clarification": step.clarification,
            }
            for step in plan.steps
        ],
    }


def parse_plan_step_selection(text: str) -> int | str | None:
    normalized = text.lower().replace(" ", "")
    if normalized in {
        "全部执行", "执行全部", "确认全部", "全执行", "执行所有", "确认所有",
        "全部确认", "全部运行", "运行全部", "确认执行", "继续执行",
        "runall", "confirmall",
    }:
        return "all"

    patterns = [
        r"^(?:确认|执行|运行|开始|做)(\d+)$",
        r"^第(\d+)(?:步|个)?$",
        r"^(?:确认|执行|运行|开始|做)第(\d+)(?:步|个)?$",
        r"^step(\d+)$",
    ]

    for pattern in patterns:
        match = re.match(pattern, normalized)
        if match:
            return int(match.group(1))

    return None


def can_execute_plan_all(plan: dict | RoutePlan) -> bool:
    if isinstance(plan, RoutePlan):
        steps = [
            {"risk": step.risk, "needs_clarification": step.needs_clarification}
            for step in plan.steps
        ]
    else:
        steps = plan.get("steps") or []

    safe_risks = {"none", "read_only", "generate_only"}
    return bool(steps) and all(
        step.get("risk") in safe_risks and not step.get("needs_clarification")
        for step in steps
    )


def format_route_plan(plan: RoutePlan) -> str:
    lines = [
        "我识别到这是一个多步骤请求。为了避免长命令被误执行，我先拆成计划：",
        "",
    ]

    for step in plan.steps:
        condition = f"条件: {step.condition}; " if step.condition else ""
        lines.append(
            f"{step.index}. {condition}意图: {step.intent}; 风险: {step.risk}; 原文: {step.text}"
        )
        if step.needs_clarification and step.clarification:
            lines.append(f"   需要补充: {step.clarification}")

    lines.extend([
        "",
        f"整体风险: {plan.risk}",
        "当前不会自动连续执行这些步骤。可以回复“确认1”或“执行1”来执行某一步；若全部步骤都是只读/生成类，也可以回复“全部执行”。",
    ])
    return "\n".join(lines)


def get_clarification(question: str) -> str:
    ctx = _build_context(question)
    return (
        _looks_like_clarify_request(ctx.q_no_space, ctx.q_normalized)
        or "这句话还缺少关键信息。请补充 Job ID、文件路径、命令或你想执行的具体操作。"
    )


def _explain_decision(question: str, intent: str) -> tuple[str, list[str], list[str]]:
    ctx = _build_context(question)
    skipped: list[str] = []

    if ctx.negated_vasp:
        skipped.append("vasp_negated")
    if ctx.negated_cleanup:
        skipped.append("cleanup_negated")
    if ctx.negated_submit:
        skipped.append("submit_negated")

    matched = [
        kw for kw in EXPLANATION_KEYWORDS.get(intent, [])
        if kw in ctx.q_no_space or kw in ctx.q_normalized
    ]

    if intent == "clarify":
        return "ambiguous_request_missing_required_slots", matched or ["ambiguous"], skipped
    if intent == "rag_qa":
        if _cluster_partition_qa_request(ctx):
            return "cluster_partition_qa", matched or ["cluster_partition"], skipped
        reason = "howto_or_concept_question" if ctx.is_howto_or_concept else "fallback_no_rule_matched"
        return reason, matched, skipped
    if matched:
        return "keyword_rule_matched", matched, skipped
    return "rule_matched_without_keyword_explanation", [], skipped


def analyze_intent(question: str) -> RouteDecision:
    intent = _detect_intent_only(question)
    reason, matched, skipped = _explain_decision(question, intent)
    needs_clarification = intent == "clarify"
    return RouteDecision(
        intent=intent,
        risk=get_intent_risk(intent),
        reason=reason,
        matched_keywords=matched,
        skipped_rules=skipped,
        needs_clarification=needs_clarification,
        clarification=get_clarification(question) if needs_clarification else None,
    )


def detect_intent(question: str) -> str:
    return analyze_intent(question).intent


def is_rule_confident(intent: str) -> bool:
    return intent not in {"rag_qa", "clarify"}

# HPC Agent

HPC Agent 是一个面向 HPC / Slurm 超算环境的对话式助手，当前保留 **Textual TUI**（终端全屏界面）作为统一交互入口。

核心功能覆盖 Slurm 知识问答、sbatch 脚本生成、普通作业提交/查询/清理、VASP 固定目录作业提交、VASP 输出同步与报告生成，以及基于 Claude Code 的 VASP 计算结果分析。

详细操作请看 [USER_GUIDE.md](USER_GUIDE.md)。

---

## 当前能力

### Slurm / HPC 知识问答
* 基于 RAG（TF-IDF + DeepSeek-V4-Pro）的 Slurm/HPC 知识库问答
* 知识库文档涵盖：集群信息、常见错误、GPU 使用、sbatch 提交、作业状态、作业取消

### 普通 Slurm 作业
* 根据自然语言生成普通 sbatch 脚本
* 根据本地普通作业文件自动补充推荐资源参数（CPU、内存、时间、GPU）
* 普通 Slurm 作业确认式提交（生成 job.sh 预览 → 确认 → SSH 上传提交）
* 普通作业文件上传到远端独立作业目录
* 支持 `.py`、`.sh`、`.slurm`、`.sbatch` 文件类型
* 危险命令检测（拒绝生成 `rm -rf`、`shutdown`、`reboot`、`mkfs` 等脚本）

### 作业查询与监控
* 查询作业状态（squeue / sacct）
* 读取 stdout / stderr
* Textual TUI 实时 Job Monitor（右侧面板，15 秒自动刷新）
* 同时监控多个运行中 Job，按 `Tab` 切换
* 监控面板显示：Job ID、State、Elapsed、Remote Dir、stdout/stderr 尾部摘录
* VASP 作业监控时附带实时诊断（错误/警告匹配）

### 远端作业管理
* 列出远端普通作业编号
* 按 Job ID 清理远端普通作业文件
* 清理全部远端普通作业文件（保留根目录）
* 列出远端 VASP 作业
* 按 Job ID 清理远端 VASP 作业
* 清理全部远端 VASP 作业

### VASP 作业
* VASP sbatch 脚本生成（结构优化/静态计算/其他）
* VASP 固定目录提交：本地 input → 远端 input → 远端 output
* 登记已有 VASP 作业，便于后续查询和同步
* VASP 输出同步到本地（按 include/exclude 规则过滤文件）
* VASP 远程文件探针与实时诊断（POTCAR、Fortran severe、OOM、Segfault、Disk full、Walltime 等）
* OUTCAR / OSZICAR 确定性解析（能量、力、应力、能带、收敛状态等）
* report_context.md 自动生成（为 Claude Code 提供结构化上下文）
* Claude Code 报告生成：`report.md`（中文用户报告）、`paper_methods.md`（英文）、`paper_results.md`（英文）
* 一键分析：自动完成同步 → report_context → Claude Code 报告全流程

### 错误诊断
* 基于规则匹配的错误日志诊断（18 类错误模式）
* 自动修复 sbatch 脚本（OOM → 提高内存、TIME → 延长时间、partition → 修正分区等）
* Pending / 不运行作业排查

### TUI 交互入口
* **Textual TUI**：全屏终端界面，含 Chat 面板和 Job Monitor 面板
* 支持确认/取消状态机（提交确认、清理确认）

### Claude Code 集成
* 通过 `skills/vasp_report/SKILL.md` 定义分析 Skill
* 调用 Claude Code CLI 生成 VASP 计算报告
* 严格约束：只使用 `report_context.md`，不编造未确认的论文结果
* 可配置模型、超时时间和命令路径

### Job Registry
* 基于 JSON 文件的本地作业登记
* 记录 Job ID、类型（slurm/vasp）、远端路径、本地路径、上传文件

### 测试体系
* 本地全量检查：Python 语法、Slurm Assistant、Error Diagnoser、VASP Assistant、Router Intent、Job Query、Submit Preview、HPC Env Config
* Live HPC 工作流检查（`--live-hpc`，真实超算提交测试）
* SSH 连接检查

---

## 快速开始

安装依赖：

```bash
uv sync
```

启动统一入口：

```bash
python app.py
```

启动后会直接进入 Textual TUI。

---

## 环境变量

项目根目录需要 `.env`。示例：

```env
PARATERA_BASE_URL=https://your-api-base-url
PARATERA_API_KEY=your-api-key

HPC_HOST=your-hpc-host
HPC_USERNAME=your-hpc-username
HPC_KEY_PATH=/path/to/your/private/key
HPC_LOCAL_WORKDIR=/path/to/local/hpc-agent-jobs
HPC_REMOTE_WORKDIR=/path/to/remote/hpc-agent-jobs
HPC_DEFAULT_PARTITION=

HPC_LOCAL_VASP_JOBS_INPUT_DIR=/path/to/local/vasp-jobs-input
HPC_LOCAL_VASP_JOBS_OUTPUT_DIR=/path/to/local/vasp-jobs-output
HPC_VASP_REMOTE_INPUT_DIR=/path/to/remote/vasp-hpc-jobs-input
HPC_VASP_REMOTE_OUTPUT_DIR=/path/to/remote/vasp-hpc-jobs-output
HPC_VASP_PARTITION=
HPC_VASP_SETUP_COMMAND=source /public1/soft/intel/2020u4/compilers_and_libraries_2020.4.304/linux/bin/compilervars.sh intel64
HPC_VASP_COMMAND=mpirun /public1/soft/vasp
HPC_VASP_MODULE=

HPC_CLAUDE_CODE_COMMAND=claude
HPC_CLAUDE_CODE_MODEL=DeepSeek-V4-Pro
HPC_CLAUDE_CODE_TIMEOUT_SECONDS=1800
```

说明：

* `PARATERA_BASE_URL`：LLM API 服务地址。
* `PARATERA_API_KEY`：LLM API Key。
* `HPC_HOST`：超算 SSH 登录主机。
* `HPC_USERNAME`：超算用户名。
* `HPC_KEY_PATH`：本机 SSH 私钥绝对路径（Ed25519）。
* `HPC_LOCAL_WORKDIR`：本地普通作业/测试文件工作目录；裸文件名查找会同时搜索当前启动目录和该目录。
* `HPC_REMOTE_WORKDIR`：普通 Slurm 作业远端根目录。
* `HPC_DEFAULT_PARTITION`：普通作业默认 partition；留空表示不写 `#SBATCH --partition`，使用集群默认分区。
* `HPC_LOCAL_VASP_JOBS_INPUT_DIR`：本地 VASP 输入作业根目录。
* `HPC_LOCAL_VASP_JOBS_OUTPUT_DIR`：本地 VASP 输出和分析根目录。
* `HPC_VASP_REMOTE_INPUT_DIR`：VASP 作业远端输入根目录。
* `HPC_VASP_REMOTE_OUTPUT_DIR`：VASP 作业远端输出/运行根目录。
* `HPC_VASP_PARTITION`：VASP 作业默认 partition；留空表示不写 `#SBATCH --partition`，使用集群默认分区。
* `HPC_VASP_SETUP_COMMAND`：VASP 运行前的环境初始化命令。当前集群上 Intel MPI 的 `mpirun` 通常需要先 source Intel 环境。
* `HPC_VASP_COMMAND`：VASP 主程序启动命令。普通 MPI 测试默认用 `srun`，VASP 默认保持 `mpirun /public1/soft/vasp`。
* `HPC_VASP_MODULE`：可选，留空表示不使用 `module load`。
* `HPC_CLAUDE_CODE_COMMAND`：Claude Code 命令，默认 `claude`。
* `HPC_CLAUDE_CODE_MODEL`：Claude Code 使用的模型名；留空时使用环境默认，Paratera 网关默认回退到 `DeepSeek-V4-Pro`。
* `HPC_CLAUDE_CODE_TIMEOUT_SECONDS`：Claude Code 报告生成超时时间，默认 1800 秒。

Claude Code 报告生成会把 `PARATERA_API_KEY` 同时传给 `ANTHROPIC_API_KEY` 和 `ANTHROPIC_AUTH_TOKEN`，并把 `PARATERA_BASE_URL` 传给 `ANTHROPIC_BASE_URL`。如果报告生成报认证错误，优先检查 `.env` 中的 `PARATERA_API_KEY` 是否过期，以及该 key 是否支持 `HPC_CLAUDE_CODE_MODEL`。

`.env` 不应提交到 Git。

---

## 常用命令

普通作业：

```text
跑 train.py，4核，15分钟
帮我提交 ./run.sh，2核，30分钟
帮我提交一个作业运行 python train.py，8核，1小时，16G内存
创建 srun -n 4 hostname 测试脚本并运行
确认提交
取消提交
```

作业查询与监控：

```text
查看 11814753 的状态
读取 11814753 的输出
读取 11814753 的错误日志
监控 11814753
取消监控 11814753
列出远端作业编号
```

远端普通作业清理：

```text
清理远端作业 11817627 的文件
确认清理
清理远端普通作业目录下所有作业文件
确认清理全部
```

VASP：

```text
帮我生成一个 VASP 结构优化脚本，1 个节点，每节点 32 核，运行 24 小时
帮我提交 VASP 作业，目录名 si_static_test，1 个节点 32 核，运行 10 分钟
登记 VASP 作业 11817144，目录名 si_static_test
同步 VASP 作业 11817144 输出到本地
生成 VASP 作业 si_static_test 报告
一键分析 VASP 作业 si_static_test
列出远端 VASP 作业
清理远端 VASP 作业 si_static_test 的文件
清理全部远端 VASP 作业文件
```

错误诊断：

```text
CUDA out of memory
ModuleNotFoundError: No module named numpy
sbatch: error: Batch job submission failed: Invalid partition name specified
我的任务一直 pending
```

---

## 普通作业流程

普通作业提交时，Agent 会先生成 `job.sh` 并展示预览。用户回复 `确认提交` 后，Agent 才会通过 SSH 连接超算并提交。

每次普通作业会在 `HPC_REMOTE_WORKDIR` 下创建独立目录，保存：

```text
job.sh
用户上传或本地读取的普通作业文件
hpc_agent_job_<jobid>.out
hpc_agent_job_<jobid>.err
```

普通作业支持 `.py`、`.sh`、`.slurm`、`.sbatch` 这类本地文件路径。没有显式指定 CPU、时间、内存、GPU 时，Agent 会尝试根据文件内容给出推荐参数；用户显式指定的参数优先。

当用户只写裸 Python 文件名（例如 `运行 test.py`）或上传 `.py` 文件但没有写运行命令时，Agent 默认推断为 `python3 test.py`。如果用户明确写了 `python train.py`，Agent 会尊重用户写出的命令。

---

## VASP 固定目录流程

### 提交准备

VASP 提交前，用户需要手动在本地准备完整作业目录：

```text
$HPC_LOCAL_VASP_JOBS_INPUT_DIR/<job-folder>/
├── INCAR
├── KPOINTS
├── POSCAR
└── POTCAR
```

### 提交过程

提交时 Agent 只做三件事：

1. 选择本地 `$HPC_LOCAL_VASP_JOBS_INPUT_DIR/<job-folder>`。
2. 上传该目录文件到远端 `$HPC_VASP_REMOTE_INPUT_DIR/<job-folder>`。
3. 在远端 `$HPC_VASP_REMOTE_OUTPUT_DIR/<job-folder>` 写入并运行 `job.sh`。

VASP 标准输出、错误日志和运行结果写入远端 output 目录。Agent 不会生成真实 `POTCAR`，`POTCAR` 需要来自你有权限使用的 VASP 赝势库。

当前建议的启动策略是：普通 Slurm/MPI 测试使用 `srun -n N ...`；VASP 使用 `HPC_VASP_SETUP_COMMAND` 初始化 Intel 环境后运行 `mpirun /public1/soft/vasp`。这两条路径不要混在一起配置。

### 输出同步

作业完成后，用"同步 VASP 作业 <job_id> 输出到本地"拉取必要结果文件：

```text
$HPC_LOCAL_VASP_JOBS_OUTPUT_DIR/<job-folder>/
├── raw_output/
│   ├── INCAR
│   ├── KPOINTS
│   ├── POSCAR
│   ├── OUTCAR
│   ├── OSZICAR
│   ├── CONTCAR
│   └── vasprun.xml
└── analysis/
    ├── file_manifest.json
    └── report_context.md
```

同步规则：
- **包含**：INCAR、POSCAR、KPOINTS、OUTCAR、OSZICAR、CONTCAR、vasprun.xml、*.out、*.err
- **排除**：WAVECAR、CHGCAR、AECCAR*、POTCAR（避免拉回超大文件或赝势文件）

### 一键分析与报告生成

"一键分析 VASP 作业 <job-folder>" 自动完成三个步骤：

1. **同步输出**：从远端拉取结果文件到本地 output 目录
2. **生成 report_context.md**：包含 VASP 确定性事实、INCAR/KPOINTS/POSCAR 摘要、日志摘要、诊断信息
3. **调用 Claude Code**：生成以下三个文件：
   - `analysis/report.md` — 中文用户报告
   - `analysis/paper_methods.md` — 英文论文方法描述
   - `analysis/paper_results.md` — 英文论文结果描述

也可以分步执行：

```text
# 仅同步
同步 VASP 作业 11817144 输出到本地

# 仅生成报告（同步完成后）
生成 VASP 作业 si_static_test 报告
```

VASP 确定性事实从 OUTCAR/OSZICAR 解析获得，包括：
- 收敛状态、自由能（TOTEN / energy without entropy / energy sigma→0）
- E-fermi、ISMEAR、SIGMA、NELECT
- 晶胞体积、晶格矢量、ENCUT
- 应力张量、外部压强
- 力（最大 |force|、平均力范数）
- 计算耗时（CPU 时间、经历时间、最大内存）
- 能带结构（VBM、CBM、带隙）
- 离子种类、数量、原子质量
- DAV/RMM 迭代次数

Claude Code 报告生成加载 `skills/vasp_report/SKILL.md`，该 skill 严格约束只使用 `analysis/report_context.md` 中的内容，避免把大体积 VASP 原始输出直接塞进模型上下文，也禁止编造未在上下文中确认的结果。

报告生成以 `analysis/report_context.md` 为受控输入：数值结果来自确定性解析器，Claude Code 只负责组织中文报告和英文 methods/results 文本。调用 Claude Code 时使用 `--bare` 模式并要求只返回 JSON，最终的 `report.md`、`paper_methods.md`、`paper_results.md` 由 Python 写入。

---

## VASP 实时诊断

TUI 模式下，VASP 作业被监控时会自动进行实时诊断。诊断探针检查远端 output 目录中关键文件，并匹配以下规则：

**错误检测**：POTCAR 输入转换错误、Fortran 严重错误、OOM、Segfault、磁盘满、Walltime 超限、文件缺失、VASP 崩溃等。

**警告检测**：BRMIX 电荷混合、ZBRENT 电子收敛、几何优化步失败等。

诊断结果包含严重级别（ok/warning/error）、具体问题列表、证据和修复建议。

---

## TUI 快捷键

Textual TUI 当前布局：

* 顶部：连接信息、远端普通作业根目录、快捷键提示
* 左侧：Chat 对话区
* 右侧：Job Monitor
* 底部：固定输入框

快捷键：

```text
Ctrl+R  手动刷新当前监控 Job
Ctrl+Y  复制上一条 Agent 回复
Ctrl+S  确认提交等待中的作业
Tab     切换右侧正在监控的 Job
Esc     取消当前等待确认的操作
Ctrl+X  退出
F10     退出
q       退出
```

---

## 错误诊断

错误诊断基于 `data/errors/errors_db.json` 中的 18 类错误模式，通过正则匹配识别问题并给出修复建议。覆盖类别：内存、权限、Slurm 配置、存储、文件、Python 环境、编译、GPU、SSH 等。

除了粘贴错误日志直接诊断外，还能对已生成的 sbatch 脚本自动修改：
- OOM → 添加 `--mem` 或提高内存
- TIME → 添加或延长 `--time`
- partition 无效 → 添加 `--partition=general`
- 缺少 nodes/cpus → 添加 `--nodes=1 --cpus-per-task=4`
- GPU OOM → 添加 `--gres=gpu:1 --mem=32G`
- 无 CUDA → 添加 `--gres=gpu:1` + `module load cuda`

---

## 测试

本地检查：

```bash
.venv/bin/python tests/run_all_checks.py
```

真实超算工作流检查：

```bash
.venv/bin/python tests/run_all_checks.py --live-hpc
```

`--live-hpc` 会连接超算并提交真实 Slurm 测试作业。

---

## 项目结构

```text
hpc-agent/
├── app.py                    # 统一入口，默认启动 Textual TUI
├── textual_cli.py            # Textual TUI 模式
├── pyproject.toml            # 项目配置和依赖
├── job.sh                    # 占位 Slurm 脚本
├── .env.example              # 环境变量模板
│
├── modules/
│   ├── core/                 # Agent runtime、上下文、确认状态、通用 tool calling
│   ├── routing/              # 自然语言意图检测、LLM intent fallback、工具分发
│   ├── slurm/                # Slurm 脚本、提交、查询、清理、远端操作、测试作业
│   ├── vasp/                 # VASP 脚本、监控、解析、报告上下文、Claude Code 报告
│   ├── tui/                  # Textual TUI helper、formatter、monitor、workflow 状态
│   └── knowledge/            # RAG 知识库和错误诊断
│
├── data/
│   ├── hpc_documents/        # RAG 知识库文档（6 个 txt）
│   │   ├── cluster_info.txt
│   │   ├── common_errors.txt
│   │   ├── gpu_usage.txt
│   │   ├── slurm_submit.txt
│   │   ├── slurm_status.txt
│   │   └── slurm_cancel.txt
│   ├── errors/
│   │   └── errors_db.json    # 18 类错误诊断规则
│   └── jobs/
│       └── job_registry.json # 作业登记数据库
│
├── skills/                   # Claude Code Skill 定义
│   ├── diagnose_error/SKILL.md
│   ├── generate_sbatch/SKILL.md
│   ├── generate_vasp_job/SKILL.md
│   └── vasp_report/SKILL.md
│
├── tests/
│   ├── run_all_checks.py     # 测试编排器
│   ├── core/
│   ├── routing/
│   ├── slurm/
│   ├── vasp/
│   └── knowledge/
│
├── README.md
└── USER_GUIDE.md
```

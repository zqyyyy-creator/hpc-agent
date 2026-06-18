# HPC Agent 用户手册

本文档说明如何配置、启动和使用 HPC Agent。当前代码保留 Textual TUI 作为统一交互入口。普通 Slurm 作业和 VASP 作业使用不同流程，尤其是 VASP 只保留固定目录提交逻辑。

---

## 1. 功能总览

### Slurm / HPC 知识问答
* 基于 RAG（TF-IDF + LLM）检索知识库文档
* 知识库覆盖：集群信息、常见错误、GPU 使用、sbatch 提交、作业状态、作业取消

### 普通 Slurm 作业
* 根据自然语言生成普通 sbatch 脚本
* 根据普通作业文件自动推荐 CPU、内存、时间、GPU 参数
* 普通 Slurm 作业确认式提交（生成预览 → 确认 → SSH 上传提交）
* 普通作业文件上传到远端独立目录
* 支持 `.py`、`.sh`、`.slurm`、`.sbatch` 文件
* 危险命令检测（`rm -rf`、`shutdown`、`reboot`、`mkfs` 等会被拒绝）

### 作业查询与监控
* 作业状态查询（squeue / sacct）
* stdout / stderr 读取
* `诊断作业 JOBID` 汇总状态、输出、错误日志和下一步建议
* 查看最近作业、查看作业详情、列出本地 VASP 作业
* Textual TUI 实时 Job Monitor（右侧面板，5 秒自动刷新）
* 多 Job 同时监控，Tab 切换
* 监控面板显示：Job ID、State、Elapsed、Remote Dir、stdout/stderr 尾部摘录
* VASP 作业监控时附带实时错误诊断

### 远端作业管理
* 列出远端普通作业编号（扫描 `HPC_REMOTE_WORKDIR` 下 Agent 管理的作业目录）
* 按 Job ID 清理远端普通作业文件（保留根目录）
* 清理全部远端普通作业文件（双重确认）
* 列出远端 VASP 作业（输入/输出目录）
* 按目录名清理远端 VASP 作业
* 清理全部远端 VASP 作业文件

### VASP 作业
* VASP sbatch 脚本生成（结构优化/静态计算/其他计算类型）
* 根据本地 VASP 作业目录中已有 `POTCAR` 生成 `INCAR`、`KPOINTS`、`POSCAR`
* 支持通过自然语言或 `/vasp gen` 覆盖 `ENCUT`、`KPOINTS`、计算类型等输入参数
* 已有 VASP 配置文件时先确认，回复 `确认覆盖` 或 `覆盖已有配置文件` 后才覆盖
* VASP 固定目录提交：本地 input → 远端 input → 远端 output
* 重复提交同名 VASP 作业时支持覆盖旧结果、自动创建新 run name 或取消
* 登记已有 VASP 作业，便于继续查询和同步
* VASP 输出同步到本地（按 include/exclude 规则过滤文件）
* VASP 远程文件探针与错误诊断
* OUTCAR / OSZICAR 确定性解析
* Claude Code 报告生成（report.md / paper_methods.md / paper_results.md）
* 一键分析（同步 + report_context + Claude Code 报告全流程）

### 错误诊断
* 基于真实案例库 + 通用错误库的错误日志诊断
* 配置检查会覆盖 `.env`、SSH key、本地/远端目录、VASP 命令、partition、Claude Code/API 等常见问题，并给出修复建议
* 新错误可半自动整理为真实案例草稿，确认后写入案例库
* 自动修复 sbatch 脚本（OOM → 提高内存、TIME → 延长时间等）
* Pending / 不运行作业排查

### 交互界面
* **Textual TUI**：全屏终端界面，Chat + Job Monitor 双面板

### 其他特性
* Claude Code 集成（通过 `skills/vasp_report/SKILL.md` 定义分析 Skill）
* 本地 JSON 作业登记（job_registry.json）
* 本地作业记录状态查看、预览归档、确认归档、归档恢复
* Chat 结果区支持鼠标选择文本；`Ctrl+Y` 优先复制选中文本，没有选中文本时复制上一条 Agent 回复
* `/help`、`/help job`、`/help vasp` 快捷帮助入口
* 全面测试体系（本地 + Live HPC）

---

## 2. 安装依赖

推荐使用 `uv`：

```bash
uv sync
```

如果使用传统虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
uv sync
```

核心依赖包括：

```text
paramiko
python-dotenv
rich
textual
jieba
requests
scikit-learn
openai
anthropic
```

---

## 3. 配置 `.env`

项目根目录需要 `.env`。示例：

```env
PARATERA_BASE_URL=https://your-api-base-url
PARATERA_API_KEY=your-api-key
PARATERA_MODEL=DeepSeek-V4-Pro

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
HPC_VASP_SETUP_COMMAND=source /path/to/vasp/env/setup.sh
HPC_VASP_COMMAND=mpirun /path/to/vasp/bin/vasp_std
HPC_VASP_MODULE=

HPC_CLAUDE_CODE_COMMAND=claude
HPC_CLAUDE_CODE_MODEL=DeepSeek-V4-Pro
HPC_CLAUDE_CODE_TIMEOUT_SECONDS=1800
```

字段说明：

* `PARATERA_BASE_URL`：LLM API 服务地址。
* `PARATERA_API_KEY`：LLM API Key。
* `PARATERA_MODEL`：Agent 主体使用的模型名，覆盖普通问答/RAG、意图分类 fallback 和脚本辅助生成；不影响 Claude Code VASP 报告模型。
* `HPC_HOST`：超算 SSH 登录主机。
* `HPC_USERNAME`：超算用户名，按集群要求填写。
* `HPC_KEY_PATH`：本机 SSH 私钥绝对路径（Ed25519 格式）。
* `HPC_LOCAL_WORKDIR`：本地普通作业/测试文件工作目录；裸文件名查找会同时搜索当前启动目录和该目录。
* `HPC_REMOTE_WORKDIR`：普通 Slurm 作业远端根目录。
* `HPC_DEFAULT_PARTITION`：普通作业默认 partition；留空表示不写 `#SBATCH --partition`，使用集群默认分区。
* `HPC_LOCAL_VASP_JOBS_INPUT_DIR`：本地 VASP 输入作业根目录，每个子目录对应一次 VASP 作业输入。
* `HPC_LOCAL_VASP_JOBS_OUTPUT_DIR`：本地 VASP 输出根目录，用来保存从远端 output 同步回来的结果和 `analysis/`。
* `HPC_VASP_REMOTE_INPUT_DIR`：VASP 远端输入根目录。
* `HPC_VASP_REMOTE_OUTPUT_DIR`：VASP 远端输出/运行根目录。
* `HPC_VASP_PARTITION`：VASP 作业默认 partition；留空表示不写 `#SBATCH --partition`，使用集群默认分区。
* `HPC_VASP_SETUP_COMMAND`：VASP 运行前环境初始化命令。当前集群的 Intel MPI `mpirun` 需要先 source Intel 环境。
* `HPC_VASP_COMMAND`：VASP 主程序启动命令。请按当前超算实际 VASP 安装路径填写；普通 MPI/hostname 测试使用 `srun`。
* `HPC_VASP_MODULE`：可选模块名，留空表示不执行 `module load`。
* `HPC_CLAUDE_CODE_COMMAND`：Claude Code 命令，默认 `claude`。
* `HPC_CLAUDE_CODE_MODEL`：Claude Code 使用的模型名；留空时使用环境默认，Paratera 网关默认回退到 `DeepSeek-V4-Pro`。
* `HPC_CLAUDE_CODE_TIMEOUT_SECONDS`：Claude Code 报告生成超时时间，默认 1800 秒。

Claude Code 报告生成会把 `PARATERA_API_KEY` 同时传给 `ANTHROPIC_API_KEY` 和 `ANTHROPIC_AUTH_TOKEN`，并把 `PARATERA_BASE_URL` 传给 `ANTHROPIC_BASE_URL`。如果报告生成出现认证错误，先检查 key 是否过期、是否支持 `HPC_CLAUDE_CODE_MODEL`。

配置检查：

```bash
# 检查本地路径
realpath -e /path/to/your/private/key
realpath /path/to/local/vasp-jobs-input
realpath /path/to/local/vasp-jobs-output

# 如果本地 VASP 根目录不存在
mkdir -p /path/to/local/vasp-jobs-input /path/to/local/vasp-jobs-output
```

`.env` 不应提交到 Git（已在 `.gitignore` 中排除）。

---

## 4. 启动方式

统一入口：

```bash
python app.py
```

启动后会直接进入 Textual TUI。

退出方式：

* **TUI**：按 `Ctrl+X`、`F10` 或 `q`。

---

## 5. Textual TUI 使用

### 布局

* **顶部**：HPC 连接信息、用户、远端作业目录、快捷键。
* **左侧**：Chat 对话区（消息气泡 + 面板）。
* **右侧**：Job Monitor（Job ID、State、Elapsed、Dir、Last Output、VASP 诊断）。
* **底部**：固定输入框。

### 快捷键

```text
Ctrl+R  手动刷新当前监控 Job
Ctrl+Y  复制选中的 Chat 文本；没有选中文本时复制上一条 Agent 回复
Ctrl+S  确认提交等待中的作业
Tab     切换右侧正在监控的 Job
Esc     取消等待确认的提交或清理
Ctrl+X  退出
F10     退出
q       退出
```

### 新手自检命令

```text
查看当前模型
```

显示 Agent 主体模型、Claude Code VASP 报告模型、LLM 网关和主要超算目录配置，不会显示 API Key 明文。

```text
检查我的超算配置
```

检查本地目录、SSH key、远端普通作业目录和 VASP input/output 目录是否配置并可写。发现 WARN 时会同时给出修复建议；当前版本只给建议，不会自动修改 `.env`、创建目录或执行 chmod。

覆盖的配置问题包括：

* `.env` 缺关键字段
* SSH key 不存在或权限过宽
* 本地工作目录不存在或不可写
* 远端普通作业目录不存在或不可写
* VASP input/output 远端目录不存在或不可写
* `HPC_VASP_COMMAND` 指向的命令或绝对路径不可执行
* `HPC_VASP_SETUP_COMMAND` 执行后仍找不到 `mpirun` 或 VASP 启动命令
* `HPC_DEFAULT_PARTITION` / `HPC_VASP_PARTITION` 配错或不可用
* Claude Code / API 配置缺失或不可用

```text
一键测试超算提交流程
```

生成一个最小 `hostname` Slurm 作业提交预览，用来验证普通作业的 sbatch、上传和远端日志链路；仍需回复“确认提交”后才会真正提交。

### 监控规则

* TUI 未开始监控时不会实时读取日志；输入 `监控 JOBID` 后才开始刷新该 Job。
* 只有输入 `监控 JOBID` 后，右侧才开始显示该 Job。
* 已完成、失败或不在队列中的 Job 不会被加入监控面板。
* 运行中的多个 Job 可以同时加入监控，按 `Tab` 切换显示。
* Job 失败后会从右侧监控列表移除，并提示可直接输入的下一步命令。
* Job 完成后会停止刷新，保留最终状态和输出摘要。
* 每 5 秒自动刷新一次（squeue/sacct 状态 + stdout/stderr 尾部 50 行）。

### 诊断作业

```text
诊断作业 11838843
诊断刚才那个作业
```

Agent 会汇总作业状态、错误日志、标准输出摘要，并给出下一步命令。VASP 作业会额外建议同步输出和一键分析。

### VASP 实时诊断（TUI）

VASP 作业在监控时会自动进行远程探针诊断：
* 检查远端 output 目录中的关键文件（INCAR、POSCAR、KPOINTS、OUTCAR、OSZICAR、vasprun.xml、CONTCAR、vasp.out 等）
* 匹配错误规则：POTCAR 输入转换错误、Fortran 严重错误、OOM、Segfault、磁盘满、Walltime 超限、文件缺失等
* 匹配警告规则：BRMIX 电荷混合、ZBRENT 电子收敛问题等
* 诊断结果显示在 Job Monitor 面板中，包含严重级别（ok/warning/error）、具体问题和修复建议

### VASP 长工作流（TUI 特有）

在 TUI 中输入 `运行并分析` 可以触发自动化周期：
1. 提交 VASP 作业
2. 监控作业直到完成
3. 同步输出到本地
4. 自动生成 Claude Code 报告

### 剪贴板支持

Chat 对话区支持鼠标拖动选择文本。选中文本后按 `Ctrl+Y` 会复制当前选区；没有选区时，`Ctrl+Y` 会复制上一条 Agent 回复。

`Ctrl+Y` 依次尝试以下剪贴板工具：
* `pyperclip`（Python 包）
* `wl-copy`（Wayland）
* `xclip`、`xsel`（X11）
* `pbcopy`（macOS）
* `clip`（WSL）
* `powershell.exe`（Windows）

---

## 6. 普通 Slurm 作业提交

### 最短用法

```text
跑 train.py
```

### 指定资源

```text
跑 train.py，4核，15分钟
帮我提交 ./run.sh，2核，30分钟
帮我提交一个作业运行 python train.py，8核，1小时，16G内存
```

### 支持的文件类型

```text
.py
.sh
.slurm
.sbatch
```

### 提交流程

1. 用户输入提交请求。
2. Agent 读取本地文件，推断运行命令（`.py` → `python3 file`，`.sh` → `bash file`）。
3. 如果用户没有指定资源，Agent 根据文件内容补充推荐参数。
4. Agent 生成并展示 `job.sh` 预览。
5. 用户回复 `确认提交` 或按 `Ctrl+S`。
6. Agent 连接超算，把文件上传到远端独立目录，并执行 `sbatch job.sh`。

### 带附件提交（TUI）

如果提交时没有显式指定文件路径，Agent 会询问是否上传附件。用户可提供本地文件路径，Agent 会将其作为附件一并上传到远端作业目录。

### 确认与取消

```text
确认提交
```

```text
取消提交
```

### 文件路径说明

相对路径：

```text
跑 examples/my_job.py，2核，10分钟
```

绝对路径：

```text
提交 /path/to/jobs/train.py，4核，1小时
```

裸文件名：

```text
运行 test.py
```

Agent 会同时搜索当前启动目录和 `HPC_LOCAL_WORKDIR`。如果只找到一个同名文件，会自动上传该文件；如果找到多个同名文件，会要求你提供更具体的路径。

解释器规则：

* 只写 `.py` 文件名或上传 `.py` 附件时，Agent 默认使用 `python3 file.py`。
* 如果你明确写了 `python file.py`，Agent 会尊重你的命令，不会自动改成 `python3`。

### 远端目录结构

```text
HPC_REMOTE_WORKDIR/<jobid>-<jobname>/
├── job.sh
├── <上传或读取的作业文件>
├── hpc_agent_job_<jobid>.out
└── hpc_agent_job_<jobid>.err
```

---

## 7. 普通作业资源推荐规则

当你提交普通作业文件但没有指定资源时，Agent 会尝试读取文件内容并推荐参数。

示例：

```text
跑 monitor_cpu.py
```

如果检测到 Python 脚本，默认会按普通计算作业处理。常见增强规则：

* 检测到 `torch`、`tensorflow`、`keras`、`jax`：提高 CPU、内存和时间。
* 检测到 `cuda`：申请 1 张 GPU。
* 检测到 `mpi4py`、`mpirun`、`srun`：提高 CPU 数。
* 检测到较长循环或 `time.sleep`：延长运行时间。
* 检测到 `numpy`、`pandas`、`scipy`、`sklearn`：提高内存。

用户显式指定的参数优先，例如：

```text
跑 monitor_cpu.py，4核，15分钟
```

这里会使用用户指定的 `4核` 和 `15分钟`，忽略自动推荐。

### 按命令提取参数

用户可以在自然语言中指定参数：

```text
帮我提交一个作业运行 python train.py，4核，1小时，16G内存
job-name:train_job，2张GPU
```

Agent 会从文本中提取：
* CPU 核数：`(\d+) 核`
* 时间限制：`HH:MM:SS`、`(\d+) 分钟`、`(\d+) 小时`
* 内存：`(\d+)G`、`(\d+)GB内存`
* GPU 数量：`gpu:(\d+)`、`(\d+)张GPU`
* Job 名称：`job-name:xxx`

### Slurm 测试文件

Agent 支持生成安全测试文件：

```text
生成一个 sleep 60 的测试作业脚本
生成 hostname 测试作业
创建 srun -n 4 hostname 测试脚本并运行
```

普通 MPI/hostname 测试默认使用 Slurm 自带的 `srun -n N hostname`。如果你输入旧习惯的 `mpirun -np 4 hostname`，Agent 仍能识别意图，但生成的测试脚本会使用 `srun`。

---

## 8. 作业查询

### 查询状态

```text
查看 11814753 的状态
```

显示 squeue 和 sacct 结果。

### 读取标准输出

```text
读取 11814753 的输出
```

### 读取错误日志

```text
读取 11814753 的错误日志
```

### 路径解析规则

对于 Agent 提交并登记过的作业，日志会优先从登记的远端作业目录读取。

* 普通作业默认读取：`HPC_REMOTE_WORKDIR/<job-folder>/*.out`、`*.err`
* VASP 作业默认读取：`HPC_VASP_REMOTE_OUTPUT_DIR/<job-folder>/*.out`、`*.err`

### 诊断作业

```text
诊断作业 11814753
诊断刚才那个作业
```

Agent 会汇总 squeue/sacct 状态、stdout/stderr 摘要和本地 registry 线索，并给出下一步可执行命令。VASP 作业会额外结合远端 output 目录探针和 VASP 诊断规则。

---

## 9. 本地作业记录与生命周期

Agent 会把提交或登记过的作业写入本地 `data/jobs/job_registry.json`。这个记录只用于 Agent 查找路径、展示详情、同步 VASP 输出和生成报告；它不是 Slurm 队列本身。

### 查看最近作业

```text
查看最近作业
列出最近作业
```

显示最近的本地记录，包含 Job ID、作业类型、目录名和当前本地阶段。

### 查看作业详情

```text
查看作业详情 11814753
查看刚才那个作业详情
```

详情会显示普通/VASP 类型、远端工作目录、本地输出目录、raw_output/analysis 阶段，以及建议下一步命令。

### 列出本地 VASP 作业

```text
列出 VASP 作业
查看我的 VASP 作业
```

这个命令只看本地 `job_registry.json` 中记录过的 VASP 作业，不连接远端。它和“远端 VASP 目录有什么”不同。

### 查看本地作业记录状态

```text
查看本地作业记录状态
本地记录有多少作业
```

显示 registry 文件大小、总记录数、普通/VASP 数量、阶段分布和归档建议。

### 预览并归档本地作业记录

```text
预览归档本地作业记录，只保留最近 100 个
```

预览不会修改任何文件，只会告诉你将保留哪些记录、将归档哪些记录。确认后才会执行：

```text
确认归档本地作业记录
```

归档只移动 `data/jobs/job_registry.json` 里的旧记录到 `data/jobs/archive/` 下的归档 JSON 文件，不会删除本地输入目录、本地输出目录，也不会删除远端作业。

### 查看和恢复归档记录

```text
查看归档记录
预览恢复最近一次本地作业记录归档
恢复归档记录
```

恢复也会先预览。确认后执行：

```text
确认恢复本地作业记录归档
```

恢复只把归档文件中的缺失记录合并回 `job_registry.json`，不会重新提交作业，也不会改动远端目录。

---

## 10. TUI Job Monitor

### 开始监控

```text
监控 11814753
```

### 取消监控

```text
取消监控 11814753
```

### 监控面板内容

```text
Job        Slurm Job ID
State      squeue 状态（RUNNING/PENDING/COMPLETED/FAILED 等）
Elapsed    运行时间
Dir        远端作业目录
Last Output stdout 尾部 50 行
```

VASP 作业还会显示实时诊断结果。

### 规则

* 只监控运行中或排队中的 Job（通过 squeue/sacct 验证）。
* 已完成、失败、不在队列中的 Job 会被阻止加入监控。
* 多个 Job 同时监控时，按 `Tab` 切换。
* 切换监控 Job 不会在 Chat 中刷屏。
* `Ctrl+R` 手动刷新当前监控 Job（不等待 5 秒周期）。
* Job 失败后会从右侧面板移除，并提示可以诊断错误日志。
* Job 完成后会停止刷新，保留最终状态。

---

## 11. 列出远端作业

### 列出普通作业编号

```text
列出远端作业编号
```

扫描 `HPC_REMOTE_WORKDIR` 下由 Agent 管理的普通作业目录，提取 Job ID 列表。

### 列出远端 VASP 作业

```text
列出远端 VASP 作业
```

分别列出 `HPC_VASP_REMOTE_INPUT_DIR` 和 `HPC_VASP_REMOTE_OUTPUT_DIR` 下的子目录。

---

## 12. 远端作业清理

### 清理单个普通作业

```text
清理远端作业 11817627 的文件
```

Agent 会先展示将删除的目录或文件。确认：

```text
确认清理
```

取消：

```text
取消清理
```

### 清理全部普通作业

```text
清理远端普通作业目录下所有作业文件
```

确认全部清理必须输入完整短语：

```text
确认清理全部
```

### 清理单个 VASP 作业

```text
清理远端 VASP 作业 si_static_test 的文件
```

### 清理全部 VASP 作业

```text
清理全部远端 VASP 作业文件
```

### 安全边界

* 只清理 `HPC_REMOTE_WORKDIR` 下的一级文件和子目录（普通作业）。
* 保留 `HPC_REMOTE_WORKDIR` 根目录本身。
* VASP 清理同时作用于 input 和 output 目录。
* 清理前均需用户确认。

---

## 13. VASP 作业目录准备

当前 VASP 只保留固定目录提交逻辑。提交前，用户需要手动在本地准备完整 VASP 作业目录：

```text
$HPC_LOCAL_VASP_JOBS_INPUT_DIR/<job-folder>/
├── INCAR
├── KPOINTS
├── POSCAR
└── POTCAR
```

可以放额外文件，Agent 会一起上传。目录必须包含四个必需文件：

```text
INCAR
KPOINTS
POSCAR
POTCAR
```

注意：

* Agent 不会生成真实 `POTCAR`。
* `POTCAR` 需要来自你有权限使用的 VASP 赝势库。
* 没有真实合法 `POTCAR` 时，真实 VASP 计算通常无法得到正常完整输出。

### 基于已有 POTCAR 生成配置文件

如果作业目录里已经放好了真实 `POTCAR`，可以让 Agent 生成其余三个输入文件：

```text
帮我生成我的 VASP 作业 Al_test 的配置文件
```

也可以显式覆盖测试参数：

```text
/vasp gen Al_test --type static --encut 400 --kpoints 2x2x2
帮我生成 Al_test 的 VASP 输入，ENCUT 400，KPOINTS 2x2x2，静态计算
/vasp gen Si_relax --type relax --encut 520 --kpoints 3x3x3 --nsw 20
```

Agent 会在 `$HPC_LOCAL_VASP_JOBS_INPUT_DIR/Al_test/` 中读取 `POTCAR`，解析元素顺序和 `ENMAX`，然后写入：

```text
INCAR
KPOINTS
POSCAR
```

注意：

* Agent 只读取 `POTCAR` 的 `TITEL`、`ENMAX`、`ZVAL` 等少量元信息，不会生成或回显真实 `POTCAR` 内容。
* 用户显式参数优先，其次使用 `POTCAR` 中的 `ENMAX` 推荐 `ENCUT`，最后才使用 Agent 默认测试参数。
* 当前支持覆盖：`type`/计算类型、`ENCUT`、`KPOINTS`、`NSW`、`EDIFF`、`ISMEAR`、`SIGMA`、`overwrite`/覆盖。
* 如果 `INCAR`、`KPOINTS` 或 `POSCAR` 已存在，Agent 不会直接覆盖，会提示确认；回复 `确认覆盖`、`覆盖已有配置文件` 或 `继续` 后才会重新生成并写入。
* 如果用户没有提供晶体结构、晶格常数或原子坐标，Agent 会生成默认 smoke test 结构，只用于测试 VASP 能否启动、POTCAR 是否可读、提交流程是否正常。
* 默认单元素使用 fcc smoke test（Si 使用 diamond），双元素使用 rocksalt smoke test；三个及以上元素不会自动猜结构，会要求用户补充结构信息。
* smoke test 输入不代表真实材料结构，不能直接用于正式科研结论。

---

## 14. VASP 作业提交

### 提交最近保存的完整 VASP 作业

```text
帮我提交最近的 VASP 作业，1 个节点 32 核，运行 10 分钟
```

### 提交指定子目录

```text
帮我提交 VASP 作业，目录名 si_static_test，1 个节点 32 核，运行 10 分钟
```

### 提交指定绝对路径

```text
帮我提交 VASP 作业，目录 /path/to/local/vasp-jobs/si_static_test，1 个节点 32 核，运行 10 分钟
```

### 确认

```text
确认提交
```

### 同名作业处理

提交 VASP 作业时，如果远端 output 目录或本地 output 目录已经存在，Agent 会先提示选择：

```text
覆盖旧结果
自动创建新 run name
取消
```

选择覆盖旧结果时，Agent 会先清空这些目录后再重新提交：

```text
HPC_VASP_REMOTE_INPUT_DIR/<job-folder>/
HPC_VASP_REMOTE_OUTPUT_DIR/<job-folder>/
HPC_LOCAL_VASP_JOBS_OUTPUT_DIR/<job-folder>/
```

这样可以避免同名目录里残留旧的 `OUTCAR`、`OSZICAR`、日志或分析文件，导致新旧结果混用。选择自动创建新 run name 时，Agent 会使用类似 `<job-folder>_YYYYMMDD_HHMM` 的目录名提交新任务，原目录不变。

### 提交过程

提交时 Agent 会：

1. 在 `HPC_LOCAL_VASP_JOBS_INPUT_DIR` 中选择完整作业目录。
2. 校验 `INCAR`、`KPOINTS`、`POSCAR`、`POTCAR` 四个文件都存在。
3. 生成 `job.sh` 并写入本地作业目录。
4. 上传全部输入文件到 `HPC_VASP_REMOTE_INPUT_DIR/<job-folder>`。
5. 在 `HPC_VASP_REMOTE_OUTPUT_DIR/<job-folder>` 写入远端 `job.sh`。
6. 远端 `job.sh` 运行时从 input 目录复制输入文件到 output 目录。
7. 在 output 目录执行 VASP。
8. 登记 Job ID、远端路径和本地 output/analysis 路径到 `job_registry.json`。

VASP 标准输出、错误日志和运行结果都会写入远端 output 目录。

### VASP 环境配置

当前默认 VASP 启动方式：

```bash
source /path/to/vasp/env/setup.sh
mpirun /path/to/vasp/bin/vasp_std
```

普通 MPI/hostname 测试默认使用 `srun`，但 VASP 默认仍使用 `mpirun`。原因是当前集群的 VASP 依赖 Intel MPI 环境，`HPC_VASP_SETUP_COMMAND` 执行后才会提供可用的 `mpirun`。

如果你的集群 VASP 启动方式不同，请修改 `.env`：

```env
HPC_VASP_SETUP_COMMAND=...
HPC_VASP_COMMAND=...
HPC_VASP_MODULE=
```

---

## 15. VASP 输出同步

### 同步命令

```text
同步 VASP 作业 11817144 输出到本地
```

或使用目录名：

```text
同步 VASP 作业 si_static_test 输出到本地
```

### 同步后目录结构

```text
$HPC_LOCAL_VASP_JOBS_OUTPUT_DIR/<job-folder>/
├── raw_output/
│   ├── INCAR
│   ├── KPOINTS
│   ├── POSCAR
│   ├── OUTCAR
│   ├── OSZICAR
│   ├── CONTCAR
│   ├── vasprun.xml
│   ├── *.out
│   └── *.err
└── analysis/
    ├── file_manifest.json
    └── report_context.md
```

### 同步规则

**包含**（从远端拉取）：
* INCAR、POSCAR、KPOINTS
* OUTCAR、OSZICAR、CONTCAR、vasprun.xml
* *.out、*.err

**排除**（不同步，避免超大文件）：
* WAVECAR、CHGCAR、AECCAR*、POTCAR

---

## 16. VASP 报告生成

### 一键分析（推荐）

一键分析自动完成同步 + report_context 生成 + Claude Code 报告生成全流程：

```text
一键分析 VASP 作业 si_static_test
```

或使用 Job ID：

```text
一键分析 VASP 作业 11817144
```

### 分步执行

先同步：

```text
同步 VASP 作业 11817144 输出到本地
```

再生成报告：

```text
生成 VASP 作业 si_static_test 报告
生成 VASP 作业 11817144 报告
```

### 报告产物

```text
$HPC_LOCAL_VASP_JOBS_OUTPUT_DIR/<job-folder>/analysis/
├── report.md           # 中文用户报告
├── paper_methods.md    # 英文论文方法描述
└── paper_results.md    # 英文论文结果描述
```

### report_context.md 内容

`report_context.md` 是 Claude Code 生成报告的受控输入，包含：

* **VASP 确定性事实**（从 OUTCAR/OSZICAR 解析）：
  - 收敛状态（达到精度 / EDIFF 中止）
  - 自由能：TOTEN、energy without entropy、energy sigma→0
  - E-fermi、ISMEAR、SIGMA、NELECT
  - 晶胞体积、晶格矢量、ENCUT
  - 应力张量、外部压强
  - 力：最大 |force|、平均力范数
  - 计算耗时：CPU 时间、经历时间、最大内存
  - 能带结构：VBM、CBM、带隙
  - 离子种类、数量、原子质量
  - DAV/RMM 迭代次数、能量路径
* **文件清单**（raw_output 下文件名和大小）
* **INCAR 参数摘要**（键值对）
* **KPOINTS 摘要**（模式、网格、偏移）
* **POSCAR 摘要**（元素种类、数量、总原子数）
* **轻量级诊断**（空文件、小文件、POTCAR/收敛问题）
* **日志摘要**（stderr、stdout、vasp.out 尾部）

### Claude Code 调用

报告生成通过 `modules/vasp/claude_code_reporter.py` 调用 `claude` CLI：

* 加载 `skills/vasp_report/SKILL.md` 作为分析指令
* 该 Skill 严格约束 Claude Code 只使用 `analysis/report_context.md`
* 不直接读取大体积原始输出文件
* 不编造未在上下文中确认的科学结果
* Claude Code 使用 `--bare` 模式，只返回 JSON；`report.md`、`paper_methods.md`、`paper_results.md` 由 Python 写入
* 超时时间由 `HPC_CLAUDE_CODE_TIMEOUT_SECONDS` 控制（默认 1800 秒）
* 调用结果会显示 Claude Code 实际耗时

---

## 17. VASP 脚本生成

### 结构优化

```text
帮我生成一个 VASP 结构优化脚本，1 个节点，每节点 32 核，运行 24 小时
```

### 静态计算

```text
帮我生成 VASP 静态计算脚本，1 个节点 32 核，运行 2 小时
```

### 说明

* 脚本生成只生成 `job.sh` 内容预览，不会上传文件或提交。
* 真正提交必须走固定目录流程（准备输入目录 → 提交）。
* VASP 请求中如果包含危险命令，Agent 会拒绝生成脚本。
* 生成的脚本包含输入文件检查、环境设置和 VASP 启动命令。

---

## 18. 登记已有 VASP 作业

如果某个 VASP 作业已经在超算上提交过，可以把 Job ID 和远端输出目录登记到本地 registry：

```text
登记 VASP 作业 11817144，目录名 si_static_test
```

或者提供远端绝对路径：

```text
登记 VASP 作业 11817144，目录 /path/to/remote/vasp-hpc-jobs-output/si_static_test
```

登记后可以继续使用全套功能：

```text
查看 11817144 的状态
读取 11817144 的输出
读取 11817144 的错误日志
同步 VASP 作业 11817144 输出到本地
生成 VASP 作业 11817144 报告
一键分析 VASP 作业 11817144
```

---

## 19. TUI 操作覆盖

Textual TUI 覆盖聊天式文本输入、Intent 检测结果展示、普通作业提交预览和确认/取消、作业状态/输出/错误日志查询、作业诊断、最近作业/作业详情/本地 VASP 作业列表、本地作业记录归档与恢复确认、远端普通作业编号列表和清理确认、VASP 输入生成和覆盖确认、VASP 固定目录提交预览和确认、同名 VASP 结果覆盖/新 run/cancel 选择、远端 VASP 作业列表和清理确认，以及清理确认状态机（含 "确认清理全部" 双重确认）。

### 快捷帮助

```text
/help
/help job
/help vasp
```

`/help` 显示通用快捷入口；`/help job` 聚合作业查询、监控、清理、记录归档等常用命令；`/help vasp` 聚合 VASP 输入生成、提交、同步、报告和清理命令。

---

## 20. 错误诊断和 Pending 排查

### 粘贴错误日志

直接粘贴报错内容即可诊断：

```text
CUDA out of memory
ModuleNotFoundError: No module named numpy
sbatch: error: Batch job submission failed: Invalid partition name specified
python: can't open file 'monitor_cpu.py': [Errno 2] No such file or directory
```

### 整理为真实案例

遇到新的真实错误时，可以让 Agent 生成案例草稿：

```text
把这个错误整理成案例：Missing required VASP input file: POTCAR
```

也可以先粘贴/诊断一段错误日志，再输入：

```text
把这个错误整理成案例
```

Agent 会生成 `real_cases.json` 草稿，并等待确认。回复“确认”才会写入错误案例库；回复“取消”则放弃。这个流程会补齐 `applies_to`、`confidence`、`patterns`、`evidence`、`suggestions`、`commands` 等字段。

案例草稿会尽量脱敏用户名、主机名、本地绝对路径、远端家目录、API key/token 等信息。确认写入前仍建议人工扫一遍草稿，确保没有保留个人路径、账号或机构内部地址。

### 错误类型覆盖

错误诊断包含两层：

* `data/errors/real_cases.json`：真实错误案例库，优先匹配，输出证据、原因、修复建议、排查命令和下次避免方式。
* `data/errors/generic_errors.json`：通用错误模式库，作为兜底匹配。
* `data/errors/README.md`：错误知识库维护说明，记录真实案例和通用错误的边界。

真实案例库覆盖：

| 领域 | 真实案例 |
|------|----------|
| VASP | 缺 POTCAR、POTCAR 无效、VASP 命令不可用、MPI 环境未初始化、POSCAR/POTCAR 不一致、时间限制、电子收敛问题、缺 OUTCAR、报告上下文生成失败 |
| Slurm | partition 不存在或无权限、OOM、远端工作目录不可写、作业完成后 squeue 查不到 |
| config | `.env` 缺关键字段、SSH 私钥权限过宽 |
| claude | Claude Code 命令不存在、API Key 或模型网关配置错误 |
| sync/agent/tui | 远端输出同步为空、SFTP/SSH 传输失败、同名目录旧结果混入、剪贴板不可用、找不到上一个作业记录 |

通用错误数据库包含 18 类错误模式，按类别分：

| 类别 | 错误示例 |
|------|----------|
| memory | OOM、CUDA out of memory、GPU OOM |
| permission | Permission denied |
| slurm | Invalid partition、node config、PENDING |
| storage | Disk quota exceeded、No space |
| file | File not found、No such file |
| python | ModuleNotFoundError、ImportError |
| environment | Command not found |
| compile | Compilation error |
| gpu | GPU unavailable、CUDA not found |
| ssh | Connection refused、Host key |

### 自动修复 sbatch 脚本

诊断后会根据错误类型建议修改 sbatch 脚本：

| 错误 | 自动修复 |
|------|----------|
| OOM | 添加 `--mem=16G` |
| TIME | 添加 `--time=04:00:00` 或 `--time=02:00:00` |
| partition 无效 | 添加 `--partition=general` |
| nodes/cpus | 添加 `--nodes=1 --cpus-per-task=4` |
| GPU OOM | 添加 `--gres=gpu:1 --mem=32G` |
| No CUDA | 添加 `--gres=gpu:1` + `module load cuda` |

### Pending 排查

```text
我的任务一直 pending
我的任务一直不运行
为什么作业没有开始
```

Agent 会分析可能的 Pending 原因（QoS、partition、资源不足、维护等）并给出排查建议。

### 从 Job Monitor 触发诊断

如果 Job Monitor 提示可诊断错误日志，先读取 stderr：

```text
读取 11814753 的错误日志
```

然后把错误内容交给 Agent 诊断。

---

## 21. 知识库问答

HPC Agent 内置了 RAG 知识库，可以用自然语言询问 Slurm/HPC 相关问题。

### 示例

```text
什么是 sbatch
squeue 是干什么的
怎么取消作业
GPU 作业怎么提交
集群有哪些分区
```

### 工作原理

1. 用户问题通过 jieba 分词后，用 TF-IDF 向量化
2. 在知识库文档（`data/hpc_documents/`）中做余弦相似度检索
3. 检索到最相关的 3 个文本块后，交给 `PARATERA_MODEL` 配置的模型生成自然语言回答
4. 回答以中文为主，力求简洁准确

---

## 22. 测试和检查

### 本地全量检查

```bash
.venv/bin/python tests/run_all_checks.py
```

包含以下检查：

1. **Python Syntax Check**：编译所有模块文件
2. **Slurm Assistant Skill Checks**：测试脚本生成、参数提取
3. **Error Diagnoser Skill Checks**：测试错误匹配和修复建议
4. **VASP Assistant Skill Checks**：测试 VASP 脚本生成
5. **Router Intent Detection Checks**：基于 `tests/fixtures/route_cases.json` 测试自然语言意图识别、风险等级和解释信息
6. **Job Query Parsing Checks**：测试 Job ID 提取等
7. **Submit Preview Checks**：测试文件上传、命令推断、资源推荐
8. **Job Lifecycle Checks**：测试最近作业、详情、本地 VASP 作业、归档预览/恢复
9. **VASP Tool Checks**：测试 VASP 输入生成、提交预览、同步和报告链路
10. **HPC Env Config Checks**：检查 `.env` 配置是否有效

### SSH 连接检查

```bash
.venv/bin/python tests/slurm/test_ssh.py
```

### 真实超算工作流检查

```bash
.venv/bin/python tests/run_all_checks.py --live-hpc
```

注意：`--live-hpc` 会连接超算并提交真实 Slurm 测试作业。

### TUI 手动测试流程

```text
什么是 sbatch
跑 /path/to/your_script.py，4核，15分钟
确认提交
监控 JOBID
读取 JOBID 的输出
取消监控 JOBID
```

---

## 23. 常用命令合集

```text
# Slurm 知识
什么是 sbatch
squeue 是干什么的
怎么取消作业

# 普通作业脚本生成
帮我写一个 sbatch 脚本运行 python train.py，4核，10分钟

# 普通作业提交
跑 train.py
跑 train.py，4核，15分钟
帮我提交 ./run.sh，2核，30分钟
帮我提交一个作业运行 python train.py，8核，1小时，16G内存
创建 srun -n 4 hostname 测试脚本并运行
确认提交
取消提交

# 作业查询
查看 11814753 的状态
读取 11814753 的输出
读取 11814753 的错误日志
诊断作业 11814753

# 本地作业记录
查看最近作业
查看作业详情 11814753
列出 VASP 作业
查看本地作业记录状态
预览归档本地作业记录，只保留最近 100 个
确认归档本地作业记录
查看归档记录
预览恢复最近一次本地作业记录归档
确认恢复本地作业记录归档

# TUI 监控
监控 11814753
取消监控 11814753

# 远端作业列表
列出远端作业编号
列出远端 VASP 作业

# 远端作业清理
清理远端作业 11817627 的文件
确认清理
清理远端普通作业目录下所有作业文件
确认清理全部
清理远端 VASP 作业 si_static_test 的文件
清理全部远端 VASP 作业文件

# VASP 脚本生成
帮我生成一个 VASP 结构优化脚本，1 个节点，每节点 32 核，运行 24 小时
帮我生成 VASP 静态计算脚本，1 个节点 32 核，运行 2 小时
帮我生成我的 VASP 作业 Al_test 的配置文件
帮我生成 Al_test 的 VASP 输入，ENCUT 400，KPOINTS 2x2x2，静态计算
/vasp gen Al_test --type static --encut 400 --kpoints 2x2x2
确认覆盖

# VASP 提交
帮我提交最近的 VASP 作业，1 个节点 32 核，运行 10 分钟
帮我提交 VASP 作业，目录名 si_static_test，1 个节点 32 核，运行 10 分钟
覆盖旧结果
自动创建新 run name

# VASP 同步与报告
同步 VASP 作业 11817144 输出到本地
生成 VASP 作业 si_static_test 报告
一键分析 VASP 作业 si_static_test

# 登记已有 VASP 作业
登记 VASP 作业 11817144，目录名 si_static_test

# 错误诊断
CUDA out of memory
ModuleNotFoundError: No module named numpy
sbatch: error: Batch job submission failed: Invalid partition name specified
我的任务一直 pending
```

---

## 24. 当前限制

* 提交和清理操作需要用户确认。
* 远端清理只作用于普通作业目录 `HPC_REMOTE_WORKDIR` 或 VASP 作业目录。
* VASP 提交前必须准备完整本地目录（含 `INCAR`、`KPOINTS`、`POSCAR`、`POTCAR`）。Agent 可以在已有 `POTCAR` 的前提下生成其余三个文件，但无结构参数时只生成 smoke test 输入。
* Agent 不会生成真实 `POTCAR`，`POTCAR` 需要来自有权限使用的 VASP 赝势库。
* 本地作业记录归档/恢复只修改 `job_registry.json` 及归档 JSON，不删除真实作业目录，也不恢复远端已删除文件。
* TUI 监控只加入运行中或排队中的 Job。
* 当前不做 GPU 利用率实时监控。
* 聊天历史不持久化。
* Claude Code 报告生成需要本地安装 `claude` 命令行工具并配置相应的 API Key。

---

## 25. 故障排查

### Textual 未安装

错误信息：

```text
Textual 依赖尚未安装
```

处理：

```bash
uv sync
```

### SSH 连接失败

* 检查 `HPC_HOST`、`HPC_USERNAME`、`HPC_KEY_PATH`。
* 确认私钥文件存在且权限正确（建议 600）。
* 确认使用 Ed25519 或 RSA 格式私钥。
* 手动测试 SSH：

```bash
ssh -i /path/to/your/private/key -l 'your-hpc-username' your-hpc-host
```

### 普通作业提示找不到文件

* 相对路径是相对于当前启动目录解析的。
* 裸文件名会同时在当前启动目录和 `HPC_LOCAL_WORKDIR` 中查找。
* 文件不在项目目录时使用绝对路径。
* 脚本内部引用的其他文件也需要作为附件上传或改成脚本运行目录下可访问的路径。

### VASP 提示缺少输入文件

* 检查本地目录是否在 `HPC_LOCAL_VASP_JOBS_INPUT_DIR` 下。
* 检查是否包含 `INCAR`、`KPOINTS`、`POSCAR`、`POTCAR` 四个必需文件。
* 如果使用绝对路径，确认路径拼写正确。
* POTCAR 必须是真实赝势文件，不能是占位符或空文件。

### 剪贴板不可用（TUI Ctrl+Y）

* TUI 的 `Ctrl+Y` 会依次尝试 `pyperclip`、`wl-copy`、`xclip`、`xsel`、`pbcopy`、`clip`、`powershell.exe`。
* 如果当前环境没有可用剪贴板命令，会在 Chat 里提示错误。
* 可以手动安装一个：`pip install pyperclip` 或 `apt install xclip`。

### Claude Code 报告生成失败

* 检查 `HPC_CLAUDE_CODE_COMMAND` 是否正确（默认 `claude`）。
* 确认 `claude` 命令在当前 PATH 中（`which claude`）。
* 检查 API Key 是否正确配置，是否过期，以及是否支持 `HPC_CLAUDE_CODE_MODEL`。
* Paratera 网关下，Agent 会把 `PARATERA_API_KEY` 同时传给 `ANTHROPIC_API_KEY` 和 `ANTHROPIC_AUTH_TOKEN`。
* 检查 `HPC_CLAUDE_CODE_TIMEOUT_SECONDS` 是否足够（OUTCAR 较大时可能需要更长超时）。
* 确认 `analysis/report_context.md` 已通过同步步骤生成。

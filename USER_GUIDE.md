# HPC Agent 用户手册

本文档说明如何配置、启动和使用 HPC Agent。当前代码支持三种界面：Textual TUI、Terminal CLI 和 Web UI。普通 Slurm 作业和 VASP 作业使用不同流程，尤其是 VASP 只保留固定目录提交逻辑。

---

## 1. 功能总览

HPC Agent 当前支持：

* Slurm / HPC 知识问答
* 生成普通 sbatch 脚本
* 根据普通作业文件自动推荐 CPU、时间、内存、GPU 参数
* 普通 Slurm 作业确认式提交
* 普通作业文件上传到远端独立目录
* 作业状态查询
* stdout / stderr 读取
* Textual TUI 右侧 Job Monitor
* 多 Job 同时监控，并用 Tab 切换
* 复制上一条 Agent 回复
* 远端普通作业编号列表
* 远端普通作业文件清理
* 错误日志诊断
* Pending / 不运行任务排查
* VASP sbatch 脚本生成
* VASP 固定目录提交
* 登记已有 VASP 作业，便于继续查询日志
* Web UI 普通作业附件上传

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
fastapi
uvicorn
paramiko
python-dotenv
python-multipart
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

HPC_HOST=your-hpc-host
HPC_USERNAME=your-hpc-username
HPC_KEY_PATH=/path/to/your/private/key
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
HPC_CLAUDE_CODE_MODEL=
HPC_CLAUDE_CODE_TIMEOUT_SECONDS=1800
```

字段说明：

* `PARATERA_BASE_URL`：LLM API 服务地址。
* `PARATERA_API_KEY`：LLM API Key。
* `HPC_HOST`：超算 SSH 登录主机。
* `HPC_USERNAME`：超算用户名，按集群要求填写。
* `HPC_KEY_PATH`：本机 SSH 私钥绝对路径。
* `HPC_REMOTE_WORKDIR`：普通 Slurm 作业远端根目录。
* `HPC_DEFAULT_PARTITION`：普通作业默认 partition；留空表示不写 `#SBATCH --partition`，使用集群默认分区。
* `HPC_LOCAL_VASP_JOBS_INPUT_DIR`：本地 VASP 输入作业根目录，每个子目录对应一次 VASP 作业输入。
* `HPC_LOCAL_VASP_JOBS_OUTPUT_DIR`：本地 VASP 输出根目录，用来保存从远端 output 同步回来的结果和 `analysis/`。
* `HPC_VASP_REMOTE_INPUT_DIR`：VASP 远端输入根目录。
* `HPC_VASP_REMOTE_OUTPUT_DIR`：VASP 远端输出/运行根目录。
* `HPC_VASP_PARTITION`：VASP 作业默认 partition；留空表示不写 `#SBATCH --partition`，使用集群默认分区。
* `HPC_VASP_SETUP_COMMAND`：VASP 运行前环境初始化命令。
* `HPC_VASP_COMMAND`：VASP 主程序启动命令。
* `HPC_VASP_MODULE`：可选模块名，留空表示不执行 `module load`。
* `HPC_CLAUDE_CODE_COMMAND`：Claude Code 命令，默认 `claude`。
* `HPC_CLAUDE_CODE_MODEL`：Claude Code 使用的模型名；留空时使用环境默认，Paratera 网关默认回退到 `DeepSeek-V4-Pro`。
* `HPC_CLAUDE_CODE_TIMEOUT_SECONDS`：Claude Code 报告生成超时时间，默认 1800 秒。

检查本地路径：

```bash
realpath -e /path/to/your/private/key
realpath /path/to/local/vasp-jobs-input
realpath /path/to/local/vasp-jobs-output
```

如果本地 VASP 根目录不存在：

```bash
mkdir -p /path/to/local/vasp-jobs-input /path/to/local/vasp-jobs-output
```

---

## 4. 启动方式

统一入口：

```bash
python app.py
```

然后选择：

```text
1. Textual TUI 控制台模式
2. Terminal CLI 对话模式
3. Web 网页对话模式
```

Web UI 默认地址：

```text
http://127.0.0.1:8000
```

也可以直接启动 Web：

```bash
uvicorn web_app:app --reload
```

退出：

* TUI：按 `Ctrl+X`、`F10` 或 `q`。
* Terminal CLI：输入 `quit`。
* Web：在启动服务的终端按 `Ctrl+C`。

---

## 5. Textual TUI 使用

TUI 布局：

* 顶部：HPC 连接信息、用户、远端普通作业目录、快捷键。
* 左侧：Chat 对话区。
* 右侧：Job Monitor。
* 底部：固定输入框。

快捷键：

```text
Ctrl+R  手动刷新当前监控 Job
Ctrl+Y  复制上一条 Agent 回复
Ctrl+S  确认提交等待中的作业
Tab     切换右侧正在监控的 Job
Esc     取消等待确认的提交或清理
Ctrl+X  退出
F10     退出
q       退出
```

注意：

* TUI 未开始监控时不会主动读取日志；输入 `监控 JOBID` 后才会刷新该 Job 的状态和输出摘要。
* 只有输入 `监控 JOBID` 后，右侧才开始显示该 Job。
* 已完成、失败或不在队列中的 Job 不会被加入监控面板。
* 运行中的多个 Job 可以同时加入监控，按 `Tab` 切换显示。
* Job 失败后会从右侧监控列表移除，并提示可诊断错误日志。
* Job 完成后会停止刷新，保留最终状态和输出摘要。

---

## 6. 普通 Slurm 作业提交

最短用法：

```text
跑 train.py
```

指定资源：

```text
跑 train.py，4核，15分钟
帮我提交 ./run.sh，2核，30分钟
帮我提交一个作业运行 python train.py，8核，1小时，16G内存
```

支持的本地文件类型：

```text
.py
.sh
.slurm
.sbatch
```

普通作业提交流程：

1. 用户输入提交请求。
2. Agent 读取本地文件，推断运行命令。
3. 如果用户没有指定资源，Agent 根据文件内容补充推荐参数。
4. Agent 生成并展示 `job.sh`。
5. 用户回复 `确认提交` 或按 TUI 的 `Ctrl+S`。
6. Agent 连接超算，把文件上传到远端独立目录，并执行 `sbatch job.sh`。

确认提交：

```text
确认提交
```

取消提交：

```text
取消提交
```

如果文件在当前项目目录下，可以直接写相对路径：

```text
跑 examples/my_job.py，2核，10分钟
```

如果文件不在当前目录，建议写绝对路径：

```text
提交 /path/to/jobs/train.py，4核，1小时
```

普通作业远端目录内容一般包括：

```text
job.sh
用户上传或读取的作业文件
hpc_agent_job_<jobid>.out
hpc_agent_job_<jobid>.err
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

这里会使用用户指定的 `4核` 和 `15分钟`。

---

## 8. 作业查询

查询状态：

```text
查看 11814753 的状态
```

读取标准输出：

```text
读取 11814753 的输出
```

读取错误日志：

```text
读取 11814753 的错误日志
```

对于 Agent 提交并登记过的作业，日志会优先从登记的远端作业目录读取。

普通作业默认读取：

```text
HPC_REMOTE_WORKDIR/<job-folder>/*.out
HPC_REMOTE_WORKDIR/<job-folder>/*.err
```

VASP 作业默认读取：

```text
HPC_VASP_REMOTE_OUTPUT_DIR/<job-folder>/*.out
HPC_VASP_REMOTE_OUTPUT_DIR/<job-folder>/*.err
```

---

## 9. TUI Job Monitor

开始监控：

```text
监控 11814753
```

取消监控：

```text
取消监控 11814753
```

右侧 Job Monitor 会显示：

```text
Job
State
Elapsed
Dir
Last Output
```

规则：

* 只监控运行中或排队中的 Job。
* 已完成、失败、不在队列中的 Job 会被阻止加入监控。
* 多个 Job 同时监控时，按 `Tab` 切换。
* 切换监控 Job 不会在 Chat 中刷屏。
* `Ctrl+R` 手动刷新当前监控 Job。
* Job 失败后会从右侧面板移除，并提示可以诊断错误日志。

---

## 10. 远端普通作业编号列表

列出远端普通作业编号：

```text
列出远端作业编号
```

这个功能只扫描 `HPC_REMOTE_WORKDIR` 下由 Agent 管理的普通作业目录，不扫描 VASP input/output 目录。

---

## 11. 远端普通作业清理

按 Job ID 清理：

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

清理全部普通作业文件：

```text
清理远端普通作业目录下所有作业文件
```

确认全部清理必须输入完整短语：

```text
确认清理全部
```

安全边界：

* 只清理 `HPC_REMOTE_WORKDIR` 下的一级文件和子目录。
* 保留 `HPC_REMOTE_WORKDIR` 根目录本身。
* 不清理 VASP input/output 目录。

---

## 12. VASP 作业目录准备

当前 VASP 只保留固定目录提交逻辑。提交前，用户需要手动在本地准备完整 VASP 作业目录：

```text
$HPC_LOCAL_VASP_JOBS_INPUT_DIR/<job-folder>/
├── INCAR
├── KPOINTS
├── POSCAR
└── POTCAR
```

可以放额外普通文件，Agent 会一起上传。目录必须包含四个必需文件：

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

---

## 13. VASP 作业提交

提交最近保存的完整 VASP 作业：

```text
帮我提交最近的 VASP 作业，1 个节点 32 核，运行 10 分钟
```

提交指定子目录：

```text
帮我提交 VASP 作业，目录名 si_static_test，1 个节点 32 核，运行 10 分钟
```

提交指定绝对路径：

```text
帮我提交 VASP 作业，目录 /path/to/local/vasp-jobs/si_static_test，1 个节点 32 核，运行 10 分钟
```

确认：

```text
确认提交
```

提交时 Agent 会：

1. 在 `HPC_LOCAL_VASP_JOBS_INPUT_DIR` 中选择完整作业目录。
2. 校验 `INCAR`、`KPOINTS`、`POSCAR`、`POTCAR`。
3. 把生成的 `job.sh` 写入本地作业目录。
4. 上传输入文件到 `HPC_VASP_REMOTE_INPUT_DIR/<job-folder>`。
5. 在 `HPC_VASP_REMOTE_OUTPUT_DIR/<job-folder>` 写入远端 `job.sh`。
6. 远端 `job.sh` 运行时从 input 目录复制输入文件到 output 目录。
7. 在 output 目录执行 VASP。
8. 登记 Job ID、远端 output 目录和本地 output/analysis 目录。

VASP 标准输出、错误日志和运行结果都会写入远端 output 目录。

作业完成后，可以把远端 output 同步回本地：

```text
同步 VASP 作业 11817144 输出到本地
```

同步后目录结构为：

```text
$HPC_LOCAL_VASP_JOBS_OUTPUT_DIR/<job-folder>/
├── raw_output/
│   ├── INCAR
│   ├── KPOINTS
│   ├── POSCAR
│   ├── OUTCAR
│   ├── OSZICAR
│   └── vasprun.xml
└── analysis/
    ├── file_manifest.json
    └── report_context.md
```

默认不会同步 `WAVECAR`、`CHGCAR`、`AECCAR*`、`POTCAR`，避免把超大文件或赝势文件拉回本地分析目录。原始输出只放在 `raw_output/`，Claude Code 分析产物只放在 `analysis/`。`report_context.md` 是后续 Claude Code 生成报告的受控输入。

生成 Claude Code 报告：

```text
生成 VASP 作业 si_static_test 报告
```

也可以使用已登记的 Job ID：

```text
生成 VASP 作业 11817144 报告
```

生成后会写入：

```text
$HPC_LOCAL_VASP_JOBS_OUTPUT_DIR/<job-folder>/analysis/
├── report.md
├── paper_methods.md
└── paper_results.md
```

一键分析会自动执行同步、`report_context.md` 生成和 Claude Code 报告生成：

```text
一键分析 VASP 作业 si_static_test
```

或：

```text
一键分析 VASP 作业 11817144
```

Claude Code 调用可能需要几十秒到数分钟。CLI/TUI 会显示等待状态，结果中会包含 Claude Code 实际耗时和超时设置。

报告生成规则来自项目内 skill：

```text
skills/vasp_report/SKILL.md
```

该 skill 约束 Claude Code 只使用 `analysis/report_context.md`，不直接读取大体积原始输出，也不编造未在上下文中确认的论文结果。

当前默认 VASP 启动方式：

```bash
source /public1/soft/intel/2020u4/compilers_and_libraries_2020.4.304/linux/bin/compilervars.sh intel64
mpirun /public1/soft/vasp
```

如果你的集群 VASP 启动方式不同，请修改 `.env`：

```env
HPC_VASP_SETUP_COMMAND=...
HPC_VASP_COMMAND=...
HPC_VASP_MODULE=
```

---

## 14. VASP 脚本生成

只生成脚本，不提交：

```text
帮我生成一个 VASP 结构优化脚本，1 个节点，每节点 32 核，运行 24 小时
```

静态计算：

```text
帮我生成 VASP 静态计算脚本，1 个节点 32 核，运行 2 小时
```

说明：

* 脚本生成不会上传文件。
* 真正提交仍然走固定目录流程。
* VASP 请求中如果包含危险命令，Agent 会拒绝生成脚本。

---

## 15. 登记已有 VASP 作业

如果某个 VASP 作业已经在超算上提交过，可以把 Job ID 和远端输出目录登记到本地 registry：

```text
登记 VASP 作业 11817144，目录名 si_static_test
```

或者提供远端绝对路径：

```text
登记 VASP 作业 11817144，目录 /path/to/remote/vasp-hpc-jobs-output/si_static_test
```

登记后可以继续使用：

```text
查看 11817144 的状态
读取 11817144 的输出
读取 11817144 的错误日志
同步 VASP 作业 11817144 输出到本地
```

---

## 16. Web UI

Web UI 支持：

* 聊天式输入
* Intent 显示
* New Chat
* 普通作业附件上传
* 普通作业提交预览和确认
* 作业状态、输出、错误日志查询
* 远端普通作业编号列表和清理
* VASP 固定目录提交预览和确认

Web 文件上传说明：

* 上传按钮只用于普通 Slurm 作业。
* Web 附件不会用于 VASP 提交。
* 上传总大小限制为 100 MB。

Web 普通作业上传示例：

```text
帮我提交一个作业运行 python train.py，1核，5分钟
```

点击输入框左侧 `+` 上传 `train.py`，发送后回复：

```text
确认提交
```

---

## 17. 错误诊断和 Pending 排查

直接粘贴错误日志：

```text
CUDA out of memory
ModuleNotFoundError: No module named numpy
sbatch: error: Batch job submission failed: Invalid partition name specified
python: can't open file 'monitor_cpu.py': [Errno 2] No such file or directory
```

Pending 排查：

```text
我的任务一直 pending
我的任务一直不运行
为什么作业没有开始
```

如果 Job Monitor 提示可诊断错误日志，可以先读取 stderr：

```text
读取 11814753 的错误日志
```

然后把错误内容交给 Agent 诊断。

---

## 18. 测试和检查

本地全量检查：

```bash
.venv/bin/python tests/run_all_checks.py
```

SSH 连接检查：

```bash
.venv/bin/python tests/test_ssh.py
```

真实超算工作流检查：

```bash
.venv/bin/python tests/run_all_checks.py --live-hpc
```

注意：`--live-hpc` 会连接超算并提交真实 Slurm 测试作业。

TUI 快速手动测试：

```text
什么是 sbatch
跑 /path/to/your_script.py，4核，15分钟
确认提交
监控 JOBID
读取 JOBID 的输出
取消监控 JOBID
```

把 `/path/to/your_script.py` 换成你本机真实存在的 `.py` 或 `.sh` 文件路径。

---

## 19. 常用命令合集

```text
什么是 sbatch
squeue 是干什么的
帮我写一个 sbatch 脚本运行 python train.py，4核，10分钟
跑 train.py
跑 train.py，4核，15分钟
帮我提交 ./run.sh，2核，30分钟
确认提交
取消提交
查看 11814753 的状态
读取 11814753 的输出
读取 11814753 的错误日志
监控 11814753
取消监控 11814753
列出远端作业编号
清理远端作业 11817627 的文件
确认清理
清理远端普通作业目录下所有作业文件
确认清理全部
帮我生成一个 VASP 结构优化脚本，1 个节点，每节点 32 核，运行 24 小时
帮我提交 VASP 作业，目录名 si_static_test，1 个节点 32 核，运行 10 分钟
登记 VASP 作业 11817144，目录名 si_static_test
CUDA out of memory
我的任务一直 pending
```

---

## 20. 当前限制

* 提交和清理操作需要用户确认。
* Web 附件上传只用于普通 Slurm 作业。
* Web 附件总大小限制为 100 MB。
* 远端清理只作用于普通作业目录 `HPC_REMOTE_WORKDIR`。
* VASP 提交前必须手动准备完整本地目录。
* Agent 不会生成真实 `POTCAR`。
* TUI 监控只加入运行中或排队中的 Job。
* 当前不做 GPU 利用率实时监控。
* 聊天历史不持久化。

---

## 21. 故障排查

Textual 未安装：

```text
Textual 依赖尚未安装
```

处理：

```bash
uv sync
```

Web 文件上传不可用：

```text
python-multipart is required
```

处理：

```bash
uv sync
```

SSH 连接失败：

* 检查 `HPC_HOST`、`HPC_USERNAME`、`HPC_KEY_PATH`。
* 确认私钥文件存在且权限正确。
* 手动测试 SSH：

```bash
ssh -i /path/to/your/private/key -l 'your-hpc-username' your-hpc-host
```

普通作业提示找不到文件：

* 相对路径是相对于当前项目目录解析的。
* 文件不在项目目录时使用绝对路径。
* 脚本内部引用的其他文件也需要作为附件上传或改成脚本运行目录下可访问的路径。

VASP 提示缺少输入文件：

* 检查本地目录是否在 `HPC_LOCAL_VASP_JOBS_INPUT_DIR` 下。
* 检查是否包含 `INCAR`、`KPOINTS`、`POSCAR`、`POTCAR`。
* 如果使用绝对路径，确认路径拼写正确。

剪贴板不可用：

* TUI 的 `Ctrl+Y` 会依次尝试 `pyperclip`、`powershell.exe`、`wl-copy`、`xclip`、`xsel`、`pbcopy`、`clip`。
* 如果当前环境没有可用剪贴板命令，会在 Chat 里提示错误。

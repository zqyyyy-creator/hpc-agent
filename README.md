# HPC Agent

HPC Agent 是一个面向 HPC / Slurm 超算环境的对话式助手。它支持 Slurm 知识问答、sbatch 脚本生成、普通作业提交、作业查询、日志读取、错误诊断、远端作业目录清理，以及固定目录流程的 VASP 作业提交和监控。

详细操作请看 [USER_GUIDE.md](USER_GUIDE.md)。

---

## 当前能力

* Slurm / HPC 知识库问答
* 根据自然语言生成普通 sbatch 脚本
* 根据本地普通作业文件自动补充推荐资源参数
* 普通 Slurm 作业确认式提交
* 普通作业文件上传到远端独立作业目录
* 查询作业状态、读取 stdout、读取 stderr
* Textual TUI 显式 Job Monitor
* 同时监控多个运行中 Job，并用 Tab 切换
* 复制上一条 Agent 回复
* 远端普通作业编号列表
* 远端普通作业文件清理，保留根目录本身
* 错误日志诊断和 Pending 排查
* VASP sbatch 脚本生成
* VASP 固定目录提交：本地 input、远端 input、远端 output
* 登记已有 VASP 作业，便于继续查询日志
* Textual TUI、Terminal CLI、FastAPI Web UI 三种入口

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

启动后选择：

```text
1. Textual TUI 控制台模式
2. Terminal CLI 对话模式
3. Web 网页对话模式
```

Web 模式默认访问：

```text
http://127.0.0.1:8000
```

也可以直接启动 Web：

```bash
uvicorn web_app:app --reload
```

---

## 环境变量

项目根目录需要 `.env`。示例：

```env
PARATERA_BASE_URL=https://your-api-base-url
PARATERA_API_KEY=your-api-key

HPC_HOST=your-hpc-host
HPC_USERNAME=your-hpc-username
HPC_KEY_PATH=/path/to/your/private/key
HPC_REMOTE_WORKDIR=/path/to/remote/hpc-agent-jobs
HPC_DEFAULT_PARTITION=

HPC_LOCAL_VASP_JOBS_DIR=/path/to/local/vasp-jobs
HPC_VASP_REMOTE_INPUT_DIR=/path/to/remote/vasp-hpc-jobs-input
HPC_VASP_REMOTE_OUTPUT_DIR=/path/to/remote/vasp-hpc-jobs-output
HPC_VASP_PARTITION=
HPC_VASP_SETUP_COMMAND=source /public1/soft/intel/2020u4/compilers_and_libraries_2020.4.304/linux/bin/compilervars.sh intel64
HPC_VASP_COMMAND=mpirun /public1/soft/vasp
HPC_VASP_MODULE=
```

说明：

* `HPC_REMOTE_WORKDIR`：普通 Slurm 作业远端根目录。
* `HPC_DEFAULT_PARTITION`：普通作业默认 partition；留空表示不写 `#SBATCH --partition`，使用集群默认分区。
* `HPC_LOCAL_VASP_JOBS_DIR`：本地 VASP 作业根目录。
* `HPC_VASP_REMOTE_INPUT_DIR`：VASP 作业远端输入根目录。
* `HPC_VASP_REMOTE_OUTPUT_DIR`：VASP 作业远端输出/运行根目录。
* `HPC_VASP_PARTITION`：VASP 作业默认 partition；留空表示不写 `#SBATCH --partition`，使用集群默认分区。
* `HPC_VASP_SETUP_COMMAND`：VASP 运行前的环境初始化命令。
* `HPC_VASP_COMMAND`：VASP 主程序启动命令。
* `HPC_VASP_MODULE`：可选，留空表示不使用 `module load`。

`.env` 不应提交到 Git。

---

## 常用命令

普通作业：

```text
跑 train.py，4核，15分钟
帮我提交 ./run.sh，2核，30分钟
帮我提交一个作业运行 python train.py，8核，1小时，16G内存
确认提交
取消提交
```

作业查询：

```text
查看 11814753 的状态
读取 11814753 的输出
读取 11814753 的错误日志
列出远端作业编号
```

TUI 监控：

```text
监控 11814753
取消监控 11814753
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

---

## VASP 固定目录流程

VASP 提交前，用户需要手动在本地准备完整作业目录：

```text
$HPC_LOCAL_VASP_JOBS_DIR/<job-folder>/
├── INCAR
├── KPOINTS
├── POSCAR
└── POTCAR
```

提交时 Agent 只做三件事：

1. 选择本地 `$HPC_LOCAL_VASP_JOBS_DIR/<job-folder>`。
2. 上传该目录文件到远端 `$HPC_VASP_REMOTE_INPUT_DIR/<job-folder>`。
3. 在远端 `$HPC_VASP_REMOTE_OUTPUT_DIR/<job-folder>` 写入并运行 `job.sh`。

VASP 标准输出、错误日志和运行结果写入远端 output 目录。Agent 不会生成真实 `POTCAR`，`POTCAR` 需要来自你有权限使用的 VASP 赝势库。

---

## TUI 快捷键

Textual TUI 当前布局保持为：

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
├── app.py
├── main.py
├── textual_cli.py
├── web_app.py
├── modules/
├── data/
├── static/
├── tests/
├── README.md
└── USER_GUIDE.md
```

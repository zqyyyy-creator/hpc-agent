# HPC Agent

HPC Agent 是一个面向 HPC / Slurm 超算环境的对话式 Agent。它可以帮助用户生成作业脚本、提交 Slurm 作业、查询状态和日志、诊断常见错误，并支持 VASP 作业的输入文件准备与提交。

详细操作说明见 [USER_GUIDE.md](USER_GUIDE.md)。

---

## 核心功能

* Slurm 知识库问答
* sbatch 脚本生成
* Slurm 参数建议
* 错误日志诊断
* Pending / 不运行任务排查
* SSH 连接超算并确认式提交作业
* 普通 Slurm 作业附件上传
* 作业状态、标准输出和错误日志查询
* 远端普通作业编号列表与文件清理
* VASP 脚本生成、输入文件准备、提交和日志读取
* Terminal CLI 与 FastAPI Web UI

---

## 快速开始

创建并激活虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
```

安装依赖：

```bash
uv sync
```

启动：

```bash
python app.py
```

选择模式：

```text
1  Terminal CLI
2  Web UI
```

Web 模式访问：

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

HPC_HOST=ssh.cn-zhongwei-1.paracloud.com
HPC_USERNAME=a0s000582@BSCC-A
HPC_KEY_PATH=/home/qyz/.ssh/id_ed25519
HPC_REMOTE_WORKDIR=/public4/home/a0s000582/hpc-agent-jobs
HPC_DEFAULT_PARTITION=amd_test

HPC_VASP_REMOTE_WORKDIR=/public4/home/a0s000582/vasp-hpc-jobs
HPC_VASP_PARTITION=amd_test
HPC_LOCAL_VASP_JOBS_DIR=/home/qyz/vasp-jobs
HPC_LOCAL_VASP_IMPORT_DIR=/home/qyz/vasp-jobs-input
HPC_VASP_SETUP_COMMAND=source /public1/soft/intel/2020u4/compilers_and_libraries_2020.4.304/linux/bin/compilervars.sh intel64
HPC_VASP_COMMAND=mpirun /public1/soft/vasp
HPC_VASP_MODULE=
```

说明：

* `HPC_REMOTE_WORKDIR` 是普通 Slurm 作业远端根目录。每次普通提交都会创建独立子目录。
* `HPC_VASP_REMOTE_WORKDIR` 是 VASP 作业远端根目录。
* `HPC_LOCAL_VASP_JOBS_DIR` 是本地 VASP 作业目录。
* `HPC_LOCAL_VASP_IMPORT_DIR` 是 VASP 输入文件导入来源目录。
* `HPC_VASP_SETUP_COMMAND` 是 VASP 运行前的环境初始化命令。
* `HPC_VASP_COMMAND` 是 VASP 主程序启动命令。
* `HPC_VASP_MODULE` 留空表示不使用 `module load`。
* `.env` 不应提交到 Git。

---

## 常用命令示例

普通作业脚本生成：

```text
帮我写一个 sbatch 脚本运行 python train.py，4 核，10 分钟
```

普通作业提交：

```text
帮我提交一个作业运行 python train.py，4 核，10 分钟
```

Web 版可以点击 `+` 上传 `train.py` 等普通作业附件。确认提交后回复：

```text
确认提交
```

查询作业：

```text
查看11814753的状态
读取11814753的输出
读取11814753的错误日志
```

列出远端普通作业编号：

```text
列出远端 hpc-agent-jobs 里的任务编号
```

清理远端普通作业文件：

```text
清理远端作业 11817627 的文件
清理远端 hpc-agent-jobs 下所有作业文件
```

VASP 作业：

```text
帮我生成一个 VASP 结构优化脚本，1 个节点，每节点 32 核，运行 24 小时
帮我提交 VASP 作业，1 个节点 32 核，运行 10 分钟
从目录导入 VASP 输入文件: /home/qyz/vasp-jobs-input
```

错误诊断：

```text
CUDA out of memory
ModuleNotFoundError: No module named numpy
sbatch: error: Batch job submission failed: Invalid partition name specified
```

---

## Web UI

Web UI 支持：

* 对话式输入
* Intent 显示
* 普通作业文件附件上传
* 提交前预览和确认
* 作业状态、输出、错误日志查询
* 远端普通作业编号列表和清理
* VASP 输入来源选择与提交确认

普通作业附件上传限制：

* 仅用于普通 Slurm 作业
* 不用于 VASP 作业
* 总大小限制为 100 MB

---

## VASP 工作流

VASP 提交前需要完整输入文件：

```text
INCAR
POSCAR
POTCAR
KPOINTS
```

提交 VASP 作业但没有指定目录时，Agent 会先让用户选择输入来源：

```text
1. 使用已有本地 VASP 作业目录
2. 从导入目录导入四个 VASP 文件
3. 在对话中粘贴四个 VASP 输入文件
4. 让 Agent 辅助生成 VASP 输入模板
```

注意：Agent 不会伪造真实 `POTCAR`。`POTCAR` 需要来自你有权限使用的 VASP 赝势库。

当前集群已验证的 VASP 启动方式为：

```bash
source /public1/soft/intel/2020u4/compilers_and_libraries_2020.4.304/linux/bin/compilervars.sh intel64
mpirun /public1/soft/vasp
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
├── web_app.py
├── static/
├── modules/
├── data/
├── tests/
├── skills/
├── README.md
└── USER_GUIDE.md
```

---

## 技术栈

* Python
* FastAPI / Uvicorn
* Rich
* Paramiko SSH / SFTP
* python-dotenv
* python-multipart
* scikit-learn retrieval

---

## 后续方向

* 更完整的作业历史管理
* 聊天历史持久化
* GPU 资源监控
* 自动修复作业脚本
* 更完整的 VASP 结果解析
* React 前端或更完整的 Web UI

---

## License

MIT License

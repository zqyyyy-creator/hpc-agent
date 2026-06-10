# HPC Agent 用户手册

本手册说明如何安装、配置和使用 HPC Agent。README 只保留项目概览；实际操作以本文档为准。

---

## 1. 功能概览

HPC Agent 支持：

* Slurm 知识库问答
* sbatch 脚本生成
* Slurm 参数建议
* 错误日志诊断
* Pending / 不运行任务排查
* 普通 Slurm 作业确认式提交
* Web 普通作业附件上传
* 作业状态、输出和错误日志查询
* 远端普通作业编号列表和文件清理
* VASP 脚本生成、输入文件准备、提交和日志读取
* Terminal CLI 和 Web UI

---

## 2. 安装

创建虚拟环境：

```bash
python -m venv .venv
```

激活虚拟环境：

```bash
source .venv/bin/activate
```

安装依赖：

```bash
uv sync
```

如果使用 pip，请以 `pyproject.toml` 中的依赖为准，并确保安装 `python-multipart`，否则 Web 文件上传不可用。

```bash
pip install fastapi uvicorn paramiko python-dotenv python-multipart rich jieba requests scikit-learn openai anthropic
```

---

## 3. 环境变量

项目根目录 `.env` 需要配置 LLM API、SSH 和 VASP 路径。

示例：

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

路径说明：

* `HPC_KEY_PATH`：本机 WSL/Linux 中 SSH 私钥的绝对路径。
* `HPC_REMOTE_WORKDIR`：普通 Slurm 作业远端根目录。每次普通提交会在下面创建独立子目录。
* `HPC_VASP_REMOTE_WORKDIR`：VASP 作业远端根目录。
* `HPC_LOCAL_VASP_JOBS_DIR`：本地 VASP 作业目录。
* `HPC_LOCAL_VASP_IMPORT_DIR`：默认导入 VASP 输入文件的本地来源目录。
* `HPC_VASP_SETUP_COMMAND`：VASP 运行前的环境初始化命令。
* `HPC_VASP_COMMAND`：VASP 主程序启动命令。
* `HPC_VASP_MODULE`：留空表示不使用 `module load`。

WSL 中检查路径：

```bash
realpath -e ~/.ssh/id_ed25519
realpath ~/vasp-jobs
realpath ~/vasp-jobs-input
```

如果本地 VASP 目录不存在：

```bash
mkdir -p ~/vasp-jobs ~/vasp-jobs-input
```

---

## 4. 启动

统一入口：

```bash
python app.py
```

选择 CLI：

```text
1
```

选择 Web：

```text
2
```

Web 地址：

```text
http://127.0.0.1:8000
```

也可以直接启动 Web：

```bash
uvicorn web_app:app --reload
```

---

## 5. 普通 Slurm 作业

生成脚本：

```text
帮我写一个 sbatch 脚本运行 python train.py，4 核，10 分钟
```

提交作业：

```text
帮我提交一个作业运行 python train.py，4 核，10 分钟
```

Agent 会先展示待提交脚本。确认提交：

```text
确认提交
```

取消提交：

```text
取消提交
```

Web 版可以点击输入框左侧 `+` 上传普通作业文件，例如：

```text
train.py
run.sh
config.yaml
```

确认提交后，Agent 会在 `HPC_REMOTE_WORKDIR` 下创建本次作业的独立子目录，并上传：

```text
job.sh
用户上传的附件
作业 .out 输出日志
作业 .err 错误日志
```

附件上传限制：

* 仅适用于普通 Slurm 作业
* 不适用于 VASP 作业
* 总大小限制为 100 MB

---

## 6. 作业查询

查询状态：

```text
查看11814753的状态
```

读取标准输出：

```text
读取11814753的输出
```

读取错误日志：

```text
读取11814753的错误日志
```

对于 Agent 提交并登记过的普通作业，输出和错误日志会优先从该作业的远端独立子目录读取。

---

## 7. 远端普通作业管理

列出 `HPC_REMOTE_WORKDIR` 下的普通作业编号：

```text
列出远端 hpc-agent-jobs 里的任务编号
```

按 Job ID 清理普通作业文件：

```text
清理远端作业 11817627 的文件
```

Agent 会先展示将删除的目标。确认清理：

```text
确认清理
```

取消清理：

```text
取消清理
```

清理全部普通作业文件：

```text
清理远端 hpc-agent-jobs 下所有作业文件
```

该操作只清理 `HPC_REMOTE_WORKDIR` 下的一级文件和子目录，保留根目录本身，不清理 VASP 目录。确认清理全部必须回复完整短语：

```text
确认清理全部
```

---

## 8. Slurm 辅助功能

知识库问答：

```text
什么是 sbatch
squeue 是干什么的
```

参数建议：

```text
训练 pytorch 模型应该申请多少 GPU
这个任务需要多少内存和 CPU
```

错误诊断：

```text
CUDA out of memory
ModuleNotFoundError: No module named numpy
sbatch: error: Batch job submission failed: Invalid partition name specified
```

Pending 排查：

```text
我的任务一直 pending
我的任务一直不运行
```

---

## 9. VASP 输入文件

VASP 提交需要完整输入文件：

```text
INCAR
POSCAR
POTCAR
KPOINTS
```

### 9.1 粘贴生成

适合你已经有四个文件的文本内容时使用。

````text
生成 VASP 输入文件
```INCAR
...
```
```POSCAR
...
```
```POTCAR
...
```
```KPOINTS
...
```
````

生成后的文件会写入：

```text
HPC_LOCAL_VASP_JOBS_DIR
```

### 9.2 从目录导入

适合你已经在本地目录中准备好四个真实文件时使用。

```text
从目录导入 VASP 输入文件: /home/qyz/vasp-jobs-input
```

导入来源默认是：

```text
HPC_LOCAL_VASP_IMPORT_DIR
```

导入完成后，Agent 会复制一份到：

```text
HPC_LOCAL_VASP_JOBS_DIR
```

### 9.3 Agent 辅助生成模板

适合快速生成初始模板：

```text
请 Agent 辅助生成 Si 结构优化 VASP 输入模板
```

Agent 可以生成部分模板文件，但不会伪造真实 `POTCAR`。如果模板缺少 `POTCAR`，不会直接进入提交预览。

---

## 10. VASP 作业提交

如果提交 VASP 作业时没有指定目录，Agent 会先让你选择输入来源：

```text
1. 使用已有本地 VASP 作业目录
2. 从导入目录导入四个 VASP 文件
3. 在对话中粘贴四个 VASP 输入文件
4. 让 Agent 辅助生成 VASP 输入模板
```

提交最近保存的完整 VASP 作业：

```text
帮我提交最近的 VASP 作业，1 个节点 32 核，运行 10 分钟
```

提交指定本地子目录：

```text
帮我提交 VASP 作业，目录名 vasp_imported_20260610_131601，1 个节点 32 核，运行 10 分钟
```

确认提交：

```text
确认提交
```

提交时 Agent 会：

* 在本地 VASP 作业目录中找到完整输入文件
* 写入 `job.sh`
* 在远端 VASP 根目录下创建独立作业目录
* 上传 `INCAR`、`POSCAR`、`POTCAR`、`KPOINTS` 和 `job.sh`
* 执行 `sbatch job.sh`
* 登记 Job ID 和远端目录

当前集群已验证的 VASP 脚本会使用：

```bash
source /public1/soft/intel/2020u4/compilers_and_libraries_2020.4.304/linux/bin/compilervars.sh intel64
mpirun /public1/soft/vasp
```

因此不再使用 `module load vasp`、`vasp_std` 或 `srun /public1/soft/vasp` 作为默认启动方式。

---

## 11. 登记已有 VASP 作业

如果某个 VASP 作业已经在超算上提交过，可以登记它的 Job ID 和远端目录名：

```text
登记 VASP 作业 11817144，目录名 vasp_imported_20260610_131601
```

登记后可以继续查询：

```text
读取11817144的输出
读取11817144的错误日志
查看11817144的状态
```

---

## 12. Web UI

Web UI 支持：

* 聊天历史滚动
* New Chat
* Intent 显示
* Enter 发送
* 普通 Slurm 附件上传
* 提交预览和确认
* VASP 输入来源选择
* 远端普通作业编号列表和清理

文件上传按钮是输入框左侧的 `+`。上传文件只会随普通 Slurm 作业提交。

---

## 13. 手动测试

本地功能检查：

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

Web 附件上传测试：

```text
帮我提交一个作业运行 python train.py，1 核，5 分钟
```

在网页中点击 `+` 上传 `train.py`，发送后回复：

```text
确认提交
```

远端编号列表测试：

```text
列出远端 hpc-agent-jobs 里的任务编号
```

清理预览测试：

```text
清理远端作业 11817627 的文件
```

看到预览后，如果不想删除，回复：

```text
取消清理
```

---

## 14. 当前限制

* 提交和清理操作都需要用户确认。
* Web 附件上传总大小限制为 100 MB。
* Web 附件上传只用于普通 Slurm 作业，不用于 VASP 作业。
* 远端清理功能只作用于普通作业目录 `HPC_REMOTE_WORKDIR`，不会清理 VASP 目录。
* Agent 不会伪造真实 `POTCAR`。
* VASP 作业提交前，本地目录必须包含完整输入文件。
* 当前不支持真实 GPU 监控。
* 当前不支持持久化聊天历史。

---

## 15. 常用命令合集

```text
什么是 sbatch
帮我写一个 sbatch 脚本运行 python train.py，4 核，10 分钟
帮我提交一个作业运行 python train.py，4 核，10 分钟
确认提交
查看11814753的状态
读取11814753的输出
读取11814753的错误日志
列出远端 hpc-agent-jobs 里的任务编号
清理远端作业 11817627 的文件
清理远端 hpc-agent-jobs 下所有作业文件
帮我生成一个 VASP 结构优化脚本，1 个节点，每节点 32 核，运行 24 小时
从目录导入 VASP 输入文件: /home/qyz/vasp-jobs-input
帮我提交最近的 VASP 作业，1 个节点 32 核，运行 10 分钟
登记 VASP 作业 11817144，目录名 vasp_imported_20260610_131601
CUDA out of memory
我的任务一直 pending
```

---

## 16. 后续方向

* 更完整的作业历史管理
* 聊天历史持久化
* GPU 资源监控
* 自动修复作业脚本
* 更完整的 VASP 结果解析
* 更完整的 Web UI

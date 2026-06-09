# HPC Agent

一个面向 HPC / Slurm 超算环境的 AI Agent 原型系统。

该项目结合：

* RAG（Retrieval-Augmented Generation）
* Slurm 作业调度
* 错误日志诊断
* sbatch 脚本生成
* SSH 超算连接
* Slurm 作业提交、状态查询与日志读取
* Rich CLI 美化
* FastAPI Web UI

实现了一个可交互的 HPC Assistant。

---

# 项目目标

本项目旨在构建一个能够帮助用户：

* 学习 Slurm
* 提交超算作业
* 自动生成 sbatch 脚本
* 通过对话确认后提交作业到指定超算
* 查询 Slurm 作业状态
* 读取作业标准输出和错误日志
* 分析错误日志
* 提供资源参数建议
* 进行 HPC 工作流辅助

的 AI Agent 系统。

---

# 当前功能

## 1. Slurm 知识库问答

支持：

* sbatch
* squeue
* scancel
* partition
* GPU 作业
* Slurm 基础概念

示例：

```text
什么是 sbatch
```

```text
如何提交一个超算作业
```

---

## 2. sbatch 脚本生成

自动生成 Slurm 作业脚本。

示例：

```text
帮我写一个 sbatch 脚本运行 python train.py
```

---

## 3. Slurm 参数建议

根据任务类型推荐：

* CPU
* GPU
* Memory
* Time limit

示例：

```text
训练 pytorch 模型应该申请多少 GPU
```

---

## 4. 错误日志诊断

支持分析：

* CUDA out of memory
* ModuleNotFoundError
* Permission denied
* invalid partition
* segmentation fault

示例：

```text
CUDA out of memory
```

---

## 5. Pending / 不运行任务排查

支持：

```text
我的任务一直 pending
```

```text
我的任务一直不运行
```

---

## 6. 提交作业到超算

支持通过 SSH 连接指定超算，并在用户确认后提交 Slurm 作业。

示例：

```text
帮我提交一个作业运行 python train.py，4 核，10 分钟
```

系统会先展示待提交的 sbatch 脚本。确认无误后输入：

```text
确认提交
```

或在 Terminal CLI 中选择：

```text
y
```

提交成功后会返回：

```text
Job ID: 11814753
```

---

## 7. 作业状态和日志查询

支持通过对话查询作业状态、标准输出和错误日志。

示例：

```text
查看11814753的状态
```

```text
读取11814753的输出
```

```text
读取11814753的错误日志
```

---

# Terminal CLI 界面

项目使用 Rich 实现：

* 彩色输出
* 表格
* 面板
* Markdown 渲染
* 状态动画

---

# Web UI

项目支持网页交互模式。

当前支持：

* 聊天历史滚动
* ChatGPT 风格对话
* New Chat 页面刷新
* Intent 显示
* Web 聊天输入框
* FastAPI 后端通信
* 作业提交预览
* 确认提交到超算
* 作业状态和日志查询

网页启动后访问：

```text
http://127.0.0.1:8000
```

---

# 启动方式

项目支持：

1. Terminal CLI 模式
2. Web 网页模式

运行：

```bash
python app.py
```

然后选择：

```text
1
```

进入 Terminal CLI。

选择：

```text
2
```

进入 Web 模式。

---

# 项目结构

```text
hpc-agent/
├── app.py
├── main.py
├── web_app.py
├── static/
│   └── index.html
├── modules/
│   ├── knowledge_base.py
│   ├── slurm_assistant.py
│   ├── slurm_tools.py
│   ├── job_submitter.py
│   ├── job_query.py
│   ├── error_diagnoser.py
│   └── router.py
├── docs/
│   ├── slurm_submit.txt
│   ├── slurm_status.txt
│   ├── slurm_cancel.txt
│   ├── cluster_info.txt
│   └── common_errors.txt
├── README.md
└── USER_GUIDE.md
```

---

# 安装方法

## 1. 创建虚拟环境

```bash
python -m venv .venv
```

---

## 2. 激活虚拟环境

Linux / WSL：

```bash
source .venv/bin/activate
```

Windows：

```powershell
.venv\Scripts\activate
```

---

## 3. 安装依赖

```bash
pip install -r requirements.txt
```

或者：

```bash
uv sync
```

---

# 环境变量配置

项目需要配置 LLM API 和超算 SSH 信息。

示例：

```env
PARATERA_BASE_URL=https://your-api-base-url
PARATERA_API_KEY=your-api-key

HPC_HOST=ssh.cn-zhongwei-1.paracloud.com
HPC_USERNAME=a0s000582@BSCC-A
HPC_KEY_PATH=/home/lenovo/.ssh/id_ed25519
HPC_REMOTE_WORKDIR=/public4/home/a0s000582
HPC_DEFAULT_PARTITION=amd_test
```

注意：

* `.env` 不应提交到 Git
* 当前测试环境使用 `amd_test` partition
* 提交作业前会先展示 sbatch 脚本并要求确认
* 如果脚本运行 `python train.py`，需要确保 `train.py` 已存在于远程工作目录或脚本中切换到正确目录

---

# 启动项目

## Terminal 模式

```bash
python app.py
```

选择：

```text
1
```

---

## Web 模式

```bash
python app.py
```

选择：

```text
2
```

或直接运行：

```bash
uvicorn web_app:app --reload
```

---

# 使用示例

## 普通问答

```text
什么是 sbatch
```

---

## 生成脚本

```text
帮我写一个 sbatch 脚本运行 python train.py
```

---

## 参数建议

```text
训练 pytorch 模型应该申请多少 GPU
```

---

## 错误诊断

```text
CUDA out of memory
```

---

## 提交作业

```text
帮我提交一个作业运行 python train.py，4 核，10 分钟
```

确认提交：

```text
确认提交
```

---

## 查询作业

```text
查看11814753的状态
```

```text
读取11814753的输出
```

```text
读取11814753的错误日志
```

---

# Intent Router

系统会自动识别用户请求类型。

支持：

| Intent           | 功能              |
| ---------------- | --------------- |
| rag_qa           | 知识库问答           |
| generate_sbatch  | sbatch 脚本生成     |
| suggest_params   | 参数建议            |
| diagnose_error   | 错误日志诊断          |
| troubleshoot_job | Pending / 不运行排查 |
| submit_job       | 提交作业到超算        |
| job_status       | 查询作业状态          |
| job_output       | 读取作业标准输出      |
| job_error        | 读取作业错误日志      |

---

# 技术栈

## AI / RAG

* OpenAI / DeepSeek API
* RAG
* Embedding Retrieval

---

## HPC

* Slurm
* sbatch
* squeue
* scancel
* Paramiko SSH

---

## Backend

* FastAPI
* Uvicorn

---

## Frontend

* HTML
* CSS
* JavaScript

---

## Python

* Rich
* Click
* jieba
* Paramiko

---

# Week 进度

## Week 1

* Python 环境
* API 接入

---

## Week 2

* 基础 RAG

---

## Week 3

* HPC 文档知识库
* Retrieval 系统

---

## Week 4

* Slurm Assistant
* 错误诊断系统

---

## Week 5

* 多功能模块整合
* Intent Router

---

## Week 6

* Rich CLI 美化
* FastAPI Web UI
* ChatGPT 风格网页
* 聊天历史滚动
* 双模式启动
* 用户手册

---

## Week 7

* Agent Skill 规范集成
* SSH 连接超算
* Slurm 作业真实提交
* 作业状态查询
* 作业 stdout/stderr 日志读取
* 功能整合优化

---

# 后续开发方向

未来计划：

* 用户登录
* 数据库存储聊天历史
* SSH 集成
* 自动提交作业
* Agent Memory
* Workflow Agent
* 自动修复作业
* GPU 资源监控
* 多轮任务规划
* React 前端
* Docker 部署

---

# 注意事项

本项目不会编造：

* partition 名称
* 节点名称
* account
* QoS

等集群专属信息。

如果知识库没有相关内容，Agent 会明确说明信息不足。

---

# 用户手册

详细使用说明请查看：

```text
USER_GUIDE.md
```

---

# License

MIT License

# HPC Agent 用户手册

## 1. 项目简介

HPC Agent 是一个面向 HPC / Slurm 超算环境的 AI Assistant。

项目支持：

* Slurm 知识库问答
* sbatch 脚本生成
* 参数建议
* 错误日志诊断
* Pending 作业排查
* Terminal CLI
* Web 网页交互

---

## 2. 支持模式

项目支持：

1. Terminal CLI 模式
2. Web 网页模式

启动：

```bash
python app.py
```

---

## 3. Terminal CLI 模式

启动后输入：

```text
1
```

进入 CLI 模式。

CLI 模式支持：

* Rich 彩色输出
* Markdown 渲染
* 状态动画
* 多功能路由

---

## 4. Web 模式

启动后输入：

```text
2
```

或直接运行：

```bash
uvicorn web_app:app --reload
```

浏览器访问：

```text
http://127.0.0.1:8000
```

---

## 5. Web UI 功能

当前网页支持：

* 聊天历史滚动
* ChatGPT 风格对话
* New Chat
* Intent 显示
* 输入框快捷发送
* Enter 快捷发送

---

## 6. 功能说明

### 6.1 Slurm 问答

示例：

```text
什么是 sbatch
```

```text
squeue 是干什么的
```

---

### 6.2 sbatch 脚本生成

示例：

```text
帮我写一个 sbatch 脚本运行 python train.py
```

---

### 6.3 参数建议

示例：

```text
训练 pytorch 模型应该申请多少 GPU
```

---

### 6.4 错误诊断

示例：

```text
CUDA out of memory
```

---

### 6.5 Pending 排查

示例：

```text
我的任务一直 pending
```

---

## 7. 项目结构

```text
hpc-agent/
├── app.py
├── main.py
├── web_app.py
├── static/
│   └── index.html
├── modules/
├── docs/
├── README.md
└── USER_GUIDE.md
```

---

## 8. 环境安装

### 创建虚拟环境

```bash
python -m venv .venv
```

---

### 激活虚拟环境

Linux / WSL：

```bash
source .venv/bin/activate
```

Windows：

```powershell
.venv\Scripts\activate
```

---

### 安装依赖

```bash
pip install -r requirements.txt
```

或：

```bash
uv sync
```

---

## 9. 退出方式

CLI：

```text
quit
```

或：

```text
Ctrl + C
```

Web：

直接关闭浏览器页面即可。

---

## 10. 当前限制

当前系统：

* 不支持真实 SSH
* 不支持自动提交作业
* 不支持真实 GPU 监控
* 不支持持久化聊天历史

目前属于：

* AI Agent 原型系统
* HPC Assistant Prototype

---

## 11. 后续开发方向

未来计划：

* SQLite 聊天历史
* 用户系统
* SSH 集成
* 自动提交作业
* 自动修复脚本
* GPU 监控
* React 前端
* Docker 部署
* 多 Agent Workflow

---

## 12. 作者说明

本项目用于学习：

* AI Agent
* RAG
* HPC
* Slurm
* CLI 工程化
* Web Agent
* FastAPI
* Workflow Routing

属于一个面向超算场景的 AI Agent 原型系统。

# HPC-Agent

一个基于 AI 的 HPC（高性能计算）智能助手，用于帮助用户使用 Slurm 超算系统。

本项目结合了：

* RAG 知识库问答
* Slurm 脚本生成
* 参数推荐
* 错误日志诊断
* 自动修复建议
* CLI Agent 架构

目标是构建一个能够辅助 HPC 用户进行作业提交、问题诊断和资源管理的智能 Agent。

---

# 项目功能

## 1. HPC 知识库问答（RAG）

Agent 可以基于本地知识库回答 Slurm/HPC 相关问题。

例如：

```text
如何提交 sbatch 作业？
--mem 和 --mem-per-cpu 有什么区别？
如何查看我的作业状态？
```

系统会：

```text
用户问题
→ 检索相关文档
→ 调用 LLM 生成回答
```

---

## 2. Slurm sbatch 脚本生成

用户可以通过自然语言生成 Slurm 作业脚本。

示例：

```text
帮我生成一个使用 4 CPU、16GB 内存的 Python 作业脚本
```

输出：

```bash
#!/bin/bash
#SBATCH --job-name=my_job
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G

python train.py
```

---

## 3. Slurm 参数推荐

根据任务需求自动推荐：

* CPU 数量
* 内存大小
* 运行时间
* GPU 配置

例如：

```text
我要训练一个中型 PyTorch 模型
```

系统会自动推荐合适的 Slurm 参数。

---

## 4. 超算错误日志诊断系统

支持诊断常见 HPC / Slurm 错误。

当前错误库包含 20+ 常见错误：

* Out of Memory (OOM)
* Time Limit Exceeded
* Invalid Partition
* Invalid Account
* Disk Quota Exceeded
* Permission Denied
* ModuleNotFoundError
* CUDA Out of Memory
* SSH Authentication Error

等。

---

## 5. 自动修复建议系统

对于支持的错误类型，Agent 可以：

```text
错误日志
→ 分析错误
→ 推荐修复方案
→ 推荐 Slurm 参数
→ 推荐 Linux 排查命令
```

例如：

检测到：

```text
OOM
```

Agent 自动推荐：

```bash
#SBATCH --mem=16G
```

检测到：

```text
CUDA Out of Memory
```

Agent 自动推荐：

```bash
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
```

---

## 6. 自动修复 sbatch 脚本

用户可以：

```text
输入错误日志
→ 粘贴 sbatch 脚本
→ Agent 自动生成修复后的脚本
```

例如：

原脚本：

```bash
#SBATCH --mem=4G
```

Agent 自动修复为：

```bash
#SBATCH --mem=16G
```

---

## 7. 交互式错误诊断模式

系统支持独立的错误诊断模式：

```text
进入错误诊断模式
→ 连续输入日志
→ 连续诊断
→ 自动修复建议
→ quit 返回主菜单
```

并支持：

```text
Ctrl + C
```

中断当前任务。

---

# 项目结构

```text
hpc-agent/
│
├── data/
│   ├── docs/                 # RAG 文档库
│   └── errors/               # 错误日志与错误数据库
│
├── modules/
│   ├── knowledge_base.py     # RAG 检索模块
│   ├── slurm_assistant.py    # Slurm 参数/脚本生成
│   └── error_diagnoser.py    # 错误诊断系统
│
├── main.py                   # Agent 主程序
├── test_diagnoser.py         # 错误诊断测试
└── requirements.txt
```

---

# 技术栈

本项目使用：

* Python
* TF-IDF
* JSON 知识库
* Regular Expressions（re）
* Slurm
* CLI Agent Architecture

---

# 系统工作流程

```text
用户输入
 ↓
Intent Detection（意图识别）
 ↓
 ┌────────────────────┐
 │ RAG Knowledge Base │
 │ Slurm Assistant    │
 │ Error Diagnoser    │
 └────────────────────┘
 ↓
回答 / 参数建议 / 修复建议
```

---

# 项目目标

很多 HPC 用户在使用超算时会遇到：

* 不会写 Slurm 脚本
* 不理解资源申请
* 看不懂错误日志
* 不知道如何修复作业

本项目希望构建一个：

```text
面向 HPC 用户的 AI 智能助手
```

帮助用户：

* 学习 HPC
* 使用 Slurm
* 诊断错误
* 修复作业

并逐步发展为：

```text
自动化 HPC Agent
```

---

# 后续计划

未来计划加入：

* SSH 自动连接超算
* 自动提交作业
* 自动监控作业状态
* 自动错误恢复
* LLM 多步推理
* Web UI
* 多 Agent 协作

---

# License

MIT License

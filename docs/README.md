# HPC Agent Docs

这里是 HPC Agent 的文档入口。第一次使用建议先看用户手册；做发布、演示或真实集群验收时再看 Live Test Checklist。

## 文档导航

| 文档 | 用途 |
| --- | --- |
| [USER_GUIDE.md](USER_GUIDE.md) | 配置、启动、日常使用、普通 Slurm 作业、VASP 作业、错误诊断、快捷命令和 TUI 操作说明 |
| [LIVE_TEST_CHECKLIST.md](LIVE_TEST_CHECKLIST.md) | 真实超算环境验收清单，记录 Slurm / VASP 提交、监控、同步、分析结果 |
| [VASP_TEST_TEMPLATES.md](VASP_TEST_TEMPLATES.md) | 推荐 VASP 测试体系、输入文件模板、资源建议和通过标准 |
| [../data/errors/README.md](../data/errors/README.md) | 错误知识库维护说明，区分真实案例库和通用错误库，说明半自动入库和脱敏要求 |

## 推荐阅读顺序

1. 新用户先读 [USER_GUIDE.md](USER_GUIDE.md)。
2. 配置好 `.env` 后，按 [LIVE_TEST_CHECKLIST.md](LIVE_TEST_CHECKLIST.md) 做真实环境验收。
3. 需要准备 VASP smoke test 时，参考 [VASP_TEST_TEMPLATES.md](VASP_TEST_TEMPLATES.md)。

## 常用入口

- 启动 TUI：`.venv/bin/python app.py`
- 本地全量检查：`hpc-agent-check`
- 真实 HPC 检查：`hpc-agent-check --live-hpc`
- 配置检查：在 TUI 输入 `检查我的超算配置`
- TUI 快捷帮助：`/help`
- Job 快捷帮助：`/help job`
- VASP 快捷帮助：`/help vasp`
- 清理/退出：`/clear`、`/clear all`、`/exit`

## 维护约定

- 根目录 [../README.md](../README.md) 保持项目概览、安装和核心能力说明。
- `docs/README.md` 只做文档索引和阅读路径，不重复长篇操作说明。
- 新增重要文档时，同步在本页登记。

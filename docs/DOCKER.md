# HPC Agent Docker 部署说明

Docker 是可选部署方式，用来提供固定、可复现的 Python 运行环境。普通用户仍然推荐使用私服 `install.sh` 安装；Docker 更适合服务器、运维环境、演示环境和统一测试环境。

## 一、前提条件

执行位置：项目根目录。

```bash
cd ~/projects/hpc-agent
```

确认已经有当前版本的 wheel 包：

```bash
export HPC_AGENT_VERSION=0.2.4
ls -lh "dist/hpc_agent-${HPC_AGENT_VERSION}-py3-none-any.whl"
```

预期结果：能看到当前版本的 wheel，例如 `dist/hpc_agent-0.2.4-py3-none-any.whl`。

如果没有，需要先重新打包：

```bash
.venv/bin/python -m build
```

## 二、构建镜像

执行位置：项目根目录。

```bash
docker build \
  --build-arg HPC_AGENT_VERSION="$HPC_AGENT_VERSION" \
  -t "hpc-agent:${HPC_AGENT_VERSION}" \
  .
```

预期结果：构建成功，并生成本地镜像，例如 `hpc-agent:0.2.4`。

检查镜像：

```bash
docker images hpc-agent
```

## 三、初始化配置

首次使用时，建议先让容器帮用户生成配置文件。

执行位置：任意目录都可以。

```bash
docker run --rm -it \
  --entrypoint hpc-agent-init \
  -v ~/.config/hpc-agent:/config \
  -v ~/.local/share/hpc-agent:/data \
  -v ~/.cache/hpc-agent:/cache \
  "hpc-agent:${HPC_AGENT_VERSION}"
```

预期结果：宿主机上生成或保留配置文件：

```bash
~/.config/hpc-agent/.env
```

## 四、填写配置

执行位置：宿主机终端。

```bash
nano ~/.config/hpc-agent/.env
```

至少填写这些配置：

```bash
PARATERA_BASE_URL=模型 API 地址
PARATERA_API_KEY=模型 API Key
HPC_HOST=超算登录地址
HPC_USERNAME=超算用户名
HPC_KEY_PATH=/ssh/id_ed25519
HPC_REMOTE_WORKDIR=超算上的工作目录
```

注意：Docker 容器里看不到宿主机原始路径，所以 `HPC_KEY_PATH` 要写容器内路径。下面运行命令会把宿主机 `~/.ssh` 挂载到容器 `/ssh`，所以私钥路径应写成：

```bash
HPC_KEY_PATH=/ssh/id_ed25519
```

如果需要 VASP 作业功能，还要配置本地输入输出目录和报告模型：

```bash
HPC_LOCAL_VASP_JOBS_INPUT_DIR=/vasp-input
HPC_LOCAL_VASP_JOBS_OUTPUT_DIR=/vasp-output
HPC_VASP_REPORT_MODEL=DeepSeek-V4-Pro
```

然后在宿主机创建对应目录：

```bash
mkdir -p ~/vasp-jobs-input ~/vasp-jobs-output
```

## 五、运行检查

执行位置：任意目录都可以。

```bash
docker run --rm -it \
  --entrypoint hpc-agent-check \
  -v ~/.config/hpc-agent:/config \
  -v ~/.local/share/hpc-agent:/data \
  -v ~/.cache/hpc-agent:/cache \
  -v ~/.ssh:/ssh:ro \
  -v ~/vasp-jobs-input:/vasp-input \
  -v ~/vasp-jobs-output:/vasp-output \
  "hpc-agent:${HPC_AGENT_VERSION}"
```

预期结果：

- 包入口、RAG 文档、Skills Registry 应为 `OK`。
- 如果 `.env` 还没填真实值，SSH、API、远端目录可能出现 `WARN`，这是正常的。
- 填好真实超算配置后，再运行检查，关键项应逐步变成 `OK`。

## 六、启动 Agent

执行位置：任意目录都可以。

```bash
docker run --rm -it \
  -v ~/.config/hpc-agent:/config \
  -v ~/.local/share/hpc-agent:/data \
  -v ~/.cache/hpc-agent:/cache \
  -v ~/.ssh:/ssh:ro \
  -v ~/vasp-jobs-input:/vasp-input \
  -v ~/vasp-jobs-output:/vasp-output \
  "hpc-agent:${HPC_AGENT_VERSION}"
```

预期结果：进入 HPC Agent 的交互界面。

## 七、使用 docker compose

执行位置：项目根目录。

构建镜像：

```bash
docker compose build
```

运行检查：

```bash
docker compose run --rm --entrypoint hpc-agent-check hpc-agent
```

启动 Agent：

```bash
docker compose run --rm hpc-agent
```

## 八、版本更新

发布新版本时，先生成新的 wheel，例如：

```bash
.venv/bin/python -m build
```

然后用新版本号重新构建镜像：

```bash
export HPC_AGENT_VERSION=0.2.4
docker build \
  --build-arg HPC_AGENT_VERSION="$HPC_AGENT_VERSION" \
  -t "hpc-agent:${HPC_AGENT_VERSION}" \
  .
```

如果使用 `docker-compose.yml`，同步修改里面的版本号：

```yaml
args:
  HPC_AGENT_VERSION: ${HPC_AGENT_VERSION:-0.2.4}
image: hpc-agent:${HPC_AGENT_VERSION:-0.2.4}
```

## 九、和 install.sh 的关系

- `install.sh` 是普通用户主线安装方式，适合本地直接使用。
- Docker 是可选补充，适合统一运行环境、服务器部署和集成测试。
- Docker 不会消除用户配置需求，`.env`、SSH 私钥、VASP 输入输出目录仍然需要由用户提供。

## 十、Claude Code / VASP 报告注意事项

VASP 报告功能会调用 `HPC_CLAUDE_CODE_COMMAND` 指向的命令。当前 Docker 镜像默认没有内置 Claude Code CLI。

如果用户需要在 Docker 内执行 VASP 报告分析，需要额外满足其中一种条件：

- 在镜像中额外安装 Claude Code CLI。
- 把宿主机可执行的 Claude Code 命令挂载进容器，并在 `.env` 中配置容器内路径。
- 暂时在宿主机安装版中使用 VASP 报告功能。

因此，Docker 版目前最适合运行基础 Agent、配置检查、Slurm/HPC 连接检查，以及不依赖宿主机 Claude Code CLI 的功能。

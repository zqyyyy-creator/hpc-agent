---
name: get-available-resources
description: Detect local CPU, GPU, memory, and disk resources before computationally intensive scientific or HPC tasks.
type: tool
intents:
  - check_local_resources
handler: modules.skills.resource_detector.detect_resources_for_agent
runtime:
  adapter: question_to_text
metadata:
  version: "0.1"
  author: "K-Dense-AI scientific-agent-skills, adapted for HPC Agent"
  source_repo: "https://github.com/K-Dense-AI/scientific-agent-skills"
  source_skill: "skills/get-available-resources"
---

# Get Available Resources Skill

This skill is adapted from `K-Dense-AI/scientific-agent-skills`:

```text
skills/get-available-resources
```

Original purpose: detect available computational resources before
computationally intensive scientific work, including CPU cores, GPUs, memory,
disk space, and strategy recommendations.

## Local Adaptation

In this HPC Agent project, the skill is integrated through the normal runtime
protocol:

```yaml
runtime:
  adapter: question_to_text
handler: modules.skills.resource_detector.detect_resources_for_agent
```

The handler detects local resources and writes a JSON snapshot to:

```text
/tmp/hpc-agent/available_resources.json
```

This avoids polluting the project working tree while preserving the original
skill's resource snapshot idea.

## When This Skill Applies

Use this skill when the user asks about the current local execution
environment, such as:

- "检查本机可用资源"
- "当前机器有多少 CPU 和内存"
- "本地有没有 GPU"
- "detect available resources"
- "check local resources"

## Scope Boundary

This skill detects **local machine resources** only.

Do not use it for remote Slurm cluster questions such as:

- BSCC-A 有哪些 partition
- amd_test 能跑多久
- 超算队列资源怎么看
- sinfo 显示的节点状态是什么意思

Those questions should use RAG or Slurm/HPC tools.

## Output

The answer should summarize:

1. CPU logical cores
2. Memory total and available amount
3. Disk total and available amount
4. GPU count and detected backend
5. Recommended parallelism and memory strategy
6. JSON output path

## Safety Rules

1. Do not submit jobs.
2. Do not connect to the remote HPC cluster.
3. Do not modify project files.
4. Do not install packages automatically.
5. Treat GPU detection as best effort; missing `nvidia-smi` or `rocm-smi` should not be an error.

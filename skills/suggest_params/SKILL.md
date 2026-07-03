---
name: suggest-params
description: Suggest safe Slurm resource directives for HPC and VASP jobs from user resource questions.
type: rule
intents:
  - suggest_params
handler: modules.slurm.slurm_assistant.suggest_slurm_parameters
runtime:
  adapter: question_to_text
metadata:
  version: "0.1"
  author: "HPC Agent"
---

# Suggest Params Skill

This skill helps the HPC Agent suggest conservative Slurm resource parameters
for HPC jobs without submitting anything.

## When This Skill Applies

Use this skill when the user asks for concrete resource suggestions, such as:

- CPU core count
- memory request
- walltime
- GPU count
- Slurm directives for a described workload
- VASP resource suggestions when the user asks how many cores or how much time
  to request

Example user requests:

- "跑 VASP 结构优化需要多少核"
- "帮我看看需要多少核再提交"
- "我这个 Python 作业需要 4 核 10 分钟，参数怎么写"
- "GPU 训练作业应该怎么写资源参数"

## Inputs to Extract

The assistant should identify these parameters when present:

- `cpus_per_task`
- `memory`
- `time`
- `gpu_count`
- `job_type`, such as VASP, Python, MPI, GPU training, or shell job

## Default Values

If the request does not provide concrete values, use conservative defaults from
the underlying Slurm assistant:

- `cpus_per_task`: `1`
- `time`: `00:10:00`
- `output_file`: `%x_%j.out`
- `error_file`: `%x_%j.err`

Do not invent a partition, account, QoS, reservation, or node list.

## Safety Rules

1. Do not submit jobs.
2. Do not create or modify files.
3. Do not invent cluster-specific partitions unless the user or RAG context
   explicitly provides them.
4. Keep suggestions as Slurm directives, not a full submission workflow.
5. If the user asks conceptual "how to choose resources" questions, RAG may be
   more appropriate than this skill.
6. If the user asks to submit after reviewing resources, still require the
   normal explicit submit confirmation flow.

## Workflow

1. Read the resource request.
2. Extract explicit CPU, memory, time, and GPU requirements.
3. Apply conservative defaults for missing values.
4. Return Slurm `#SBATCH` directives only.
5. Mention that cluster-specific partition/account settings should be verified
   separately when needed.

## Output Format

Output a concise Slurm parameter suggestion, for example:

```text
建议使用以下 Slurm 参数：

#SBATCH --cpus-per-task=4
#SBATCH --time=00:10:00
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err
```

---
name: diagnose-error
description: Diagnose common HPC, Slurm, CUDA, Python, permission, memory, and runtime errors from user-provided logs.
metadata:
  version: "0.1"
  author: "QYz"
---

# Diagnose Error Skill

This skill helps the HPC Agent analyze user-provided error logs from HPC and Slurm jobs.

## When This Skill Applies

Use this skill when the user provides or asks about:

- Slurm job failure logs
- Python traceback messages
- CUDA or GPU errors
- out-of-memory errors
- permission errors
- module or package import errors
- invalid Slurm parameters
- segmentation faults
- time limit failures
- job submission failures

Example user requests:

- "CUDA out of memory"
- "我的作业运行失败了，日志里有 Permission denied"
- "ModuleNotFoundError: No module named torch"
- "slurmstepd: error: Detected 1 oom-kill event"
- "sbatch: error: Batch job submission failed: Invalid partition name"

## Inputs to Extract

The assistant should identify the following information from the user's log or message:

- `error_type`: broad category, such as Slurm, CUDA, Python, permission, memory, or runtime
- `matched_keywords`: important matched error phrases
- `possible_reason`: likely cause of the error
- `solution`: practical fix or next action
- `related_commands`: commands that can help diagnose the issue
- `sbatch_fix`: optional Slurm directive changes if the error can be fixed by adjusting a script

## Supported Error Categories

The skill should focus on common HPC job issues:

- CUDA out of memory
- Slurm out-of-memory kill
- job time limit exceeded
- invalid partition
- permission denied
- missing Python module
- command not found
- no GPU detected
- segmentation fault
- disk quota or file system errors

## Safety Rules

Follow these rules strictly:

1. Do not claim certainty if the log is incomplete.
2. Do not invent cluster-specific partition names, account names, node names, or QoS names.
3. Do not recommend destructive cleanup commands such as `rm -rf` without clear user confirmation.
4. Prefer diagnostic commands that only read state, such as `squeue`, `sacct`, `scontrol`, `sinfo`, `df`, and `quota`.
5. If suggesting an sbatch fix, keep the change minimal and explain why it helps.
6. If no known error is matched, ask the user for more complete logs.
7. Do not execute commands automatically.

## Workflow

When using this skill, follow this process:

1. Read the user-provided log or error message.
2. Match the text against known HPC and Slurm error patterns.
3. Identify the most likely error category.
4. Explain the likely cause in plain language.
5. Provide practical fix suggestions.
6. Include safe diagnostic commands when useful.
7. If applicable, suggest minimal sbatch directive changes.

## Output Format

The assistant should output:

1. Diagnosis result
2. Likely cause
3. Suggested fix
4. Optional diagnostic commands
5. Optional sbatch adjustment

Example:

```text
诊断结果：
1. CUDA out of memory
   类型: GPU / Memory
   可能原因: GPU 显存不足，模型或 batch size 超过当前 GPU 可用显存。
   解决方案: 减小 batch size，使用更小模型，或申请更多/更大显存 GPU。
   推荐排查命令:
     - nvidia-smi
     - squeue -j <job_id>
```

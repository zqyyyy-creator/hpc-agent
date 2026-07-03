---
name: generate-sbatch
description: Generate a safe Slurm sbatch script for HPC jobs based on user requirements.
type: tool
intents:
  - generate_sbatch
handler: modules.slurm.slurm_assistant.generate_sbatch_script
runtime:
  adapter: question_to_text
metadata:
  version: "0.1"
  author: "HPC Agent"
---

# Generate SBATCH Skill

This skill helps the HPC Agent generate safe and basic Slurm `sbatch` scripts from natural language user requests.

## When This Skill Applies

Use this skill when the user asks to:

- create a Slurm job script
- generate an `sbatch` script
- submit a Python, shell, or compiled program to an HPC cluster
- request CPU cores, memory, runtime, GPU, output file, or error file
- convert a natural language job request into a runnable Slurm script

Example user requests:

- "帮我生成一个 4 核、运行 10 分钟的 Python 作业脚本"
- "Create an sbatch script to run train.py on 1 GPU"
- "我想提交一个需要 8GB 内存的作业"
- "Generate a Slurm script for running main.py"

## Inputs to Extract

The assistant should identify the following parameters from the user request:

- `job_name`: name of the Slurm job
- `cpus_per_task`: number of CPU cores
- `memory`: memory requirement, such as `4G`, `8G`, or `16G`
- `time`: runtime limit, such as `00:10:00`, `01:00:00`, or `1-00:00:00`
- `gpu`: whether GPU is required
- `gpu_count`: number of GPUs if requested
- `command`: command to run, such as `python main.py`
- `output_file`: Slurm output file path
- `error_file`: Slurm error file path

## Default Values

If the user does not provide some parameters, use safe generic defaults:

- `job_name`: `hpc_agent_job`
- `cpus_per_task`: `1`
- `memory`: not included unless the user specifies it
- `time`: `00:10:00`
- `gpu`: not included unless the user explicitly asks for GPU
- `command`: ask the user for the command if missing
- `output_file`: `%x_%j.out`
- `error_file`: `%x_%j.err`

## Safety Rules

Follow these rules strictly:

1. Do not invent cluster-specific partition names.
2. Do not invent account names, node names, QoS names, or reservation names.
3. Do not add `#SBATCH --partition` unless the user or cluster documentation provides it.
4. Do not add `#SBATCH --account` unless the user or cluster documentation provides it.
5. Do not execute the generated script automatically.
6. Do not run arbitrary shell commands.
7. Do not include destructive commands such as `rm -rf`, `shutdown`, `reboot`, or commands that modify system files.
8. If the command is missing, ask for it instead of guessing.
9. If GPU is requested, use a generic Slurm GPU directive only if appropriate:
   `#SBATCH --gres=gpu:<gpu_count>`
10. Keep the generated script simple and readable.

## Workflow

When using this skill, follow this process:

1. Understand the user's natural language request.
2. Extract Slurm job parameters.
3. Check for missing required information.
4. Apply safe defaults for optional fields.
5. Generate a clean `sbatch` script.
6. Briefly explain how to save and submit the script.
7. Remind the user to verify cluster-specific settings such as partition or account if needed.

## Output Format

The assistant should output:

1. A short explanation
2. The generated `sbatch` script
3. The command to save or submit it

Example:

```bash
sbatch job.sh

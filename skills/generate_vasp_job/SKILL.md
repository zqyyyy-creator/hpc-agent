---
name: generate-vasp-job
description: Generate a safe minimal Slurm sbatch script for VASP jobs.
metadata:
  version: "0.1"
  author: "QYz"
---

# Generate VASP Job Skill

This skill helps the HPC Agent generate a safe, minimal Slurm `sbatch`
script for VASP calculations.

## When This Skill Applies

Use this skill when the user asks to:

- run or submit a VASP job
- generate a VASP `sbatch` script
- run calculations that mention `INCAR`, `POSCAR`, `POTCAR`, `KPOINTS`
- run `vasp_std`, `vasp_gam`, or `vasp_ncl`
- run structure optimization, static calculation, band structure, or DOS jobs

Example user requests:

- "帮我提交一个 VASP 结构优化任务，1 个节点 32 核，运行 24 小时"
- "Generate a Slurm script for vasp_std using 64 cores"
- "我想运行 VASP 静态计算，命令是 mpirun vasp_std"

## Inputs to Extract

Identify these parameters from the user request:

- `job_name`: Slurm job name
- `nodes`: number of nodes
- `ntasks_per_node`: MPI tasks per node
- `time`: runtime limit
- `partition`: only if the user or cluster config provides it
- `vasp_module`: software module to load, if configured
- `command`: VASP command, such as `vasp_std`, `srun vasp_std`, or `mpirun vasp_std`
- `calculation_type`: structure optimization, static, band, DOS, or unknown

## Default Values

Use conservative defaults when the user does not provide values:

- `job_name`: `vasp_job`
- `nodes`: `1`
- `ntasks_per_node`: `32`
- `time`: `24:00:00`
- `command`: configured default VASP command, otherwise `vasp_std`
- `output_file`: `%x_%j.out`
- `error_file`: `%x_%j.err`

## Safety Rules

1. Do not invent account names, QoS names, reservation names, or node names.
2. Do not add `#SBATCH --account` unless the user or cluster config provides it.
3. Do not generate `POTCAR` content.
4. Do not execute the generated script automatically.
5. Submission must require explicit user confirmation.
6. Check that `INCAR`, `POSCAR`, `POTCAR`, and `KPOINTS` exist in the run directory.
7. Do not include destructive commands.
8. Keep the first version simple and readable.

## Workflow

1. Understand the VASP calculation request.
2. Extract Slurm resource parameters.
3. Apply safe defaults for missing optional values.
4. Generate a minimal `sbatch` script.
5. Include a preflight input-file check.
6. Remind the user that input files must already be in the remote work directory.
7. Ask for confirmation before submission.

## Output Format

Output:

1. A short explanation
2. The generated `sbatch` script
3. A note about required VASP input files

---
name: generate-vasp-inputs
description: Generate VASP INCAR, KPOINTS, and POSCAR files from an existing POTCAR in a local VASP job directory.
type: tool
intents:
  - generate_vasp_inputs
handler: modules.vasp.vasp_input_generator.generate_vasp_inputs_from_potcar_request
runtime:
  adapter: structured_result
  message_field: message
  success_field: success
  pending_action: generate_vasp_inputs_overwrite
metadata:
  version: "0.1"
  author: "HPC Agent"
---

# Generate VASP Inputs Skill

This skill generates VASP input files from a local VASP job directory that
already contains a real `POTCAR`.

## When This Skill Applies

Use this skill when the user asks to generate:

- `INCAR`
- `KPOINTS`
- `POSCAR`
- VASP input files
- VASP configuration files

Example requests:

- "帮我生成我的 VASP 作业 Al_test 的配置文件"
- "帮我生成 Al_test 的 VASP 输入，ENCUT 400，KPOINTS 2x2x2"
- "/vasp gen Al_test"

## Runtime Integration

This skill uses a structured result adapter:

```yaml
runtime:
  adapter: structured_result
  message_field: message
  success_field: success
  pending_action: generate_vasp_inputs_overwrite
```

The handler returns a dictionary. The runtime uses:

- `message` as the user-facing answer
- `success` as the runtime success flag
- the full result dictionary as `AgentRuntimeResult.data`

If the target directory already contains generated VASP input files, the runtime
creates a pending overwrite action instead of writing files automatically.

## Safety Rules

1. Do not generate or reconstruct `POTCAR`.
2. Only generate `INCAR`, `KPOINTS`, and `POSCAR`.
3. Do not overwrite existing input files without explicit confirmation.
4. If only `POTCAR` is available, keep generated structures conservative and
   clearly warn when the structure is a smoke-test placeholder.
5. Validate user-provided numerical parameters before writing files.

## Output

The skill should return:

1. success/failure status
2. target job directory
3. detected element order
4. generated parameter summary
5. written files, or a pending overwrite action if files already exist

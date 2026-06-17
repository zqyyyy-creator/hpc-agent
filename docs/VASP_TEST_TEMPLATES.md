# VASP Test Templates

本文档定义 HPC Agent 推荐使用的 VASP 标准测试模板。它用于真实测试、演示和后续功能扩展，不会被当前程序自动执行，也不影响现有代码逻辑。

目标：

- 给 VASP 输入生成、提交、监控、同步和报告生成提供稳定测试样例。
- 避免每次临时选择体系导致测试结果不可复现。
- 为新手提供从简单到稍复杂的 VASP 作业练习路径。
- 后续可扩展为 Agent 可读取的模板库。

建议原则：

- 优先选择小体系、短作业、低资源消耗。
- 每个模板都应明确元素、任务类型、输入文件、资源建议和通过标准。
- 模板默认用于功能测试，不直接代表正式科研参数。
- 所有模板都应提醒用户：正式计算前需要根据材料体系、赝势版本和研究目标重新检查参数。

---

## 1. 模板总览

| 模板名 | 体系 | 复杂度 | 主要验证目标 | 推荐用途 |
| --- | --- | --- | --- | --- |
| `Al_static_test` | Al 金属 | 低 | 单元素 POTCAR、静态计算、快速提交链路 | 最小 VASP smoke test |
| `Si_static_test` | Si 半导体 | 低 | 单元素半导体、静态计算、与既有测试兼容 | 回归测试 |
| `MgO_static_test` | MgO 离子晶体 | 中 | 双元素 POTCAR、多元素 POSCAR、绝缘体输出 | 多元素测试 |
| `NaCl_static_test` | NaCl 离子晶体 | 中 | 双元素体系、不同元素组合 | 多元素泛化测试 |
| `Si_relax_test` | Si 半导体 | 中 | 结构优化、离子步、CONTCAR 输出 | relax 流程测试 |

---

## 2. 通用默认参数

这些参数只适合测试用途。

### 静态计算默认 INCAR

```text
SYSTEM = VASP static test
ENCUT = 520
EDIFF = 1E-5
ISMEAR = 0
SIGMA = 0.05
IBRION = -1
NSW = 0
ISIF = 2
PREC = Accurate
LREAL = Auto
LWAVE = .FALSE.
LCHARG = .FALSE.
```

说明：

- `IBRION = -1`、`NSW = 0` 表示静态计算。
- `ISMEAR = 0` 更适合半导体/绝缘体；金属 Al 正式计算可考虑 `ISMEAR = 1` 或其他设置。
- `ENCUT = 520` 是偏保守测试值，正式计算应结合 POTCAR 推荐值检查。

### 结构优化默认 INCAR

```text
SYSTEM = VASP relax test
ENCUT = 520
EDIFF = 1E-5
EDIFFG = -0.02
ISMEAR = 0
SIGMA = 0.05
IBRION = 2
NSW = 50
ISIF = 3
PREC = Accurate
LREAL = Auto
LWAVE = .FALSE.
LCHARG = .FALSE.
```

说明：

- `IBRION = 2` 用于共轭梯度优化。
- `NSW = 50` 对小测试体系足够。
- `ISIF = 3` 同时优化离子和晶胞，正式计算前需要确认是否符合研究目标。

### 默认 KPOINTS

小晶胞测试可用：

```text
Automatic mesh
0
Gamma
6 6 6
0 0 0
```

更快 smoke test 可用：

```text
Automatic mesh
0
Gamma
4 4 4
0 0 0
```

说明：

- `4 4 4` 更快，适合链路测试。
- `6 6 6` 更稳，适合报告/收敛输出测试。
- 正式计算应做 k 点收敛测试。

### 默认 sbatch 资源建议

```text
nodes = 1
ntasks = 4
time = 00:10:00
partition = 使用 HPC_VASP_PARTITION 或集群默认
```

说明：

- 轻量测试优先短时间、少核。
- 如果队列拥堵，可先用普通 hostname 测试确认 Slurm 链路，再提交 VASP。

---

## 3. `Al_static_test`

### 目标

验证最小单元素 VASP 静态计算链路。

适合测试：

- POTCAR 单元素解析。
- INCAR / KPOINTS / POSCAR 生成。
- VASP 作业提交。
- Job Monitor 基本状态。
- 输出同步和作业详情。

### 前置 POTCAR

推荐远端来源：

```text
<REMOTE_POTCAR_ROOT>/Al/POTCAR
```

本地目标目录：

```text
$HPC_LOCAL_VASP_JOBS_INPUT_DIR/Al_test/POTCAR
```

### 推荐 POSCAR

```text
Al fcc test
1.0
4.050000 0.000000 0.000000
0.000000 4.050000 0.000000
0.000000 0.000000 4.050000
Al
4
Direct
0.000000 0.000000 0.000000
0.000000 0.500000 0.500000
0.500000 0.000000 0.500000
0.500000 0.500000 0.000000
```

### 推荐用户指令

```text
帮我生成我的vasp作业Al_test的配置文件
提交 VASP 作业，路径为 $HPC_LOCAL_VASP_JOBS_INPUT_DIR/Al_test
查看最近作业
查看作业详情 <JobID>
同步 VASP 作业 <JobID> 输出
诊断作业 <JobID>
```

### 通过标准

- Agent 能生成 `INCAR`、`KPOINTS`、`POSCAR`。
- 提交后能得到 Job ID。
- OSZICAR / OUTCAR 非空。
- `查看作业详情 <JobID>` 能显示本地和远端路径。
- 同步后 `raw_output` 和 `analysis/report_context.md` 存在。

---

## 4. `Si_static_test`

### 目标

验证单元素半导体静态计算，并作为已有 `si_static_test` 的回归模板。

适合测试：

- 单元素但非金属体系。
- 已有 Si 流程回归。
- 静态计算报告生成。

### 前置 POTCAR

推荐远端来源：

```text
<REMOTE_POTCAR_ROOT>/Si/POTCAR
```

本地目标目录：

```text
$HPC_LOCAL_VASP_JOBS_INPUT_DIR/si_static_test/POTCAR
```

### 推荐 POSCAR

```text
Si diamond static test
1.0
5.430000 0.000000 0.000000
0.000000 5.430000 0.000000
0.000000 0.000000 5.430000
Si
8
Direct
0.000000 0.000000 0.000000
0.000000 0.500000 0.500000
0.500000 0.000000 0.500000
0.500000 0.500000 0.000000
0.250000 0.250000 0.250000
0.250000 0.750000 0.750000
0.750000 0.250000 0.750000
0.750000 0.750000 0.250000
```

### 推荐用户指令

```text
帮我生成我的vasp作业si_static_test的配置文件
提交 VASP 作业，路径为 $HPC_LOCAL_VASP_JOBS_INPUT_DIR/si_static_test
帮我分析 VASP 作业 <JobID>
```

### 通过标准

- 能完整走通输入生成、提交、同步、报告生成。
- 报告不编造未在 `report_context.md` 中出现的数据。

---

## 5. `MgO_static_test`

### 目标

验证双元素离子晶体 VASP 作业。

适合测试：

- 多元素 POTCAR 组合。
- POSCAR 元素顺序与 POTCAR 顺序一致。
- OUTCAR / OSZICAR 解析。
- VASP 作业诊断。

### 前置 POTCAR

推荐拼接顺序：

```text
Mg
O
```

远端来源：

```text
<REMOTE_POTCAR_ROOT>/Mg/POTCAR
<REMOTE_POTCAR_ROOT>/O/POTCAR
```

本地目标目录：

```text
$HPC_LOCAL_VASP_JOBS_INPUT_DIR/MgO_test/POTCAR
```

### 推荐 POSCAR

```text
MgO rocksalt static test
1.0
4.210000 0.000000 0.000000
0.000000 4.210000 0.000000
0.000000 0.000000 4.210000
Mg O
4 4
Direct
0.000000 0.000000 0.000000
0.000000 0.500000 0.500000
0.500000 0.000000 0.500000
0.500000 0.500000 0.000000
0.500000 0.500000 0.500000
0.500000 0.000000 0.000000
0.000000 0.500000 0.000000
0.000000 0.000000 0.500000
```

### 推荐用户指令

```text
帮我生成我的vasp作业MgO_test的配置文件
提交 VASP 作业，路径为 $HPC_LOCAL_VASP_JOBS_INPUT_DIR/MgO_test
查看作业详情 <JobID>
同步 VASP 作业 <JobID> 输出
帮我分析 VASP 作业 <JobID>
```

### 通过标准

- Agent 正确识别 Mg / O。
- 输出目录同步后能生成 `report_context.md`。
- `诊断作业 <JobID>` 不应把正常收敛误判成失败。

---

## 6. `NaCl_static_test`

### 目标

验证另一个双元素体系，避免多元素逻辑只对 MgO 测试有效。

适合测试：

- 多元素泛化。
- POTCAR 拼接顺序检查。
- 轻量静态计算。

### 前置 POTCAR

推荐拼接顺序：

```text
Na
Cl
```

远端来源：

```text
<REMOTE_POTCAR_ROOT>/Na/POTCAR
<REMOTE_POTCAR_ROOT>/Cl/POTCAR
```

本地目标目录：

```text
$HPC_LOCAL_VASP_JOBS_INPUT_DIR/NaCl_test/POTCAR
```

### 推荐 POSCAR

```text
NaCl rocksalt static test
1.0
5.640000 0.000000 0.000000
0.000000 5.640000 0.000000
0.000000 0.000000 5.640000
Na Cl
4 4
Direct
0.000000 0.000000 0.000000
0.000000 0.500000 0.500000
0.500000 0.000000 0.500000
0.500000 0.500000 0.000000
0.500000 0.500000 0.500000
0.500000 0.000000 0.000000
0.000000 0.500000 0.000000
0.000000 0.000000 0.500000
```

### 推荐用户指令

```text
帮我生成我的vasp作业NaCl_test的配置文件
提交 VASP 作业，路径为 $HPC_LOCAL_VASP_JOBS_INPUT_DIR/NaCl_test
查看最近作业
列出 VASP 作业
```

### 通过标准

- Agent 正确识别 Na / Cl。
- 不误用 MgO 或 Si 的结构信息。
- 本地 VASP 作业列表能显示该作业。

---

## 7. `Si_relax_test`

### 目标

验证结构优化流程。

适合测试：

- `IBRION` / `NSW` / `EDIFFG` 等 relax 参数。
- 离子步输出。
- `CONTCAR` 生成。
- 结构优化状态诊断。

### 前置 POTCAR

推荐远端来源：

```text
<REMOTE_POTCAR_ROOT>/Si/POTCAR
```

本地目标目录：

```text
$HPC_LOCAL_VASP_JOBS_INPUT_DIR/Si_relax_test/POTCAR
```

### 推荐 POSCAR

可使用 `Si_static_test` 的 diamond 结构，或轻微扰动原子坐标以测试优化。

### 推荐用户指令

```text
帮我生成一个 VASP 结构优化脚本
帮我生成我的vasp作业Si_relax_test的配置文件
提交 VASP 作业，路径为 $HPC_LOCAL_VASP_JOBS_INPUT_DIR/Si_relax_test
同步 VASP 作业 <JobID> 输出
诊断作业 <JobID>
```

### 通过标准

- INCAR 使用结构优化参数。
- OUTCAR / OSZICAR 中有离子步记录。
- 作业完成后存在 `CONTCAR`。
- Agent 能区分电子步和离子步相关信息。

---

## 8. 后续 Agent 功能设计

未来可以让 Agent 直接支持这些自然语言命令：

```text
列出 VASP 测试模板
用 Al_static_test 模板生成 VASP 测试作业
用 MgO_static_test 模板准备输入文件
查看 NaCl_static_test 模板详情
```

建议内部意图名：

```text
list_vasp_templates
show_vasp_template
generate_vasp_from_template
```

建议模板数据结构：

```json
{
  "name": "Al_static_test",
  "system": "Al fcc",
  "task": "static",
  "elements": ["Al"],
  "potcar_order": ["Al"],
  "recommended_kpoints": "6 6 6",
  "recommended_resources": {
    "nodes": 1,
    "ntasks": 4,
    "time": "00:10:00"
  },
  "warnings": [
    "This template is for smoke testing, not production research."
  ]
}
```

---

## 9. Live Test 对应关系

| Live test 项目 | 推荐模板 |
| --- | --- |
| 最小 VASP 提交链路 | `Al_static_test` |
| 已有 Si 回归 | `Si_static_test` |
| 多元素 POTCAR | `MgO_static_test` |
| 多元素泛化 | `NaCl_static_test` |
| 结构优化流程 | `Si_relax_test` |

每次修改 VASP 输入生成、提交、同步、报告相关逻辑后，至少应跑：

```text
Al_static_test
MgO_static_test
```

准备演示或阶段验收时，建议跑：

```text
Al_static_test
MgO_static_test
NaCl_static_test
```

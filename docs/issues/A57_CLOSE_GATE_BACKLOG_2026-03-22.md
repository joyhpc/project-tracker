# Close Gate 未闭环总表

> 项目: `A57 域控测试盒` / `A57`
> 文档性质: 自动生成
> 目的: 汇总当前所有未通过 Merge-to-Close 的任务、缺失字段和正式回写落点

## 1. 汇总

| 任务 | 状态 | Docs Anchor | 回写路径 | 人工待补字段 |
|---|---|---|---|---|
| `fpga_dev.mipi_3g5_verify.verdict` 验证结论与GO/NO-GO判定 | `pending` | `A57.CAMRX.HS_3P5G.CURRENT` | `01_需求阶段_Requirements/00_项目级需求_Project_Level/CAMRX_3.5Gbps_当前有效结论页.md` | `sample_entity_id, firmware_version, fpga_version, pcb_version, bom_version, evidence_paths` |
| `dcurx_integration` DCURX 软硬件联调 | `pending` | `A57.DCURX.EDP_OLDI.EXEC_V1_V2` | `01_需求阶段_Requirements/00_项目级需求_Project_Level/DCURX_V1_V2_执行记录页.md` | `sample_entity_id, protocol_object_id, firmware_version, fpga_version, bom_version, evidence_paths` |
| `camrx_integration` CAMRX 软硬件联调 | `pending` | `A57.CAMRX.HS_3P5G.EXEC_V1_V2` | `01_需求阶段_Requirements/00_项目级需求_Project_Level/CAMRX_V1_V2_执行记录页.md` | `sample_entity_id, firmware_version, fpga_version, pcb_version, bom_version, evidence_paths` |
| `dcurx_fmc_ecn` DCURX核心板 QSPI→FMC改线(ECN-001) | `in_progress` | `A57.DCURX.CONTROL_PLANE.GONOGO` | `01_需求阶段_Requirements/00_项目级需求_Project_Level/DCURX_控制平面Go_No-Go执行记录页.md` | `sample_entity_id, borrowed_object_id, firmware_version, fpga_version, bom_version, evidence_paths` |

## 2. 明细

### fpga_dev.mipi_3g5_verify.verdict - 验证结论与GO/NO-GO判定

- `status`: `pending`
- `close_mode`: `merged_fix`
- `formal_object_id`: `CAMRX_MAIN`
- `docs_anchor`: `A57.CAMRX.HS_3P5G.CURRENT`
- `docs_backwrite_path`: `01_需求阶段_Requirements/00_项目级需求_Project_Level/CAMRX_3.5Gbps_当前有效结论页.md`
- `human_fields`: `sample_entity_id, firmware_version, fpga_version, pcb_version, bom_version, evidence_paths`
- `issues`:
  - 证据路径不存在: NEED_HUMAN_CHECK
- `human_template`:
  - `sample_entity_id`: `NEED_HUMAN_CHECK`
  - `firmware_version`: `NEED_HUMAN_CHECK`
  - `fpga_version`: `NEED_HUMAN_CHECK`
  - `pcb_version`: `NEED_HUMAN_CHECK`
  - `bom_version`: `NEED_HUMAN_CHECK`
  - `evidence_paths`: `NEED_HUMAN_CHECK`

### dcurx_integration - DCURX 软硬件联调

- `status`: `pending`
- `close_mode`: `merged_fix`
- `formal_object_id`: `DCURX_MAIN`
- `docs_anchor`: `A57.DCURX.EDP_OLDI.EXEC_V1_V2`
- `docs_backwrite_path`: `01_需求阶段_Requirements/00_项目级需求_Project_Level/DCURX_V1_V2_执行记录页.md`
- `human_fields`: `sample_entity_id, protocol_object_id, firmware_version, fpga_version, bom_version, evidence_paths`
- `issues`:
  - 证据路径不存在: NEED_HUMAN_CHECK
- `human_template`:
  - `sample_entity_id`: `NEED_HUMAN_CHECK`
  - `protocol_object_id`: `NEED_HUMAN_CHECK`
  - `firmware_version`: `NEED_HUMAN_CHECK`
  - `fpga_version`: `NEED_HUMAN_CHECK`
  - `bom_version`: `NEED_HUMAN_CHECK`
  - `evidence_paths`: `NEED_HUMAN_CHECK`

### camrx_integration - CAMRX 软硬件联调

- `status`: `pending`
- `close_mode`: `merged_fix`
- `formal_object_id`: `CAMRX_MAIN`
- `docs_anchor`: `A57.CAMRX.HS_3P5G.EXEC_V1_V2`
- `docs_backwrite_path`: `01_需求阶段_Requirements/00_项目级需求_Project_Level/CAMRX_V1_V2_执行记录页.md`
- `human_fields`: `sample_entity_id, firmware_version, fpga_version, pcb_version, bom_version, evidence_paths`
- `issues`:
  - 证据路径不存在: NEED_HUMAN_CHECK
- `human_template`:
  - `sample_entity_id`: `NEED_HUMAN_CHECK`
  - `firmware_version`: `NEED_HUMAN_CHECK`
  - `fpga_version`: `NEED_HUMAN_CHECK`
  - `pcb_version`: `NEED_HUMAN_CHECK`
  - `bom_version`: `NEED_HUMAN_CHECK`
  - `evidence_paths`: `NEED_HUMAN_CHECK`

### dcurx_fmc_ecn - DCURX核心板 QSPI→FMC改线(ECN-001)

- `status`: `in_progress`
- `close_mode`: `merged_fix`
- `formal_object_id`: `DCURX_MAIN`
- `docs_anchor`: `A57.DCURX.CONTROL_PLANE.GONOGO`
- `docs_backwrite_path`: `01_需求阶段_Requirements/00_项目级需求_Project_Level/DCURX_控制平面Go_No-Go执行记录页.md`
- `human_fields`: `sample_entity_id, borrowed_object_id, firmware_version, fpga_version, bom_version, evidence_paths`
- `issues`:
  - 证据路径不存在: NEED_HUMAN_CHECK
- `human_template`:
  - `sample_entity_id`: `NEED_HUMAN_CHECK`
  - `borrowed_object_id`: `NEED_HUMAN_CHECK`
  - `firmware_version`: `NEED_HUMAN_CHECK`
  - `fpga_version`: `NEED_HUMAN_CHECK`
  - `bom_version`: `NEED_HUMAN_CHECK`
  - `evidence_paths`: `NEED_HUMAN_CHECK`

# Hardware Closure Evidence Matrix

Status: current evidence checklist for the hardware closure gatekeeper protocol.

| Gate | 触发动作 | 缺失证据 | 必填字段 | 输出脚手架 |
|---|---|---|---|---|
| `Gate 1` | 选型、系统框图、总体方案 | 边界不清、控制权不清 | `NON_GOALS`, `OWNERSHIP_MATRIX` | Ownership 矩阵认领表 |
| `Gate 2` | 电源树、外围电路、Pin Assign | 功耗/引脚预算缺失 | `POWER_BUDGET`, `PIN_BUDGET`, `TIMING_DEP` | Power Budget 表、Pin Budget 表 |
| `Gate 3` | 原理图定稿、Layout 发板 | 测试点、默认态、Bring-up 计划缺失 | `TEST_POINT`, `DEFAULT_STATE`, `BRINGUP_PLAN` | TP 点位表、Level 1 Bring-up 计划表 |
| `Gate 4` | Bug 修复、飞线可跑、事项关闭 | 根因、回归、回写缺失 | `ROOT_CAUSE`, `REGRESSION_SCOPE`, `ISSUE_LOG`, `DOC_ANCHOR` | Issue/ECN 回写标准单 |

---

## A57 类项目附加字段

| 场景 | 必填字段 |
|---|---|
| 正式对象闭环 | `formal_object_id`, `sample_entity_id`, `version_anchor`, `evidence_path` |
| 借用验证对象 | `borrowed_object_id`, `borrowed_purpose`, `scope_statement` |
| 多板视频链路 | `board_id_rule`, `power_domain_isolation`, `state_reversible` |

---

## 统一口径

> 任何跨阶段硬件定稿动作，如果缺少矩阵中对应的证据字段，Agent 必须拦截并输出对应脚手架，而不是继续给最终设计。

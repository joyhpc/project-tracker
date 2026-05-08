# TASK_TRACKER

## Goal

将 `docs/MERGE_TO_CLOSE_PROTOCOL.md` 中的 Merge-to-Close 规则落成真实 CLI 命令：

- `pt close`
- `pt gate closure`
- `pt closure scaffold`

并完成测试、验证、自审。

## Checklist

- [x] 定位目标仓库并读取项目级约束文件
- [x] 读取 `AGENTS.md` 和 Merge-to-Close 相关文档，提炼行为规则
- [x] 盘点现有 CLI 路由、命令实现、数据模型和测试覆盖点
- [x] 设计命令行为与输出契约，写入 tracker 任务说明
- [x] 先写失败测试：`pt close`
- [x] 先写失败测试：`pt gate closure`
- [x] 先写失败测试：`pt closure scaffold`
- [x] 实现 `pt close`
- [x] 实现 `pt gate closure`
- [x] 实现 `pt closure scaffold`
- [x] 跑定向测试并修复失败
- [x] 跑全量测试并修复失败
- [x] 自我 Code Review：边界条件、异常处理、死逻辑
- [x] 根据 Review 修复问题并再次验证
- [x] 整理结果并完成最终确认

## Command Contract

- `pt close <task_id>`
  - 面向 Merge-to-Close 事项的一站式关闭命令。
  - 默认执行 closure gate 校验，校验不通过则拒绝关闭并退出非 0。
  - 校验通过后执行正式 `done`。
  - 支持 `--json` 输出机器可读结果。

- `pt gate closure <task_id>`
  - 作为 `close-check` 的正式分组命令别名，输出 closure gate 结果。
  - 支持 `--json`。

- `pt closure scaffold <task_id>`
  - 为节点补齐缺失的 `closure` 元数据骨架。
  - 不覆盖已有字段，只补缺失字段。
  - 默认写回项目 YAML，并输出补齐项；支持 `--dry-run`、`--json`。

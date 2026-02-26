# 超级LLM问题：Project Tracker 节点 CRUD 与 DAG 动态维护系统设计

## 背景

Project Tracker (pt) 是一个通用电子产品硬件项目智能推进 CLI 工具。核心数据模型是扁平 DAG（有向无环图）：所有任务/里程碑是 nodes 列表，phase 是属性标签，depends 写在节点里，支持跨阶段依赖。单文件自包含（YAML）。

### 当前痛点

项目执行过程中，需要频繁对 DAG 进行动态修改：
- **新增节点**：验证任务、设计变更(ECN)、临时采购、新发现的子任务
- **删除/归档节点**：方案废弃（如 JW7221 → LM5060 替换）
- **依赖重接**：新节点插入已有依赖链中间、方案变更导致上下游关系变化
- **批量操作**：一次性添加一组相关节点（如"CPHY验证"含5个子节点+内部依赖+外部接入）

目前这些操作全靠手写 Python 脚本，逐个创建节点、手动接依赖、手动检查完整性。问题：
1. **重复劳动** — 每次都写临时脚本，模式相同但无法复用
2. **容易出错** — 忘记接依赖导致孤立终点（已发生过，CAMRX slack 从 0 算成 27）
3. **无法回滚** — 批量修改出错后没有撤销机制
4. **AI Agent 无法自主操作** — Nova（AI助手）需要写原始 Python 才能改 DAG，没有稳定 API

### 现有系统概况

**数据模型**（单个节点）：
```yaml
id: cphy_bridge_verify          # 唯一标识
name: CAMRX CPHY桥接方案验证(60K) # 显示名
phase: DETAIL                    # 阶段标签
status: pending                  # pending/in_progress/done/blocked/skipped
depends: []                      # 上游依赖列表（节点ID）
days: 5                          # 预估工时
owner: 硬件工程师                 # 负责人
note: 用60K评估板验证             # 备注
deliverables: [...]              # 交付物
docs: [{path, desc, added}]      # 关联文档
```

**现有 API**（tracker/core.py，931行）：
- `init_project()` — 从流程模板创建项目（deep copy）
- `start_task()` / `done_task()` / `block_task()` — 状态变更
- `add_subtask()` — 添加子任务（当前实现是嵌套在父节点下，非一等节点）
- `check_integrity()` — 6类完整性检查（孤立终点、悬空依赖等）
- `get_status()` → CPM 关键路径分析

**缺失的能力**：
- 没有 `add_node()` — 添加一等节点到 DAG
- 没有 `remove_node()` — 从 DAG 移除节点（含依赖清理）
- 没有 `rewire()` — 依赖关系重接
- 没有 `batch_add()` — 批量添加一组节点
- 没有 `undo/history` — 操作回滚

**CLI 命令**（30个，cli.py 236行）：
```
init, list, switch, status, phases, note, log, tasks, next, start, done,
block, unblock, sub, sub-done, sub-block, sub-list, sub-load, plan, digest,
timeline, estimate, guide, risk, conflict, prompt, brief, review, decision,
poc, docs, propose, scan, visual
```

**引擎**（engine.py，315行）：
- CPM 前向/反向推导（ES/EF/LS/LF/Slack）
- Kahn 拓扑排序 + 环检测
- 关键路径提取

**完整性检查**（core.py check_integrity，~180行）：
- 孤立终点（无后继）
- 悬空依赖（依赖不存在的节点）
- 里程碑缺上游
- 反向跨阶段依赖
- 重复ID
- 完全孤立节点

**代码量**：~3200行 | 19模块 | 30命令

---

## 核心问题

### Q1: 节点 CRUD API 设计

在扁平 DAG + 单文件 YAML 的约束下，如何设计节点增删改的 API，使其：

1. **原子性** — 单次操作要么全部成功，要么全部回滚（尤其批量操作）
2. **完整性保证** — 每次修改后自动验证 DAG 完整性（无孤立终点、无悬空依赖、无环）
3. **最小惊讶** — 删除节点时自动处理依赖关系（下游节点的 depends 怎么办？）

具体子问题：

**Q1.1: add_node 的接入策略**

添加节点时，除了指定 `depends`（上游），还需要指定"接入下游"。当前做法是手动找到下游节点并修改其 depends。

方案空间：
- A: 只指定 depends，不管下游（调用者自己接）
- B: 提供 `--before <node_id>` 参数，自动将新节点插入为目标节点的新依赖
- C: 提供 `--between <upstream> <downstream>` 参数，插入到两个节点之间
- D: 基于 phase 自动推断接入点（同阶段的里程碑节点？）

哪种方案（或组合）在"通用性 vs 易用性"上最优？考虑到用户是 AI Agent + 硬件工程师。

**Q1.2: remove_node 的依赖清理策略**

删除节点 X 时，X 的下游节点依赖了 X。处理策略：
- A: 下游的 depends 中删除 X（可能导致下游变成无依赖的悬空节点）
- B: 下游的 depends 中用 X 的上游替换 X（依赖链自动缝合）
- C: 拒绝删除有下游的节点（强制先手动重接）
- D: 标记为 archived/skipped 而非真删除

哪种策略最安全？是否应该区分"软删除"和"硬删除"？

**Q1.3: 批量操作的事务性**

一次添加 5 个节点 + 3 条依赖关系，中间某步失败（如 ID 冲突、环检测失败）。如何回滚？

当前 YAML 单文件存储，没有事务机制。方案空间：
- A: 操作前备份 YAML，失败时恢复
- B: 内存中构建完整新状态，验证通过后一次性写入
- C: 引入操作日志（operation log），支持 undo
- D: Git 级别的回滚（每次操作自动 commit，失败时 git reset）

### Q2: 依赖重接（rewire）的设计

场景：方案变更时，需要将 DAG 中一个节点替换为另一个（或一组）节点。

例：JW7221 热插拔方案 → LM5060 方案
- 原来：`power_design → jw7221_verify → schematic`
- 现在：`power_design → lm5060_verify → schematic`（jw7221_verify 废弃）

**Q2.1: rewire 的语义应该是什么？**

- `pt rewire --replace old_node new_node` — 1:1 替换，所有引用 old 的地方换成 new
- `pt rewire --replace old_node new_node1,new_node2` — 1:N 替换
- `pt rewire --insert new_node --after upstream --before downstream` — 插入
- 还是应该拆成更原子的操作？

**Q2.2: 废弃节点的处理**

被替换的旧节点：
- 直接删除？（丢失历史）
- 标记 status=archived？（保留历史但不参与 CPM）
- 移到单独的 archived 区域？

### Q3: AI Agent 友好的操作接口

Nova（AI助手）是 pt 的主要操作者。当前 Nova 需要写原始 Python 脚本来修改 DAG，这不可靠。

**Q3.1: CLI vs API vs 自然语言**

- CLI 命令（`pt add "节点名" --phase DETAIL --days 5 --depends a,b --before c`）
- Python API（`core.add_node(project, {...})`）
- 自然语言接口（`pt apply "添加LM5060验证节点，5天，接入camrx_sch_base上游"`）

应该优先实现哪层？CLI 和 API 的参数设计有什么差异？

**Q3.2: 批量操作的输入格式**

一次添加一组相关节点（如 CPHY 验证的 5 个节点），输入格式：
- A: YAML 文件（和项目文件同格式的节点片段）
- B: 简化 DSL（每行一个节点，缩进表示依赖）
- C: JSON patch 格式
- D: 交互式向导

考虑到 AI Agent 生成 + 人类审核的工作流，哪种格式最优？

### Q4: 与现有系统的集成

**Q4.1: check_integrity 的角色**

当前 check_integrity 是被动检查（status 时运行）。新增 CRUD 操作后：
- 每次 CRUD 操作后自动运行？（性能影响？）
- 只在写入前运行（作为 gate）？
- 区分 error（阻止写入）和 warning（允许写入但提示）？

**Q4.2: 与 CPM 引擎的交互**

添加/删除节点后，关键路径可能变化。是否需要：
- 操作后自动输出关键路径变化 diff？
- 检测"新增节点是否落在关键路径上"并告警？
- 检测"删除节点是否影响关键路径"并阻止？

**Q4.3: 与 sub（子任务）系统的关系**

当前有两套体系：
- 一等节点（nodes 列表，参与 CPM）
- 子任务（嵌套在父节点下，不参与 CPM）

add_node 添加的是一等节点。是否需要 `pt promote`（子任务提升为一等节点）和 `pt demote`（一等节点降为子任务）？

---

## 约束条件

1. **单文件 YAML** — 不引入数据库，项目数据必须保持单文件自包含
2. **零重依赖** — Python 3.10+ 和 PyYAML，不加新依赖
3. **向后兼容** — 现有项目文件不能 break
4. **代码精简** — 当前 3200 行，新增功能控制在合理范围内
5. **AI Agent 是主要用户** — 接口设计要对程序化调用友好
6. **人类是最终审核者** — 关键操作需要可预览、可回滚

---

## 期望输出

1. 推荐的 API 设计（函数签名 + 行为语义）
2. 每个 Q 的方案选择 + 理由
3. 边界情况处理策略（环检测、ID冲突、跨阶段依赖）
4. 实现优先级排序（哪些先做，哪些可以后做）
5. 如果有我没想到的问题或更好的整体架构，请指出

---

## 回复区域

> 请在下方回复：


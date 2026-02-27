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
q1回复
这是一个非常经典的工程设计问题。在“扁平 DAG + 单文件 YAML + 强完整性约束”的架构下，既要符合人类硬件工程师的直觉（保留方案变更记录、灵活变阵），又要为 AI Agent (Nova) 提供绝对稳定、防呆、可回滚的 API。
整体架构的核心哲学应该是：“将 DAG 的修改视为数据库事务（Transaction），以现有的 check_integrity 作为提交门控（Commit Gate），并提供基于业务意图的高阶拓扑操作，拒绝底层微操。”
针对你的三个痛点，以下是系统性的 API 设计与底层改造方案：
Q1.3: 批量操作的事务性与回滚（解决基建问题）
推荐方案：B（内存沙盒校验）为主，A（本地快照 Undo）为辅。
既然数据全部在一个 YAML 文件里，引入复杂的 Undo Log 或要求用户必须用 Git 都是过度设计。最优雅、最原子的方式是利用 Python 的上下文管理器实现内存级事务。只有建立好这个底座，AI 才可以肆无忌惮地调用增删改 API。
设计实现：
在 tracker/core.py 中引入一个 mutate 上下文管理器：
import copy
from contextlib import contextmanager

class ProjectTracker:
    # ... 
    
    @contextmanager
    def mutate(self):
        """原子化操作 DAG 的上下文管理器"""
        # 1. 内存级深拷贝当前节点状态 (极快，构建沙盒)
        backup_nodes = copy.deepcopy(self.nodes)
        
        try:
            # 2. 将控制权交还给调用方（允许在此期间随意增删改 self.nodes）
            yield self
            
            # 3. 离开上下文时，强制触发引擎现有的 6 类完整性检查！
            self.check_integrity() 
            
        except Exception as e:
            # 4. 任何报错（环路、悬空、孤立终点），瞬间回滚内存，绝不污染 YAML
            self.nodes = backup_nodes
            raise RuntimeError(f"DAG 事务回滚: {str(e)}")
            
        else:
            # 5. 校验通过，写入文件前先备份当前 YAML
            self._snapshot_for_undo()
            # 6. 一次性安全覆写 YAML
            self._save_yaml()

双重保险收益：
 * 对 AI (Nova)：如果 AI 在批量操作中间搞出了环路，事务会自动回滚，并将底层的 IntegrityError 抛给 AI。AI 拿到清晰的报错后可以重新生成修正后的指令，彻底杜绝将损坏的 DAG 写入文件。
 * 对人类工程师：在 _snapshot_for_undo() 中，将当前的 project.yaml 复制到隐藏目录 .pt_history/project_<timestamp>.yaml（保留最近 10 次）。CLI 新增 pt undo 命令，一键用备份覆盖回来，提供终极“后悔药”。
Q1.1: add_node 的接入策略
推荐方案：组合提供 depends (上游) 和 leads_to (下游)，并在引擎内实现“智能断点切入 (Auto-Splice)”。
坚决不推荐方案 D（基于 phase 盲猜），因为黑盒魔法会让 AI 无法预测操作结果，极易出错。提供显式的双向绑定是最稳健的。
API 签名与行为设计：
def add_node(self, node_data: dict, depends: list=None, leads_to: list=None):

 * 基础挂载 (方案 A)：新节点自身的 depends 等于传入的 depends 列表。
 * 下游接管 (方案 B)：遍历 leads_to 指定的下游节点，将新节点的 ID 注入到这些下游的 depends 数组中。
 * 智能切断 (融合方案 C 的 --between 语义)：（最核心的一步） 如果某个下游节点 D 原本直接依赖了某个上游节点 U，现在新节点 X 插入在它们中间（即 X 依赖 U，D 依赖 X），引擎必须自动从 D.depends 中移除 U。
   * 场景再现：原本链路是 [原理图] -> [PCB Layout]。现在要插入 ECN 评审，调用 add_node("ECN", depends=["原理图"], leads_to=["PCB Layout"])。
   * 系统行为：自动切断直连边，变成 [原理图] -> [ECN] -> [PCB Layout]。不需要用户再手动去清理旧依赖，且不会留下并行的冗余短路边（保证关键路径 Slack 计算正确）。
Q1.2: remove_node 的清理策略
推荐方案：业务上主推 D（软删除），技术上实现 B（自动缝合）+ C（防呆拦截）。
硬件工程不同于纯软件，诸如“JW7221 替换为 LM5060”这种方案废弃，是极具价值的避坑经验和文档索引节点，在 DAG 中绝不应该被物理抹除。
策略 1：软删除 / 归档 (Soft Delete) - 默认与推荐
 * API / CLI：pt skip <id> --reason "方案废弃"
 * 机制：完全不修改 DAG 拓扑连线，仅将节点状态置为 skipped 或 cancelled。
 * 引擎改造 (engine.py)：只需改动一两行代码。在 CPM 关键路径正向/反向推导时，如果遇到 status == skipped，将其预估工时 days 强制视为 0。它的 Earliest Finish (EF) 直接等于 Earliest Start (ES)。
 * 优势：完美保留拓扑上下文，对关键路径工时计算零污染，不会触发孤立终点报警。
策略 2：硬删除与智能缝合 (Hard Delete with Stitching)
仅用于处理刚建错的节点（如 AI 幻觉生成的无用节点、拼写错误）。
 * API / CLI：pt rm <id> --stitch
 * 防呆拦截 (方案 C)：如果不带 --stitch 且节点有下游，系统直接拦截报错：“该节点存在下游，强制删除会产生悬空依赖。请使用 --stitch 缝合连线，或使用 pt skip 软删除。”
 * 缝合逻辑 (方案 B)：删除节点 X 时，提取它的所有 Upstreams。遍历所有依赖了 X 的下游节点，从它们的 depends 中删去 X，并把 X 的 Upstreams 补充进去（Set 去重）。这就是“拓扑缝合”，保证 DAG 不断链。
🚀 总结：给 AI Agent 与 CLI 的最终形态
经过上述底层改造，你就可以为 AI 提供一个强大的批量更新 API。AI 只需要按业务逻辑生成字典，无需小心翼翼地处理图论边缘情况：
# 提供给 Nova 的高级工具 API (可直接映射为 CLI 宏命令)
with pt.mutate():
    # 1. 批量添加 CPHY 验证任务群
    pt.add_node({"id": "cphy_board", "days": 5}, depends=["cphy_design"])
    pt.add_node({"id": "cphy_test", "days": 3}, depends=["cphy_board"])
    
    # 2. 将测试任务接入现有主流程（自动切断原来的短路边）
    pt.add_node({"id": "cphy_review"}, depends=["cphy_test"], leads_to=["pcb_release"])
    
    # 3. 依赖重接 (极其简单，在内存事务里改完就行)
    pt.rewire("old_mipi_test", remove_depends=["sensor_ready"])
    
    # 4. 软删除老方案 (0工时透传)
    pt.get_node("old_mipi_test")['status'] = 'skipped'

# 退出 with 块时：
# -> 自动执行 check_integrity()
# -> 成功：拷贝旧 yaml 到 .pt_history，覆写新 yaml
# -> 失败：报错回滚，AI 收到报错后重试

实施路线图建议：
 * 第一步（工时最小）：改造 engine.py 支持对 status: skipped 节点的 0 工时穿透计算。
 * 第二步（核心地基）：在 core.py 实现 mutate 上下文管理器及针对 .pt_history 目录的复制备份机制。
 * 第三步（完善动作）：实现带 leads_to 断点切入逻辑的 add_node 和带 --stitch 缝合逻辑的 remove_node。


q2回复



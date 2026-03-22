# Merge-to-Close 协议

## 目的

本协议用于强制约束 A57 类硬件项目的过程闭环方式，防止 `project-tracker` 中的过程结论先于 `A57-docs` 中的正式结论关闭，导致真相漂移。

## 核心原则

对以下任一类事项，`project-tracker` 中的对应任务节点或其映射的过程事项，不允许仅凭讨论完成而直接 `Closed`：

- 能力成立
- 接口打通
- 验证跑通
- 风险解除
- 设计决策完成
- 范围冻结
- 基线更新

上述事项只有在 `A57-docs` 中完成正式回写后，才算真正闭环。

## 一句话规则

**先回写 `A57-docs`，再关闭 `project-tracker`。**

## 闭环判据

一个过程事项要满足以下全部条件，才允许在 `project-tracker` 中关闭：

1. 已明确正式对象与借用对象边界
2. 已明确本次结论适用范围
3. 已在 `A57-docs` 更新对应正式文档
4. `A57-docs` 中已能找到本次结论对应的版本锚点或证据锚点
5. `project-tracker` 中已留下指向 `A57-docs` 对应文档的链接

## 最小回写要求

根据事项类型，至少应回写到 `A57-docs` 中的一个正式落点：

- 当前有效结论页
- 执行记录页
- 目标设计版本表
- 对象台账
- 需求追溯矩阵
- 专项技术页

若当前没有合适落点，应先在 `A57-docs` 创建正式承载页，再执行关闭。

## 标准流程

1. 在 `project-tracker` 中提出问题、记录过程或收敛结论
2. 判断该事项是否属于“可形成正式项目知识”的事项
3. 若是，则先整理为面向 `A57-docs` 的正式表述
4. 更新 `A57-docs` 正式文档
5. 在 `project-tracker` 中补充链接、对象边界、证据锚点和适用范围
6. 只有完成上述步骤后，才允许 `Closed`

## 特别规则

### 草稿可以留在 `project-tracker`

- 未证实结论
- 讨论中的技术路径
- 待确认问题
- 临时试验记录

这些内容可以保留在 `project-tracker`，但不能冒充正式闭环。

### 正式结论必须进入 `A57-docs`

- 一旦团队口径变成“当前有效结论”
- 一旦该结论会影响需求、设计、验证或发布
- 一旦下游任务需要把它当输入物继续推进

就必须进入 `A57-docs`。

## 反例

以下情况都不允许直接关闭：

- 只在评论里写“已跑通”
- 只有聊天记录，没有对象编号
- 只有口头确认，没有证据路径
- 只更新了 `project-tracker`，没有更新 `A57-docs`
- 借用对象得出的结论，没有写清对正式对象的适用边界

## 合法关闭方式

对来自审核、联调或验证的问题，当前工具层只接受以下 `close_mode`：

- `merged_fix`：对应修复已经进入 `A57-docs` 的正式文档，并完成关联记录
- `merged_waiver`：对应豁免结论已经进入 `A57-docs` 的正式文档，并完成关联记录
- `accepted_risk`：对应风险接受结论已经进入 `A57-docs` 的正式文档，并完成关联记录

报告生成、口头确认、截图、聊天记录、单独修改 `project-tracker` 状态，都不构成合法关闭。

## 推荐关闭模板

在 `project-tracker` 中关闭相关事项前，建议至少补齐以下内容：

- 正式对象：
- 借用对象：
- 本次结论：
- 适用范围：
- 证据锚点：
- `A57-docs` 回写路径：
- 回写提交或版本标识：

对应当前 CLI / YAML 结构，至少应映射为：

- `conclusion`
- `formal_object_id`
- `sample_entity_id`
- `protocol_object_id`
- `borrowed_object_id`
- `borrowed_purpose`
- `scope`
- `firmware_version`
- `fpga_version`
- `docs_anchor`
- `evidence_paths`
- `docs_backwrite_path`
- `close_mode`

## 工具落地点

当前建议通过以下命令形成标准闭环，而不是手改 YAML：

1. `pt close set <task_id> ...` 写入或更新 closure 元数据
2. `pt close show <task_id>` 查看单任务当前正式关闭信息
3. `pt close list [--invalid-only]` 汇总当前项目所有 close gate 任务
4. `pt close check <task_id>` 或 `pt close-check <task_id>` 执行机器校验
5. `pt done <task_id>` 在 close gate 不满足时会自动拒绝关闭

同时，`pt status` 和 `pt map` 会显示当前项目的 Merge-to-Close 风险摘要，避免“任务已 done，但正式闭环未完成”的假进展。

建议把以下字段写入任务节点的 `closure` 元数据：

- `conclusion`
- `formal_object_id`
- `formal_object_class`
- `sample_entity_id`
- `protocol_object_id`
- `protocol_object_class`
- `borrowed_object_id`
- `borrowed_object_class`
- `borrowed_purpose`
- `scope`
- `firmware_version`
- `fpga_version`
- `pcb_version`
- `bom_version`
- `docs_anchor`
- `evidence_paths`
- `docs_backwrite_path`
- `need_human_check_fields`
- `close_mode`

## 推荐命令示例

```bash
pt close set edp_bringup \
  --require \
  --conclusion "eDP 底层已跑通，但正式版本和样机实体仍待补齐" \
  --formal-object-id DCURX_MAIN \
  --scope "DCURX eDP 底层链路" \
  --sample-entity-id NEED_HUMAN_CHECK \
  --protocol-object-id DCURX_TI984_DECODER \
  --firmware-version NEED_HUMAN_CHECK \
  --fpga-version NEED_HUMAN_CHECK \
  --docs-anchor A57.DCURX.EDP_OLDI.EXEC_V1_V2 \
  --docs-backwrite-path "01_需求阶段_Requirements/.../DCURX_V1_V2_执行记录页.md" \
  --close-mode merged_fix \
  --evidence "records/2026-03-22/edp_pass.md" \
  --need-human-check-fields sample_entity_id,firmware_version,fpga_version

pt close check edp_bringup
pt close list --invalid-only
```

## 与多 Repo 协议的关系

本协议是 [`A57_MULTI_REPO_COLLAB_PROTOCOL.md`](./A57_MULTI_REPO_COLLAB_PROTOCOL.md) 的强制执行补充。

若两者出现冲突，以“项目真相必须先回写 `A57-docs`”为最高优先级。

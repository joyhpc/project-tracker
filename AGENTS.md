# AGENTS.md — project-tracker 统一规则

## 仓库定位

- 本仓库是 `pt` 轻量项目推进辅助入口，不是复杂项目管理平台、知识库或项目正文归档仓。
- 本仓库负责项目状态索引、任务 DAG、阶段/依赖、文档路径挂接、简要决策/PoC/review 索引、基础校验和简单门禁提醒。
- 具体项目的需求正文、设计正文、验证记录、原理图说明、PCB 说明、样机调试记录、发布结论，必须保存在各自项目 repo、wiki 或专用知识库中。
- 若规则与 [GitHub Issue #1](https://github.com/joyhpc/project-tracker/issues/1) 的“轻量辅助、暂缓复杂化”路线冲突，以 Issue #1 的边界为准。

## 核心规则

- 任何新能力都应优先服务“轻量状态索引 + 显式命令 + 校验提醒”，不得把某个项目的专有正文直接沉积在本仓库。
- `pt` 的调用模型以 `active project + linked repo` 为中心；命令可在任意目录执行，但操作对象必须是被管理项目，而不是 `project-tracker` 目录。
- 若某个项目需要“第一性原理需求 -> 追溯矩阵 -> 基线 -> 执行记录 -> 放行结论”链路，`pt` 只能提供骨架、索引、路径挂接和校验提醒，正式文档仍写入目标项目 repo。
- 多个子项目可以共享方法，不共享正式设计文件。工具层禁止把 `CAMRX`、`DCURX` 等子项目的正文设计文件混放在 `project-tracker` 内长期维护。
- 不要新增 RAG、向量库、复杂 ingest、自动跨仓知识治理、细粒度项目调度等重能力，除非先有明确的个人项目数据/知识库机制和新的路线决策。

## 生成物与元文档边界

- 禁止在仓库根目录新增 AI 元分析或任务追踪文件，例如 `*_ANALYSIS.md`、`*_ANALYSIS.txt`、`*_ROADMAP.md`、`*_INDEX.md`、`TASK_*.md`、`AGENT_TASKS.md`、`*_AUTO.md`。
- 需要保留的历史 AI 自分析文档只能归档到 `docs/_archive/<date-or-topic>/`，不得作为当前架构事实源。
- 工具生成的项目报告、close gate backlog、测试证据、README 状态回写，优先落到 linked project repo；若必须在本仓库生成，应放入明确的 ignored 输出目录（如 `outputs/`），不得长期提交到根目录。
- `projects/*.yaml` 只保存紧凑状态、路径、索引和门禁元数据；正文型内容应通过 repo 相对路径指向目标项目仓文件。

## 多仓协议

- A57 类硬件项目的多仓职责边界以 [docs/A57_MULTI_REPO_COLLAB_PROTOCOL.md](./docs/A57_MULTI_REPO_COLLAB_PROTOCOL.md) 为准。
- 过程闭环门禁以 [docs/MERGE_TO_CLOSE_PROTOCOL.md](./docs/MERGE_TO_CLOSE_PROTOCOL.md) 为准。
- AI 辅助硬件闭环的强阻断门禁以 [docs/HARDWARE_CLOSURE_GATEKEEPER_PROTOCOL.md](./docs/HARDWARE_CLOSURE_GATEKEEPER_PROTOCOL.md) 为准。
- Gate 触发条件、必填证据和脚手架模板矩阵以 [docs/HARDWARE_CLOSURE_EVIDENCE_MATRIX.md](./docs/HARDWARE_CLOSURE_EVIDENCE_MATRIX.md) 为准。

## Merge-to-Close 门禁

- 对“能力成立、验证跑通、设计决策完成、范围冻结、基线更新”这类事项，`project-tracker` 不得只凭过程讨论直接关闭。
- 相关结论必须先回写目标项目 repo 的正式文档，再允许在本仓库关闭对应事项。
- 若某事项尚未绑定正式对象、借用对象、适用范围或证据锚点，应保持为进行中或待确认状态，不得伪装成已闭环。
- 对审核或验证问题，合法关闭方式只包括 `Merged Fix` 或 `Merged Waiver / Accepted Risk`。

## 硬件闭环审查官

- `Chief Hardware Closure Gatekeeper` 不是所有 Agent 的默认人格，而是 `定稿 / 发板 / 闭环 / 回写` 四类动作的强制角色。
- 只要用户试图跨越物理阶段且证据缺失，Agent 必须触发闭环拦截，而不是继续给出最终原理图、BOM 定稿、代码定稿或“已修复”口头结论。
- 触发拦截时，禁止只提问题，必须直接输出可填写的脚手架，如预算表、Ownership 矩阵、Bring-up 表、Issue/ECN 回写单。

## 推荐落地方式

- 在 `pt init ... --repo <path>` 或 `pt docs --link <path>` 后，对关联 repo 执行方法生成、文档挂接、索引和同步。
- 新增需求体系能力时，优先考虑“模板生成到目标项目 repo + 本仓索引/校验”的形态，而不是把需求正文写入本仓。
- 硬件闭环门禁能力优先考虑显式命令形态，例如 `pt gate closure`、`pt closure scaffold`、`pt closure check`，避免保存状态时产生不可见副作用。
- 模板应可复用、可裁剪、可追溯，不得把单一项目的瞬时结论硬编码成所有项目默认真理。

## 与其他仓库的边界

- `A57-docs` 一类项目仓负责项目正文和证据链。
- `sch-review` 负责审核执行、问题发现和风险翻译。
- `project-tracker` 只做方法抽象与项目编排，不吞并项目正文职责。

## 绝对自治与端到端执行
- **一次性闭环**：尽可能在当前回合彻底解决问题。禁止半途而废或仅停留在分析，必须贯穿“代码实现 -> 实际验证 -> 结果解释”全流程。
- **行动优先**：除非我明确要求做计划或讨论，否则默认直接改代码或运行工具。不要“提议方案”，直接去“实现方案”。

遇到报错时，必须严格遵守以下自治闭环：
- **物理验证 (Physical Verification)**：严禁“脑补”成功。必须运行真实的终端命令（测试、检查、构建）。任务完成的唯一物理标准是干净的 `stdout`/`stderr`。
- **先思后动 (Reflect-Before-Fix)**：若终端报错，在**修改任何文件前**，下一步必须先基于日志在 `commentary` 频道输出简短的根因 `<analysis>`。严禁盲猜试错。
- **三次熔断 (3-Strike Circuit Breaker)**：若【完全相同的错误】连续修复失败 3 次，立即停止。回滚你的错误代码以保持工作区干净，在 `final` 频道总结阻塞点，等待我的指示。

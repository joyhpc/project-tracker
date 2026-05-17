# Project Tracker 文档入口

本文是 `docs/` 的可信阅读入口。读项目架构、边界和重要规则时，以这里列出的“当前事实源”为准；未列入当前事实源的历史方案、一次性报告、项目专属样例和旧路线图，不应当用来判断当前实现。

## 当前事实源

| 文档 | 可信范围 |
|---|---|
| [`../README.md`](../README.md) | 仓库定位、快速开始、目录边界、常用命令 |
| [`../AGENTS.md`](../AGENTS.md) | Agent 工作规则、仓库边界、硬件闭环拦截规则 |
| [`architecture.md`](./architecture.md) | 当前整体架构、数据流、模块分层、读写边界 |
| [`core-architecture.md`](./core-architecture.md) | `core.py` façade、`project_*` 模块、存储与调用链 |
| [`PROJECT_DATA_LAYOUT.md`](./PROJECT_DATA_LAYOUT.md) | 项目 YAML、示例、模板、linked repo 的存放边界 |
| [`DEPENDENCY_RULES.md`](./DEPENDENCY_RULES.md) | DAG 依赖定义规则 |
| [`PROJECT_MAP_METHOD.md`](./PROJECT_MAP_METHOD.md) | 项目地图方法论；其中“未来视图/契约”属于目标，不代表已实现 |
| [`MERGE_TO_CLOSE_PROTOCOL.md`](./MERGE_TO_CLOSE_PROTOCOL.md) | Merge-to-Close 正式关闭规则 |
| [`HARDWARE_CLOSURE_GATEKEEPER_PROTOCOL.md`](./HARDWARE_CLOSURE_GATEKEEPER_PROTOCOL.md) | 定稿、发板、闭环、回写类动作的硬件证据拦截规则 |
| [`HARDWARE_CLOSURE_EVIDENCE_MATRIX.md`](./HARDWARE_CLOSURE_EVIDENCE_MATRIX.md) | 硬件闭环 Gate 触发条件与必填证据 |
| [`A57_MULTI_REPO_COLLAB_PROTOCOL.md`](./A57_MULTI_REPO_COLLAB_PROTOCOL.md) | A57 类多仓职责边界 |
| [`req-architecture.md`](./req-architecture.md) | `pt req` 的目标、边界与 linked repo 生成规则 |
| [`KNOWLEDGE_ROUTING.md`](./KNOWLEDGE_ROUTING.md) | 项目经验进入 `pt`、升级到 `sch-review` 的判定规则 |

## 辅助方法文档

| 文档 | 可信范围 |
|---|---|
| [`DECISION_FRAMEWORK.md`](./DECISION_FRAMEWORK.md) | 工程决策思维框架，不是实现事实源 |

## 非事实源

以下目录或文件只保留历史背景，不作为当前架构事实源：

- [`_archive/`](./_archive/)：过期 AI 分析、旧路线图、历史设计草案。
- [`issues/`](./issues/)：人类协作议题、历史同步材料或 generated backlog，不是架构文档。
- 单项目样例、带具体项目名的地图/问题文档：只能作为历史案例，不能推断通用架构。

## 维护规则

1. 修改架构文档前，先从代码确认事实：`tracker/cli.py`、`tracker/core.py`、`tracker/project_*.py`、`tracker/engine.py`、`tracker/requirements.py`、`tracker/close_gate.py`。
2. 文档只描述 `project-tracker` 的工具事实、方法边界和索引规则；项目正文、证据、设计结论必须留在 linked project repo。
3. 如果某能力只是目标、草案或实验能力，必须明确标注，不能写成当前事实。
4. 旧方案、一次性分析和不再可靠的路线图归档到 `_archive/`，不要继续放在当前文档入口旁边。
5. 更新文档后至少运行：

```powershell
python tools/check_repo_boundary.py
python -m tracker doctor
python -m tracker validate --all
pytest -q
```

# Project Tracker Anchors

这份文档给新 agent / 新同事一个稳定落脚点。进入仓库后，优先按这里建立心智模型，再去读具体代码。

## 阅读顺序

1. [`README.md`](../README.md)：仓库定位、快速开始、目录边界。
2. [`docs/README.md`](./README.md)：哪些文档是当前事实源，哪些只是历史背景。
3. [`docs/architecture.md`](./architecture.md)：整体架构、数据流、读写边界。
4. [`docs/core-architecture.md`](./core-architecture.md)：`core.py` façade 与 `project_*` 模块边界。
5. [`tracker/cli.py`](../tracker/cli.py)：所有 CLI 命令的总路由。
6. [`tracker/core.py`](../tracker/core.py)：兼容入口、active project、YAML 读写、快照、迁移。
7. [`tracker/project_storage.py`](../tracker/project_storage.py)、[`tracker/project_model.py`](../tracker/project_model.py)、[`tracker/project_validation.py`](../tracker/project_validation.py)、[`tracker/project_query.py`](../tracker/project_query.py)、[`tracker/project_mutation.py`](../tracker/project_mutation.py)、[`tracker/subtask_templates.py`](../tracker/subtask_templates.py)、[`tracker/project_map.py`](../tracker/project_map.py)：已拆出的存储、模型、校验、查询、状态机、模板和地图层。
8. [`tracker/engine.py`](../tracker/engine.py)：DAG、拓扑排序、关键路径、Slack、ready/waiting/blocked 分类。
9. [`tests/`](../tests/)：当前行为合同和回归保护。

## 架构锚点

### CLI 层

- 入口：`pt`、`pt.sh`、`python -m tracker`、`tracker/cli.py`
- 责任：参数解析、子命令注册、路由到 `tracker/commands/*.py`
- 不应承接：项目读写规则、依赖计算、状态机细节、文档生成逻辑

### 状态与持久化层

- 兼容入口：`tracker/core.py`
- 存储原语：`tracker/project_storage.py`
- 迁移归一化：`tracker/project_migration.py`
- 运行时数据：`projects/<PROJECT_ID>.yaml`
- 当前项目：`projects/.active`
- 本地快照：`projects/.pt_history/`

`core.py` 现在是 façade，不是所有逻辑的家。新逻辑优先拆到更具体模块，再由 `core.py` 暴露稳定 API。

### 项目逻辑层

- `project_model.py`：把项目 YAML 转成引擎和展示可消费的结构。
- `project_validation.py`：schema、DAG、悬空依赖、反向跨阶段依赖、粗粒度节点等校验。
- `project_query.py`：聚合 `status` 所需的 ready/waiting/blocked/done、CPM、fallback。
- `project_mutation.py`：任务状态机、子任务状态、文档挂接等项目内变更规则。
- `subtask_templates.py`：子任务模板发现、匹配、应用和 DAG rewire。
- `project_map.py`：单项目/全局项目地图快照、文本输出、HTML 渲染。

### 图引擎层

- 核心文件：`tracker/engine.py`
- 责任：构建 DAG、拓扑排序、CPM、slack、ready/waiting/blocked 分类、下游影响。
- 约束：不关心 YAML 如何保存，只消费 flow-like 结构和任务状态映射。

### Linked Repo 能力

- `requirements.py`：把需求骨架、索引和追溯矩阵生成到 linked project repo。
- `close_gate.py`：校验 closure 元数据是否足以关闭事项。
- `docs_cmd.py` / `core.attach_doc()`：只在项目 YAML 中保存正式文档路径。

正式项目正文和证据不属于 `project-tracker`。

### 辅助能力

- `knowledge.py` / `prompt.py`：给 `pt prompt` 的本地检索和 prompt 组装，辅助判断，不是正式事实源。
- `datax/`：CSV、Gantt、Mermaid、burndown、stats 导出。
- `web/`：只读 Web 看板。
- `notify/` 与 `post_save.py`：best-effort 钩子和通知，不应改变主流程成败。
- `repo_boundary.py`：根目录边界检查，必须保持纯函数形态。

## 常见修改入口

| 目标 | 优先看 |
|---|---|
| 改 CLI 参数或命令入口 | `tracker/cli.py` + 对应 `tracker/commands/*.py` |
| 改任务状态机 | `tracker/project_mutation.py`，再检查 `core.py` 包装 |
| 改 YAML schema 或校验 | `tracker/project_migration.py`、`tracker/project_validation.py` |
| 改依赖/关键路径/ready 判断 | `tracker/engine.py` |
| 改项目地图 | `tracker/project_map.py`、`tracker/commands/visual_cmd.py` |
| 改需求骨架/trace/check | `tracker/requirements.py`、`tracker/commands/req_cmd.py` |
| 改 close gate | `tracker/close_gate.py`、`tracker/commands/close_cmd.py` |
| 改 prompt 辅助能力 | `tracker/knowledge.py`、`tracker/prompt.py`、`tracker/commands/prompt_cmd.py` |

## 验证命令

```powershell
python tools/check_repo_boundary.py
python -m tracker doctor
python -m tracker validate --all
pytest -q
```

如果只需要快速语法检查：

```powershell
python -m py_compile tracker/*.py tracker/commands/*.py tests/*.py
```


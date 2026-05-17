# Project Tracker Core Architecture

本文描述 `project-tracker` 当前核心代码边界，重点回答：

1. 项目状态存在哪里。
2. `core.py` 为什么还存在。
3. DAG / 校验 / 状态查询 / 状态变更 / linked repo 能力分别由谁负责。

## 设计原则

1. **CLI-first**：主操作从 `pt` 命令闭环。
2. **YAML-first**：单项目单 YAML 是运行时状态事实源。
3. **Git-friendly**：状态文件可 diff、可审查、可回滚、可同步。
4. **Deterministic**：依赖分类、关键路径、校验结果尽量确定性输出。
5. **Boundary-first**：项目正文和证据留在 linked project repo，`project-tracker` 只保留索引和门禁元数据。

## 分层总览

```text
tracker/cli.py
        │
        ▼
tracker/commands/*.py
        │
        ▼
tracker/core.py                        兼容 façade / 持久化入口
        │
        ├─ project_storage.py          YAML load/save、active project、snapshot、restore
        ├─ project_migration.py        schema 迁移、保存前归一化
        ├─ project_constants.py        schema 版本和枚举常量
        ├─ project_model.py            纯项目模型辅助函数
        ├─ project_validation.py       schema + DAG 完整性校验
        ├─ project_query.py            状态聚合 / fallback 查询
        ├─ project_mutation.py         状态机 / 任务变更规则
        ├─ subtask_templates.py        子任务模板发现 / 匹配 / DAG rewire
        ├─ project_map.py              项目地图快照 / 文本与 HTML 渲染
        ├─ requirements.py             linked repo 需求骨架、索引、检查、追溯
        └─ close_gate.py               Merge-to-Close 元数据校验和报告
        │
        ├─ engine.py                   DAG 分类 / CPM / 关键路径
        ├─ flow.py                     流程模板加载
        ├─ datax/*                     导出与统计
        ├─ web/*                       只读 Web 看板
        ├─ knowledge.py                BM25 检索，辅助 prompt
        └─ prompt.py                   Prompt 组装，辅助能力
        │
        ▼
projects/*.yaml                        项目运行时状态事实源
linked project repo                     正式项目正文和证据事实源
```

## `core.py` 的当前职责

`core.py` 是对外稳定入口，不是所有实现细节的归宿。

仍适合保留在 `core.py` 的职责：

- active project 选择和加载入口。
- 对 `project_storage.py` 的统一包装。
- 历史快照和 `undo`。
- 兼容旧命令层与旧测试依赖的公共 API。
- 把 `requirements.py`、`close_gate.py` 等能力接到统一项目模型上。
- 在保存项目后触发 best-effort post-save hooks。

不应继续塞进 `core.py` 的职责：

- 纯状态机规则。
- DAG 校验规则。
- 展示和地图渲染。
- 需求模板细节。
- close gate 字段规则。
- 新的导出格式。

新增能力的默认落点应该先是具体模块，再由 `core.py` 暴露薄包装。

## 模块职责

### `project_storage.py`

只处理存储原语：

- `project_file()`
- `load_project()`
- `save_project()`
- `get_active()` / `set_active()`
- `list_project_files()`
- `snapshot()` / `restore_latest_snapshot()`

它不理解 DAG、任务状态、需求或 close gate。

### `project_migration.py`

负责把旧项目数据迁移到当前 schema，并在保存前清理内部字段。

关键函数：

- `migrate_project_data()`
- `prepare_for_save()`
- `normalize_verdicts()`

### `project_constants.py`

集中维护共享常量：

- `PROJECT_SCHEMA_VERSION`
- `VALID_NODE_STATUSES`
- `VALID_DECISION_STATUSES`
- `VALID_POC_STATUSES`
- `VALID_REVIEW_VERDICTS`

### `project_model.py`

纯函数层，不碰文件系统，不依赖 CLI：

- `_get_task_status()`
- `_project_as_flow()`
- `_effective_nodes()`
- `_progress_counts()`
- `_undone_dependencies()`

它把项目 YAML 转成 `engine.py` 和展示层可消费的结构。

### `project_validation.py`

负责两层校验：

- schema 校验：顶层字段、列表结构、枚举字段、必需字段。
- 完整性校验：DAG 环、悬空依赖、重复 ID、反向跨阶段依赖、粗粒度节点提示等。

输出统一 issue 列表，供 CLI、doctor、测试和后续集成使用。

### `project_query.py`

负责状态快照：

- 调 `engine.classify_tasks()` 计算 ready / waiting / blocked / done。
- 调 `engine.compute_cpm()` 计算关键路径和 slack。
- 在项目结构有问题时生成保守 fallback。
- 输出 `core.get_status()` 的统一返回结构。

### `project_mutation.py`

负责项目对象内的变更规则，不负责文件读写：

- `start_task_in_project()`
- `done_task_in_project()`
- `block_task_in_project()` / `unblock_task_in_project()`
- `add_subtask_to_project()` / `done_subtask_in_project()`
- `attach_doc_to_task()`

依赖未完成、close gate 未通过、状态非法等规则应优先在这里或 close gate 模块表达。

### `subtask_templates.py`

负责子任务模板：

- 候选模板目录发现。
- 模板元数据列表。
- `attach_to` 匹配。
- 模板应用后的子图插入、外部依赖提示和 DAG rewire。

### `project_map.py`

负责把状态快照整理成“人读得懂”的地图：

- 单项目地图。
- 全局项目地图。
- stale/sync 风险摘要。
- 当前焦点选择。
- 阶段泳道、阻塞、关键路径、close gate 摘要。
- 文本和 HTML 渲染。

`plan`、`map`、`visual` 应共享这里的语义，避免各自拼一套。

### `requirements.py`

负责 `pt req` 的 linked repo 能力：

- 生成需求骨架到目标 repo。
- 维护 `.pt/requirements_manifest.yaml`。
- 重建索引页。
- 检查 frontmatter、绑定、断链和必需列。
- 刷新需求追溯矩阵。

运行时项目 YAML 只保存 profile、root、manifest、subprojects、last_check、last_trace 等轻量状态。

### `close_gate.py`

负责 Merge-to-Close：

- 判断任务是否需要 close gate。
- 归一化 closure 视图。
- 校验正式对象、借用对象、适用范围、版本、证据和回写路径。
- 生成单任务人工补齐模板。
- 汇总项目级 close gate 状态。
- 渲染 Markdown backlog/report。

它不负责保存正式结论正文；正式结论仍应在 linked repo。

### `engine.py`

图引擎内核：

- `build_graph()`
- `topo_sort()` / `stable_node_order()`
- `compute_cpm()`
- `classify_tasks()`
- `analyze_blockers()`
- `find_alternatives()`

它不关心项目 YAML 如何保存，也不关心 CLI 输出格式。

## 关键调用链

### `pt validate --all`

```text
commands/project.py
  → core.validate_all_projects()
  → core.validate_project_file()
  → project_storage.load_project()
  → project_migration.migrate_project_data()
  → project_validation.validate_project()
```

### `pt doctor`

```text
commands/doctor_cmd.py
  → repo_boundary.find_root_boundary_violations()
  → core.validate_all_projects()
  → core._get_active() / core._load()
```

`doctor` 必须只读。

### `pt status`

```text
commands/project.py
  → core.require_active()
  → core.get_status(project)
  → project_query.get_status(project)
  → project_validation.check_integrity(project)
  → engine.classify_tasks()
  → engine.compute_cpm()
```

### `pt done <task>`

```text
commands/tasks.py
  → core.done_task() / core.quick_done()
  → core.task_completion_issues()
  → close_gate.check_close_gate()
  → project_mutation.done_task_in_project()
  → project_storage.save_project()
  → post_save.run_post_save_hooks()
```

### `pt req trace`

```text
commands/req_cmd.py
  → core.trace_requirements()
  → requirements.trace_requirements()
  → linked repo trace matrix
  → project YAML lightweight last_trace state
```

### `pt close report --save docs/issues/CLOSE_GATE_BACKLOG.md`

```text
commands/close_cmd.py
  → core.list_close_gates()
  → close_gate.summarize_close_gates()
  → close_gate.render_close_report_markdown()
  → linked repo relative path when project.repo exists
```

## 当前边界判断

适合继续做的改进：

- 继续把纯持久化包装从 `core.py` 薄化到 `project_storage.py`。
- 为项目 YAML 补 machine-readable schema 或 schema 文档。
- 为命令层补更细粒度测试。
- 给 `project_query.py` / `project_map.py` 增加 explain/debug 输出。

不适合在当前路线中扩张的方向：

- 把项目正文搬进 `project-tracker`。
- 引入数据库替代 YAML 状态源。
- 做自动全仓 ingest、向量库或复杂知识治理。
- 让 `doctor`、check 类命令写回或修复文件。


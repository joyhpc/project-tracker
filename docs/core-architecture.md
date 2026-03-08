# Project Tracker Core Architecture

这份文档描述 `project-tracker` 当前的核心架构边界，重点回答三个问题：

1. 项目状态存在哪里
2. DAG / 校验 / 状态查询分别由谁负责
3. 为什么 `tracker/core.py` 仍然存在，但不再承担所有实现细节

## 设计目标

系统仍然坚持这 4 个基本原则：

1. **CLI-first**：所有主操作都能从 `pt` 命令闭环完成
2. **YAML-first**：项目状态以单项目单 YAML 为事实源
3. **Git-friendly**：状态文件可 diff、可审查、可回滚、可同步
4. **Deterministic**：依赖分类、关键路径、校验结果尽量确定性输出

## 分层总览

```text
pt / tracker/commands/*.py
        │
        ▼
tracker/core.py                 ← 兼容 façade / 持久化入口
        │
        ├─ tracker/project_constants.py   ← schema 版本与枚举常量
        ├─ tracker/project_model.py       ← 纯项目模型辅助函数
        ├─ tracker/project_validation.py  ← schema + DAG 完整性校验
        ├─ tracker/project_query.py       ← 状态聚合 / fallback 查询
        ├─ tracker/project_mutation.py    ← 状态机 / 任务变更规则
        └─ tracker/subtask_templates.py   ← 子任务模板发现 / 匹配 / DAG rewire
        │
        ├─ tracker/engine.py              ← DAG 分类 / CPM / 关键路径
        ├─ tracker/flow.py                ← 流程模板加载
        ├─ tracker/knowledge.py           ← Markdown AST + BM25 检索
        └─ tracker/prompt.py              ← Prompt 组装
        │
        ▼
projects/*.yaml                 ← 项目事实源
projects/.pt_history/           ← 历史快照
```

## 模块职责

### `tracker/core.py`

`core.py` 现在承担两类职责：

1. **必须保留在这里的状态相关能力**
   - 项目文件路径与激活项目路径
   - YAML 读写
   - schema 迁移
   - 乐观锁
   - 历史快照
   - 兼容旧命令层和旧测试的公共 API

2. **对外兼容 façade**
   - 命令层继续 `import core`
   - 但底层纯逻辑已经拆到 `project_*` 模块
   - 这样先降低复杂度，再逐步继续重构命令层

这是一个刻意的过渡架构：**先拆实现，再保持接口稳定**。

### `tracker/project_constants.py`

集中维护共享常量：

- `PROJECT_SCHEMA_VERSION`
- `VALID_NODE_STATUSES`
- `VALID_DECISION_STATUSES`
- `VALID_POC_STATUSES`
- `VALID_REVIEW_VERDICTS`

价值：

- 避免多个模块各自维护枚举
- 后续加 schema 文档或 JSON Schema 时更容易复用

### `tracker/project_model.py`

这里放**纯函数**，不碰文件系统，不依赖 CLI：

- `_get_task_status()`
- `_project_as_flow()`
- `_effective_nodes()`
- `_progress_counts()`
- `_undone_dependencies()`

这些函数本质是在做“项目 YAML → 引擎可消费结构 / 展示统计”的转换。

### `tracker/project_validation.py`

负责两层校验：

1. **Schema 校验**
   - 顶层字段是否存在
   - `nodes/phases/reviews/decisions/pocs` 结构是否合法
   - 枚举字段是否合法

2. **完整性校验**
   - DAG 是否有环
   - 是否有悬空依赖
   - 是否有重复 ID
   - 是否存在反向跨阶段依赖
   - 是否存在粗粒度 bringup 节点等提示

输出统一为 issue 列表，便于：

- CLI 打印
- JSON 输出
- 后续接 GitHub Actions / pre-commit / external integrations

### `tracker/project_query.py`

负责把多个子能力拼成“状态快照”：

- 调引擎计算 ready / waiting / blocked / done
- 调 CPM 算关键路径
- 结合校验结果生成保守 fallback
- 产出 `get_status()` 的统一返回结构

这个模块的核心价值是：

- 把“读取状态”和“修改状态”拆开
- 避免 `core.py` 同时承担查询、写入、校验、展示拼装

### `tracker/project_mutation.py`

负责项目内的状态变更规则：

- `start_task_in_project()`
- `done_task_in_project()`
- `block_task_in_project()` / `unblock_task_in_project()`
- `add_subtask_to_project()` / `done_subtask_in_project()`
- `attach_doc_to_task()`

这个模块只处理**已加载项目对象上的状态机逻辑**，不负责文件读写。

价值是：

- 把“怎么改状态”从 `core.py` 文件系统层里拆出来
- 让任务状态机更容易单测
- 为后续继续细分子任务编排逻辑铺路

### `tracker/subtask_templates.py`

负责子任务模板相关的 3 类能力：

- 模板目录发现与模板元数据列举
- `attach_to` 匹配
- 模板应用到项目后的子图插入、外部依赖提示处理、DAG rewire

这让 `core.py` 不再自己承担模板发现 + YAML 解析 + 子图重连的混合职责。

### `tracker/engine.py`

`engine.py` 仍然是图引擎内核：

- 任务分类
- 拓扑顺序
- CPM 关键路径
- Slack / 工期推导

它不关心 YAML 如何保存，只关心输入是否是合法 flow + status 映射。

## 关键调用链

### 1. `pt validate --all`

```text
tracker/commands/project.py
    → core.validate_all_projects()
    → core.validate_project_file()
    → core.validate_project()
    → project_validation.validate_project()
    → project_validation.check_integrity()
```

### 2. `pt status`

```text
tracker/commands/project.py
    → core.get_status(project)
    → project_query.get_status(project)
    → project_validation.check_integrity(project)
    → engine.classify_tasks(...)
    → engine.compute_cpm(...)
```

### 3. `pt done <task>`

```text
tracker/commands/node_cmd.py
    → core.done(...)
    → project_mutation.done_task_in_project(...)
    → core._save(project)
    → core.check_integrity(project)
```

注意这里 `done()` 仍然走 `core.py`，但 `_undone_dependencies()` / `check_integrity()` 的实现已经来自拆分模块。

## 为什么保留 `core.py` façade

如果直接让所有命令层改成分别 import 新模块，会带来三个风险：

1. 命令层改动面太大，回归成本高
2. 旧测试和 monkeypatch 依赖 `core.PROJECTS_DIR` / `core.CONFIG_FILE` / `core.HISTORY_DIR`
3. 持久化逻辑和纯逻辑会在一次改动里同时变化，难以定位回归

所以当前策略是：

- **先抽纯逻辑**
- **再保留 `core` 作为稳定入口**
- **最后视需要继续把命令层直接改到更细粒度模块**

这是更适合现有仓库节奏的低风险重构路径。

## 当前边界判断

### 适合继续留在 `core.py` 的内容

- 文件系统路径
- active project 选择
- YAML 读写 / 迁移
- 历史快照
- repo sync / README 状态写回
- 对外兼容 API

### 适合继续拆出去的内容

- 纯展示格式化
- 更细粒度的 project repository 抽象
- project repository / persistence 抽象继续拆分
- JSON Schema 导出 / schema 文档生成

## 当前闭环状态

完成这轮重构后，系统具备如下闭环：

- 新模块已承接 `core` 内部的纯逻辑与校验逻辑
- 命令层无需修改即可继续使用
- `pytest -q` 可回归验证
- `./pt validate --all` 可显式校验项目数据
- 文档与 handoff 已同步说明新的模块边界

## 下一轮最值得做的优化

1. 把 project repository / persistence 抽象从 `core.py` 继续拆出去
2. 给 `project_validation.py` 补 JSON Schema 导出或 machine-readable schema
3. 给 `project_query.py` 增加 explain/debug 输出，解释 ready / blocked / CPM 来源
4. 给命令层补更细粒度单测，而不只依赖回归测试


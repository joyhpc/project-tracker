# Project Tracker 当前架构

本文是 `project-tracker` 的整体架构事实源。它描述当前代码实际采用的模块边界、数据流和读写规则；旧路线图、Prompt 方案草稿和项目专属样例不再作为架构依据。

## 定位

`project-tracker` 是 `pt` 轻量项目推进辅助入口，不是项目正文仓、复杂项目管理平台或知识库系统。

当前边界与 [GitHub Issue #1](https://github.com/joyhpc/project-tracker/issues/1) 一致：

- `pt` 只保存项目状态索引、DAG、路径挂接、简要决策/PoC/review 索引和门禁元数据。
- 正式需求、设计、验证、样品、BOM、发布结论和长期知识必须保存在 linked project repo、wiki 或专用知识库。
- 暂不扩张为全量 ingest、复杂调度、自动跨仓知识治理或替代人工判断的重型系统。

## 数据事实源

```text
project-tracker/
  projects/<PROJECT_ID>.yaml       运行时状态事实源：节点、阶段、依赖、状态、门禁元数据
  projects/.active                 当前活跃项目 ID
  projects/.pt_history/            本地安全快照，默认不提交
  flows/                           repo 根目录流程模板
  tracker/flows/                   package 内流程模板，加载优先级更高
  tracker/templates/               可生成到 linked repo 的文档骨架
  docs/                            工具协议、架构边界、方法说明

linked-project-repo/
  .pt/<PROJECT_ID>.yaml            可选同步快照
  .pt/requirements_manifest.yaml   `pt req` 绑定 manifest
  docs/ / evidence/ / reviews/     正式项目正文和证据
```

项目 YAML 回答“现在做到哪、依赖谁、卡在哪里、证据路径是什么”。linked repo 回答“正式事实是什么、版本锚点是什么、证据原文在哪里”。

## 运行时分层

```text
pt / python -m tracker
        │
        ▼
tracker/cli.py
        │  参数解析和命令路由
        ▼
tracker/commands/*.py
        │  CLI 适配、输出格式、参数到核心 API 的转换
        ▼
tracker/core.py
        │  兼容 façade：active project、YAML 读写、快照、迁移、公共 API
        ├─ tracker/project_storage.py      存储原语：load/save/active/snapshot/restore
        ├─ tracker/project_migration.py    schema 迁移和保存前归一化
        ├─ tracker/project_model.py        纯项目模型转换
        ├─ tracker/project_validation.py   schema + DAG 完整性校验
        ├─ tracker/project_query.py        状态聚合与 fallback
        ├─ tracker/project_mutation.py     任务状态机和项目内变更规则
        ├─ tracker/subtask_templates.py    子任务模板发现、应用、DAG rewire
        ├─ tracker/project_map.py          项目地图快照与文本/HTML 渲染
        ├─ tracker/requirements.py         linked repo 需求骨架、索引、检查、追溯
        └─ tracker/close_gate.py           Merge-to-Close 元数据校验与报告渲染
        │
        ├─ tracker/engine.py               DAG、拓扑排序、CPM、ready/waiting/blocked 分类
        ├─ tracker/flow.py                 流程模板加载
        ├─ tracker/datax/*                 CSV、Gantt、deps、burndown、stats 导出
        ├─ tracker/web/*                   只读 Web 看板
        ├─ tracker/knowledge.py            Markdown 切块 + BM25 检索，辅助 `pt prompt`
        ├─ tracker/prompt.py               Prompt 组装，辅助能力，不是项目事实源
        └─ tracker/repo_boundary.py        纯函数根目录边界检查
```

`core.py` 仍是主入口，但不应继续吸收所有业务逻辑。新的纯逻辑优先放进对应 `project_*`、`requirements`、`close_gate` 或 `project_map` 模块，再由 `core.py` 暴露兼容 API。

## 命令族

| 命令族 | 代表命令 | 主要写入位置 | 说明 |
|---|---|---|---|
| 项目管理 | `init`, `list`, `switch`, `status`, `phases`, `log`, `validate`, `doctor` | `projects/*.yaml` 或只读 | `doctor` 必须只读 |
| 任务推进 | `tasks`, `next`, `start`, `done`, `block`, `unblock`, `update`, `find` | `projects/*.yaml` | `update --dry-run` 和 `update --json` 不写入 |
| DAG 编辑 | `add`, `rm`, `skip`, `rewire`, `replace`, `promote`, `undo` | `projects/*.yaml` / `.pt_history` | 通过 `core.mutate()` 做完整性检查和快照 |
| 子任务模板 | `sub`, `sub-done`, `sub-block`, `sub-list`, `sub-load` | `projects/*.yaml` | 子任务可作为一等节点接入 DAG |
| 分析导出 | `plan`, `map`, `digest`, `timeline`, `estimate`, `gantt`, `stats`, `deps`, `burndown`, `export`, `risk`, `who` | 终端/输出目录 | `map --html` 和 `visual` 可生成 HTML/PNG |
| 文档挂接 | `docs --link`, `docs --attach`, `docs --sync`, `docs --load` | `projects/*.yaml`、linked repo `.pt/` | 正式文档仍在 linked repo |
| 需求体系 | `req init`, `req index`, `req check`, `req trace` | linked repo；可回写轻量状态 | `--dry-run` 不写文件，`--no-save` 不回写项目状态 |
| 决策/PoC/review | `decision`, `poc`, `review`, `review-sync`, `scan`, `propose` | `projects/*.yaml` | 只存索引、摘要、路径和 verdict |
| 闭环门禁 | `close`, `closure`, `close-check`, `gate closure` | `projects/*.yaml`；报告可写 linked repo | 关闭结论必须绑定正式对象、范围、证据和回写路径 |
| 辅助能力 | `prompt`, `web`, `notify`, `hooks`, `domain-sync` | 视命令而定 | 这些不是项目正式事实源 |

## 关键数据流

### 状态查询

```text
CLI → core.require_active()
    → core.get_status(project)
    → project_query.get_status()
    → project_validation.check_integrity()
    → engine.classify_tasks() / engine.compute_cpm()
    → commands 输出 status / next / map / digest
```

### 状态变更

```text
CLI → core.start_task()/done_task()/block_task()
    → project_mutation.*_in_project()
    → close_gate / dependency 检查
    → project_storage.save_project()
    → post_save hooks best-effort
```

### DAG 结构变更

```text
CLI → core.mutate(project, dry_run=...)
    → add_node/remove_node/rewire/replace/promote
    → project_validation.check_integrity()
    → snapshot → save
```

### 需求骨架

```text
pt req ... → core.*requirements*()
           → requirements.py
           → linked project repo 写模板、索引、trace matrix
           → projects/*.yaml 只保存 profile/root/manifest/subprojects/last_check 等轻量状态
```

### Merge-to-Close

```text
pt close set/check/list/report
    → core.update_task_closure()/check_close_gate()
    → close_gate.py
    → projects/*.yaml 保存 closure 元数据
    → linked repo 保存正式结论和可选 backlog/report
```

## 读写边界

### 必须只读

- `pt doctor`
- `python tools/check_repo_boundary.py`
- `pt validate` / `pt validate --all`
- `pt close check`, `pt close-check`, `pt gate closure`
- `pt req check --no-save`、`pt req trace --dry-run --no-save`

### 允许写 `projects/*.yaml`

- 项目切换、任务状态、DAG 编辑、决策/PoC/review 索引、文档路径挂接、close metadata。
- 写入内容必须是紧凑状态和索引，不得沉积正式需求正文、设计正文、验证原文或发布结论。

### 允许写 linked repo

- `pt docs --sync` 写 `.pt/<PROJECT_ID>.yaml` 和 README 状态块。
- `pt req init/index/trace` 写需求骨架、索引和追溯矩阵。
- `pt close report --save <relative-path>` 在项目有 `repo` 时写入 linked repo 相对路径。
- post-save close backlog 写入 linked repo 的 `docs/issues/<PROJECT_ID>_CLOSE_GATE_BACKLOG_AUTO.md`。

### 允许写输出目录

- HTML/PNG/CSV/Mermaid 等导出物应写到调用方指定目录或 ignored 输出目录，不应提交到仓库根目录。

## 不再作为当前事实的内容

- 旧 `docs/PLAN.md`、旧 prompt 升级方案、单项目地图样例、一次性回归报告和历史设计草稿已经归档。
- `docs/issues/` 中的材料是协作议题，不是当前架构事实源。
- `docs/_archive/` 仅供追溯历史，不用于判断当前实现。

# Project Tracker Anchors

这份文档给新 agent / 新同事一个“落脚点”，让进入仓库后能快速找到主干，而不是在命令、流程、知识检索、项目 YAML 之间迷路。

## 1. 先看哪里

按这个顺序读：

1. `README.md` — 安装、CLI 快速开始、基本目录结构
2. `tracker/cli.py` — 所有 CLI 命令的总路由
3. `tracker/core.py` — 项目 YAML 读写、迁移、乐观锁、任务状态变更
4. `tracker/engine.py` — DAG、拓扑排序、关键路径、Slack、依赖分类
5. `tracker/knowledge.py` — Markdown 切块 + BM25 检索
6. `tracker/prompt.py` — Prompt 组装层，把项目上下文变成给 LLM 的输入
7. `tests/test_regressions.py` — 回归保护网，里面基本能看出系统承诺了什么

## 2. 当前架构锚点

### A. CLI 层
- 入口：`pt`, `pt.sh`, `tracker/cli.py`
- 责任：只做参数解析和命令路由
- 不该做：项目读写规则、依赖计算、知识检索细节

### B. 状态持久化层
- 核心文件：`tracker/core.py`
- 数据目录：`projects/`
- 持久化格式：单项目单 YAML
- 关键机制：
  - schema 迁移：`migrate_project_data()`
  - 乐观锁：`_save(..., check_mtime=True)`
  - 历史快照：`.pt_history`

### C. 计划引擎层
- 核心文件：`tracker/engine.py`
- 责任：
  - 构建全局 DAG
  - 识别 ready / waiting / blocked
  - CPM 关键路径和 slack
  - 下游影响和拓扑顺序

### D. AI / 知识增强层
- 核心文件：`tracker/knowledge.py`, `tracker/prompt.py`
- 责任：
  - 从 note / note_file / docs 建知识块
  - 用 BM25 做确定性检索
  - 把当前任务、依赖链、历史结论拼成 prompt

### E. 流程定义层
- 目录：`tracker/flows/`
- 说明：流程模板是产品逻辑，不是运行时状态
- 原则：
  - flow 负责“标准节点是什么”
  - project YAML 负责“现在做到哪了”

## 3. 当前已知高价值入口

### 如果要改 CLI 行为
优先看：`tracker/cli.py` + 对应 `tracker/commands/*.py`

### 如果要改任务状态机 / YAML 结构
优先看：`tracker/core.py`

### 如果要改依赖、关键路径、ready 判断
优先看：`tracker/engine.py`

### 如果要改 prompt 质量
优先看：`tracker/knowledge.py` 和 `tracker/prompt.py`

### 如果要防回归
优先看：`tests/test_regressions.py`

## 4. 这轮新建的工程锚点

为了让 fresh clone 更容易接手，这一轮补了两个基础设施：

- `tests/conftest.py`
  - 作用：保证直接在仓库根目录运行 `pytest` 时，`tracker` 包可被稳定导入
  - 价值：新机器不先 `pip install -e .` 也能直接跑回归

- `pt validate` / `core.validate_project_file(...)`
  - 作用：把结构级 schema 校验和 DAG 完整性检查显式暴露出来
  - 价值：新 agent 可以先验项目 YAML，再开始修改状态或流程

- `.github/workflows/python-tests.yml`
  - 作用：对 `main` / PR 自动执行 `pip install -e . && pytest -q`
  - 价值：把“测试能过”从口头承诺变成 GitHub 上的可见信号

## 5. 推荐验证命令

```bash
python -m pip install -e .
pytest -q
./pt validate
./pt list
./pt --help
```

如果只想做快速静态验证：

```bash
python -m py_compile tracker/*.py tracker/commands/*.py tests/*.py
```

## 6. 下一批适合交给别的 agent 的任务

1. 补 `pyproject.toml` / 现代化打包配置，替代纯 `setup.py`
2. 为关键 CLI 命令增加更细粒度测试，而不是只靠大回归集
3. 给 `projects/*.yaml` 增加更明确的 schema 文档或 JSON Schema
4. 增加导入/导出能力，支持和外部 PM 工具做一跳同步
5. 给 `prompt` / `knowledge` 增加可解释调试输出，方便看“为什么召回这几段”

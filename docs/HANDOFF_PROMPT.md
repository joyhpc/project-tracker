# Handoff Prompt

把下面这段直接发给下一位 agent 即可。

```text
你正在接手 `project-tracker` 仓库。

Repository:
- https://github.com/joyhpc/project-tracker
- Branch: main

这不是 Web 服务，而是一个以 YAML 为状态源的本地 CLI 项目推进系统。
核心目标不是“任务列表漂亮”，而是：
1. 用流程模板定义标准开发路径
2. 用项目 YAML 记录真实推进状态
3. 用 DAG/CPM 找 ready task、关键路径和风险
4. 用知识检索 + prompt 组装增强项目判断质量

你接手时应先建立以下心智模型：
- `tracker/cli.py`：命令入口和路由层
- `tracker/core.py`：兼容 façade，负责项目 YAML 读写、迁移、乐观锁、快照
- `tracker/project_model.py` / `tracker/project_validation.py` / `tracker/project_query.py` / `tracker/project_mutation.py`：已拆出的纯模型、校验、查询、状态机层
- `tracker/engine.py`：依赖图、CPM、ready/waiting 分类
- `tracker/knowledge.py`：Markdown 切块 + BM25 检索
- `tracker/prompt.py`：给 LLM 的 prompt 组装
- `tracker/flows/*.yaml`：流程模板
- `tests/test_regressions.py`：当前行为合同
- `docs/ANCHORS.md`：新加的锚点文档，先读

当前这轮已经完成的优化：
- 新增 `tests/conftest.py`，让 fresh clone 下直接运行 `pytest` 更稳定
- 新增 GitHub Actions：`.github/workflows/python-tests.yml`
- 新增 `docs/ANCHORS.md`
- 新增这份 `docs/HANDOFF_PROMPT.md`
- 新增显式校验入口：`pt validate` / `core.validate_project_file(...)`
- 将 `core.py` 中的共享常量、纯模型逻辑、校验逻辑、状态查询逻辑、状态机规则拆到 `project_*` 模块
- README / anchors / handoff 增补开发验证与架构入口

当前建议先执行：
```bash
python -m pip install -e .
pytest -q
./pt validate
./pt --help
```

工作边界：
- 不要把项目改造成重型服务端系统
- 不要把 YAML 状态源替换成数据库，除非有非常强的理由
- 保持 CLI-first + Git-friendly 的设计原则
- 优先做“提高可接手性、可验证性、可解释性”的优化

推荐下一步路线：
1. 把 subtask template loading / rewire 继续从 `core.py` 拆到独立模块
2. 现代化 packaging（`pyproject.toml`）
3. 给命令层补更细粒度单测
4. 给 project YAML 补 schema / 校验器
5. 给知识检索或状态查询增加 explain/debug 输出

交付风格：
- 尽量小步、可验证、可回滚
- 每次改动后优先跑 `pytest -q`
- 更新 README / docs，保证下一位 agent 不需要重新摸索结构
```

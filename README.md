# Project Tracker (项目推进助手)

基于度信平台机型流程的硬件项目推进 CLI 工具。

## 安装

推荐使用虚拟环境安装，避免系统 Python 的 PEP 668 限制：

```bash
git clone git@github.com:joyhpc/project-tracker.git
cd project-tracker
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

如果你只是临时使用，也可以不安装，直接运行：

```bash
./pt --help
./pt status
```

## 数据迁移

旧项目 YAML 会在运行时自动兼容到当前 schema；如果你想把历史文件直接升级落盘：

```bash
python tools/migrate_projects.py --dry-run
python tools/migrate_projects.py
```

## 快速开始

```bash
# 创建项目
pt init A57-CAMRX --name "A57 摄像头测试设备 - CAMRX" --flow duxin

# 查看状态
pt status

# 显式校验项目 YAML / DAG
pt validate

# 查看所有任务
pt tasks

# 查看下一步
pt next

# 开始任务
pt start pcb_sample

# 完成任务
pt done pcb_sample --note "PCB已发板厂"

# 标记阻塞
pt block pcb_eq --reason "等板厂回复EQ"

# 解除阻塞
pt unblock pcb_eq

# 查看阶段进度
pt phases

# 添加备注
pt note "今天和PCB工程师确认了堆叠方案"

# 查看项目历史
pt log

# 列出所有项目
pt list

# 切换项目
pt switch A57-DCURX
```

## 开发与验证

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
pytest -q
./pt validate
./pt --help
```

如果你是新机器 fresh clone，优先先跑一次 `pytest -q` 确认环境和核心回归都正常。

## 交接文档

- `docs/ANCHORS.md`：新 agent 快速定位核心模块
- `docs/HANDOFF_PROMPT.md`：可直接贴给下一位 agent 的交接 prompt
- `docs/core-architecture.md`：核心状态层 / 校验层 / 查询层 / 状态机层 / 子任务模板层架构
- `docs/architecture.md`：知识检索 / prompt 架构
- `docs/PLAN.md`：历史计划与阶段演进

## 项目结构

```
project-tracker/
├── pt                    # CLI 入口 (可直接 ./pt)
├── tracker/
│   ├── __init__.py
│   ├── cli.py            # CLI 命令定义
│   ├── core.py           # 兼容 façade / 持久化入口
│   ├── project_constants.py # schema 版本与共享枚举
│   ├── project_model.py  # 纯项目模型辅助函数
│   ├── project_validation.py # schema + DAG 完整性校验
│   ├── project_query.py  # 状态聚合 / fallback 查询
│   ├── project_mutation.py # 状态机 / 任务变更规则
│   ├── subtask_templates.py # 子任务模板发现 / DAG 重连
│   └── flow.py           # 流程定义加载
├── flows/
│   └── duxin.yaml        # 度信平台流程定义
├── projects/             # 项目数据 (git tracked)
│   └── A57-CAMRX.yaml
├── setup.py
└── README.md
```

## 流程阶段

```
REQ → FEAS → INIT → OUTLINE → DETAIL → SAMPLE → SW_DEV → INTEG
 │                    MS1                  MS2              MS3
 ↓
TEST_A → TEST_B → TEST_C → TRIAL → RELEASE → ACCEPT
                              MS4
```

## 设计原则

1. **数据即 Git** - 所有项目状态都是 YAML，换电脑 clone 即可
2. **CLI 闭环** - 所有操作通过命令行完成
3. **流程驱动** - 基于标准流程自动推荐下一步
4. **零依赖** - 只需 Python 3.10+ 和 PyYAML

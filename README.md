# Project Tracker (项目推进助手)

> **[REVIEW] 新增: 钩子协议 (`pt hooks`) + 领域同步桥 (`pt domain-sync`) — 详见 `tracker/post_save.py`, `tracker/domain_sync.py`**

基于 DAG + CPM 关键路径的硬件项目推进 CLI 工具。

**核心能力**: 全局 DAG + CPM 引擎 | BM25 知识检索 | LLM Prompt 生成 | 投板门禁 | 风险量化 | 审核工具链集成

## 安装

```bash
git clone git@github.com:joyhpc/project-tracker.git
cd project-tracker
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

或直接运行：`./pt --help`

## 快速开始

```bash
# 项目管理
pt init A57 --name "A57 域控测试盒" --flow duxin
pt status                      # 查看状态
pt map                         # 终端项目地图
pt map --html                  # HTML 项目地图
pt list                        # 列出所有项目
pt switch A57                  # 切换项目

# 任务操作
pt tasks                       # 查看任务列表
pt next                        # 下一步行动
pt start pcb_sample            # 开始任务
pt done pcb_sample --note "已发板厂"  # 完成任务
pt block pcb_eq --reason "等EQ"      # 标记阻塞

# 分析与决策
pt risk                        # 风险评估
pt prompt "MIPI问题" --deep    # 生成带知识上下文的 LLM prompt
pt decision --add "方案变更"   # 登记决策
pt poc --add "验证项" --metric "红线指标"  # PoC 追踪

# 审核集成（v2.5 新增）
pt review-sync                 # 从 sch-review 自动同步审核报告
pt gate schematic_review       # 投板门禁检查（P0/P1/P2 汇总）
pt gate schematic_review --scan-dir ~/sch-review/reports/gwbrgic/

# 数据导出
pt gantt                       # Mermaid Gantt 图
pt deps                        # 依赖图
pt burndown                    # 燃尽图
pt export nodes                # CSV 导出
```

## 项目结构

```
project-tracker/
├── pt                           # CLI 入口
├── tracker/
│   ├── cli.py                   # 命令路由
│   ├── core.py                  # 持久化 façade
│   ├── engine.py                # DAG + CPM 引擎
│   ├── knowledge.py             # BM25 知识检索（硬件术语增强）
│   ├── prompt.py                # LLM Prompt 生成（v4: BM25 + 角色聚焦）
│   ├── risk.py                  # 多维度风险评分
│   ├── conflict.py              # 多项目资源冲突
│   ├── project_map.py           # 项目地图（终端 + HTML）
│   ├── project_model.py         # 纯函数辅助
│   ├── project_validation.py    # schema + DAG 校验
│   ├── project_mutation.py      # 状态机规则
│   ├── project_query.py         # 状态聚合
│   ├── project_constants.py     # schema 版本
│   ├── subtask_templates.py     # 子任务模板 DAG 重连
│   ├── flow.py                  # 流程定义加载
│   ├── onboard.py               # 中途导入
│   ├── guide.py                 # 启发式引导
│   ├── commands/
│   │   ├── gate_cmd.py          # 投板门禁（P0→NO-GO 映射）
│   │   ├── review_sync_cmd.py   # sch-review 报告自动同步
│   │   ├── prompt_cmd.py        # Prompt 导出
│   │   ├── node_cmd.py          # 节点 CRUD
│   │   ├── scan_cmd.py          # 仓库扫描
│   │   └── ...
│   ├── datax/                   # 数据导出（burndown/gantt/csv/deps）
│   ├── notify/                  # 通知子包
│   └── web/                     # Web 看板子包
├── flows/                       # 流程模板
│   ├── duxin_v2.yaml            # 度信平台流程
│   ├── generic_v2.yaml          # 通用流程
│   └── subtasks/                # 子任务模板
│       ├── board_bringup.yaml
│       ├── schematic_design.yaml
│       ├── signal_validation.yaml
│       └── mcu_firmware.yaml
├── projects/                    # 项目数据 (git tracked)
├── docs/                        # 架构文档
└── setup.py
```

## 硬件审核工具集成

```
sch-review (审核判定)          opendatasheet (器件参数)
        │                              │
        └──── pt review-sync ──────────┘
                    │
         project-tracker (项目中枢)
           │ DAG + CPM │ 知识库 │ 门禁 │
                    │
              pt prompt --deep
                    │
              Claude Code (AI 对话)
```

### 投板门禁 (`pt gate`)

- 自动汇总节点关联的所有审核报告
- sch-review P0 → pt NO-GO | P1 → CAUTION | P2 → GO
- 有 P0 未闭合 → 输出阻断清单 → 阻止投板

### 审核同步 (`pt review-sync`)

- 扫描 `~/sch-review/reports/` 中的审核报告
- 解析 P0/P1/P2 标记，自动注册到项目 reviews
- 支持 `--dry-run` 试运行

## 流程阶段

```
REQ → FEAS → INIT → OUTLINE → DETAIL → SAMPLE → SW_DEV → INTEG
                      MS1                  MS2              MS3
TEST_A → TEST_B → TEST_C → TRIAL → RELEASE → ACCEPT
                              MS4
```

## 设计原则

1. **数据即 Git** — YAML 文件，clone 即用
2. **CLI 闭环** — 所有操作命令行完成
3. **流程驱动** — 标准流程 + CPM 自动推荐
4. **零依赖** — Python 3.10 + PyYAML
5. **审核闭环** — 与 sch-review 双向打通，投板决策有据可查

## 开发

```bash
pytest -q
./pt validate --all
```

## 文档

- `docs/architecture.md` — 知识检索 / prompt 架构
- `docs/req-architecture.md` — 需求体系平台化架构
- `docs/PLAN.md` — 开发计划与版本演进
- `docs/DECISION_FRAMEWORK.md` — 决策框架
- `docs/KNOWLEDGE_ROUTING.md` — 项目经验沉淀与规则升级法则
- `docs/graph-refactor-design.md` — DAG 重构设计

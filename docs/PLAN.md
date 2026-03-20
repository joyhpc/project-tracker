# Project Tracker — 开发计划

## 已完成

### v1.0 (2/18) — 基础功能完整
- 24个CLI命令, 2804行, 阶段容器模型
- prompt引擎(实体驱动+信号检测)

### v2.0 (2/19 上午) — 图论架构重构
- 全局DAG + CPM关键路径 + Slack
- 单文件自包含项目
- 子任务一等节点
- 19个场景闭环验证通过

### v2.1 (2/19) — 跨阶段依赖 ✅
- 29条跨阶段依赖，总工期 24天→132天
- 关键路径贯穿14阶段(49节点)

### v2.2 (2/19) — 死代码清理 ✅
- 删除 formatter.py + timeline.py (-526行)
- 代码量 3161→2635行

### v2.3 (2/19) — 子任务跨边界 + 通用性 ✅
- 边重连(Rewire)机制：入口继承、出口替代、父节点排除
- 子任务参与全局CPM（7个子任务在关键路径上）
- generic流程跨阶段依赖（8条，18→45天）
- 3流程通用性验证通过

### v2.4 — 项目地图 + Web + 数据导出 ✅
- 终端文本项目地图 `pt map`
- HTML 项目地图（暗色主题，响应式）
- datax 子包：burndown / gantt / csv / deps_graph / stats
- Web 看板子包
- notify 通知子包

### v2.5 (3/12) — 硬件审核工具链集成 ✅
- **`pt gate`** — 投板门禁命令：扫描审核报告汇总 P0/P1/P2，NO-GO 判定
- **`pt review-sync`** — sch-review 报告自动同步（P0→NO-GO, P1→CAUTION, P2→GO）
- **BM25 分词增强** — 硬件位号/型号（U4/TPS56C215）、规格值（3.5Gbps）、FPGA pin 格式整体保留
- **A57 数据补全** — 5 个 decisions、3 个 POCs、11 个关键任务工时估算，CPM 总工期 100→148 天
- **repo 路径修复** — /tmp → ~/A57-docs

## 待完成

### v2.6 — 审核深度集成
- [ ] `pt gate` 自动关联节点与板卡名，无需手动 --scan-dir
- [ ] review-sync 增量同步（只同步新增/变更的报告）
- [ ] gate 结果写入项目 log，可追溯
- [ ] BM25 索引审核报告内容（审核结论参与 pt prompt 检索）

### v2.7 — 需求体系平台化
- [x] 新增 `pt req` 一级命令，围绕 active project + linked repo 工作
- [x] `req init` 在目标 repo 中生成需求骨架，不把项目正文写入 `project-tracker`
- [x] `req index` 维护需求阶段索引页
- [x] `req check` 校验需求链路缺页、断链、当前有效结论
- [x] `req trace` 管理项目级需求到子项目目标/验证/结论的追溯矩阵
- [ ] `req attach` 将关键需求文档批量挂接到项目任务
- [x] 项目 YAML 增加轻量 `requirements` 状态，供 `status/brief/prompt` 后续使用

### v3.0 — 多工具协同
- [ ] `pt component <位号>` — 调用 opendatasheet 查询器件参数
- [ ] `pt analyze <板名>` — 调用 hardware-copilot 拓扑/时序分析
- [ ] 知识库整合：审核报告 + 器件数据 + 拓扑分析 → 统一 BM25 索引
- [ ] Claude Code / MCP 集成：pt 作为 MCP tool server

### v3.1 — 多项目/多板卡结构
- [ ] 父子项目关系（A57 → DCURX / CAMRX / PMU）
- [ ] 跨项目依赖和关键路径
- [ ] 资源瓶颈跨项目可视化

### 远期
- [ ] pip install 打包分发
- [ ] Web Dashboard 增强（burndown 趋势、审核状态卡片）
- [ ] 多人协作（Git 友好的乐观锁已就绪）
- [ ] Skills / AI Agent 集成

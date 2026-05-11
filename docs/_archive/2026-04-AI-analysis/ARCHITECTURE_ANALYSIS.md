# Project-Tracker 完整架构分析

## 📊 代码规模与分布

### 核心模块 (7700+ 行)
| 模块 | 行数 | 职责 | 复杂度 |
|------|------|------|--------|
| core.py | 1865 | 数据持久化 façade + 迁移 | 🔴 高 |
| requirements.py | 778 | 需求体系平台化 + 追溯矩阵 | 🟡 中 |
| prompt.py | 506 | LLM Prompt 生成 + BM25 | 🟡 中 |
| project_map.py | 506 | 项目地图 (Mermaid/HTML) | 🟡 中 |
| project_validation.py | 443 | Schema + DAG 校验 | 🟡 中 |
| cli.py | 428 | 命令路由层 | 🟢 低 |
| onboard.py | 410 | 中途导入助手 | 🟢 低 |
| engine.py | 386 | DAG + CPM 关键路径 | 🔴 高 |
| project_mutation.py | 275 | 状态机规则 | 🟡 中 |
| post_save.py | 274 | 钩子协议 + 自动化 | 🟢 低 |
| guide.py | 231 | 启发式引导 | 🟢 低 |
| domain_sync.py | 230 | 领域同步桥 | 🟢 低 |
| fuzzy.py | 225 | 自然语言意图解析 | 🟡 中 |
| knowledge.py | 215 | BM25 知识检索 | 🟡 中 |
| subtask_templates.py | 210 | 子任务模板 DAG 重连 | 🟡 中 |
| risk.py | 173 | 多维度风险评分 | 🟡 中 |
| close_gate.py | 135 | 投板门禁规则 | 🟢 低 |
| conflict.py | 118 | 多项目资源冲突检测 | 🟡 中 |

### 命令层 (27 文件)
| 分类 | 文件数 | 重点 | 行数范围 |
|------|--------|------|----------|
| 任务操作 | 5 | tasks.py, node_cmd.py | 260-340 |
| 分析导出 | 6 | analysis.py, prompt_cmd.py | 250-295 |
| 审核集成 | 3 | review_cmd.py, gate_cmd.py | 150-400 |
| 数据同步 | 3 | review_sync_cmd.py, domain_sync_cmd.py | 60-156 |
| 低价值 | 8 | conflict_cmd.py, guide_cmd.py, notify_cmd.py 等 | 5-70 |
| 辅助 | 2 | web_cmd.py | 5-30 |

## 🎯 3-5 个高价值核心功能

### 1. **DAG + CPM 关键路径引擎** ⭐⭐⭐⭐⭐
- **文件**: engine.py (386 行)
- **功能**:
  - DAG 构建与拓扑排序 (Kahn 算法)
  - CPM 关键路径法计算 (Slack, ES/EF/LS/LF)
  - 任务分类 (关键/准关键/缓冲/自由度)
  - 智能工时默认估算 (_SMART_DEFAULTS)
- **用途**: 支撑风险评估、投板门禁、进度管理
- **依赖**: core.py → engine.py → {prompt.py, risk.py, project_map.py}
- **数据质量**: 直接影响所有后续分析的准确性

### 2. **BM25 知识检索 + LLM Prompt 生成** ⭐⭐⭐⭐
- **文件**: knowledge.py (215) + prompt.py (506)
- **功能**:
  - Markdown AST 切块 + 硬件术语增强分词
  - BM25 TF-IDF 数学检索 (无需 LLM API)
  - 角色聚焦 (决策/方案/风险/战略)
  - 上下文融合 (产品背景 + 项目数据 + 风险评分)
- **用途**: `pt prompt --deep` 一键生成高质量 LLM 提示词
- **创新点**: 硬件领域优化的分词 + 实时 DAG 数据融合

### 3. **投板门禁系统** ⭐⭐⭐⭐
- **文件**: close_gate.py (135) + gate_cmd.py (200)
- **功能**:
  - sch-review P0/P1/P2 自动映射 (NO-GO/CAUTION/GO)
  - 门禁条件聚合 (评审、样品、认证等)
  - 阻断清单生成
- **集成**: sch-review + opendatasheet
- **用途**: `pt gate <node>` 投板决策有据可查

### 4. **项目状态机 + 持久化 façade** ⭐⭐⭐⭐
- **文件**: core.py (1865) + project_mutation.py (275) + project_query.py (71)
- **功能**:
  - YAML 版本迁移 + Schema 演进
  - 状态转移规则 (pending → in_progress → done/blocked)
  - 依赖校验 + 循环检测
  - 事务性保存 + 自动备份
- **用途**: 项目数据可靠性与版本兼容性

### 5. **需求体系平台化** ⭐⭐⭐
- **文件**: requirements.py (778)
- **功能**:
  - 追溯矩阵模板 (需求 → 子项目 → 验证)
  - 自动索引 + 完整性校验
  - 多项目分解与汇总
- **用途**: `pt req init/trace/check` 硬件需求全链路管理

---

## ❌ 2-3 个可以删除的低价值模块

### 1. **conflict.py + conflict_cmd.py** ⚠️ 删除优先级: 高
- **当前规模**: 118 + 8 = 126 行
- **功能**: 多项目资源冲突检测 (owner 负载分析)
- **问题**:
  - 使用频率极低 (文件仅 8 行入口)
  - 硬阈值 (`>= 10 tasks`) 无法适配多种项目规模
  - 逻辑重复: risk.py 已计算 owner_load
  - 无人活跃维护迹象 (无测试用例)
- **替代方案**:
  - 整合到 `pt stats` 或 `pt risk --cross-project`
  - 或作为报告功能合并到 `analyze.py`
- **迁移成本**: 低 (仅内部使用，无外部依赖)

### 2. **guide.py + guide_cmd.py** ⚠️ 删除优先级: 中
- **当前规模**: 231 + 37 = 268 行
- **功能**: 交互式项目启发式问卷引导
- **问题**:
  - 依赖外部文件 (`flows/guide_questions.yaml`) 维护成本高
  - 生成的项目框架已被 `pt init --flow duxin` 取代
  - 运行频率极低 (仅新建项目时一次)
  - 问题模板老化风险
- **替代方案**:
  - 保留问卷，改为可选的 `--guide` 参数
  - 或完全移到文档 (README 检查清单)
- **迁移成本**: 低 (独立功能，无深度依赖)

### 3. **onboard.py** ⚠️ 删除优先级: 中偏低
- **当前规模**: 410 行
- **功能**: 中途导入历史项目
- **问题**:
  - 仅在特殊场景使用 (迁移遗留项目)
  - 与 core.py 的迁移逻辑重复
  - 维护成本: 需要追踪多版本 schema
  - 无单元测试
- **替代方案**:
  - 功能合并到 core.py 的 `migrate_project_data()`
  - 保留 CLI 入口，但逻辑统一化
- **迁移成本**: 中 (涉及迁移流程重构)

---

## 🏗️ 主要技术负债

### 1. **core.py 的上帝类问题** 🔴
- **规模**: 1865 行 (总代码的 24%)
- **职责**:
  - YAML I/O
  - 数据迁移
  - 40+ 个 internal API (前缀 `_`)
  - 命令代理转发
- **问题**:
  - 修改需要全量回归测试
  - 难以理解数据流向
  - 新功能优先选择堆在 core.py 而非创建新模块
- **建议**:
  ```
  core.py (1865)
  ├─ core_io.py (数据 I/O, ~200 行)
  ├─ core_migration.py (版本迁移, ~300 行)
  ├─ core_api.py (Internal API, ~800 行)
  └─ core_facade.py (公开接口, ~200 行)
  ```

### 2. **命令层设计冗余** 🟡
- **问题**: 27 个命令文件，很多只是薄包装
- **示例**:
  - conflict_cmd.py: 8 行 → 调用 conflict.py
  - guide_cmd.py: 37 行 → 调用 guide.py
  - risk_cmd.py: 33 行 → 调用 risk.py
  - notify_cmd.py: 30 行 → 调用 notify/
- **建议**:
  - 合并薄命令为 analysis.py
  - 保留复杂命令 (review_cmd.py, node_cmd.py, tasks.py)
  - 可减少 ~8-10 个文件

### 3. **缺乏数据验证中间件** 🟡
- **问题**:
  - 每个命令独立校验输入
  - 重复的依赖检查逻辑
  - 无统一的错误处理
- **示例**:
  - tasks.py, node_cmd.py, update_cmd.py 都有类似的 "获取当前项目" 逻辑
- **建议**:
  - 抽象 CommandContext 类
  - 统一参数验证与异常处理

### 4. **项目地图双模式不一致** 🟡
- **问题**:
  - project_map.py 同时处理 Mermaid + HTML 渲染
  - 两种输出格式共用一套逻辑，难以独立优化
  - 不支持 PlantUML / GraphViz 等扩展
- **建议**:
  ```
  project_map.py (纯数据转换)
  ├─ map_renderer_mermaid.py
  ├─ map_renderer_html.py
  └─ map_renderer_graphviz.py (未来)
  ```

### 5. **测试覆盖率低** 🟡
- **统计**:
  - 9 个测试文件 (test_*.py)
  - 覆盖: core, project_mutation, validation, requirements 等核心路径
  - **缺失**: guide.py, conflict.py, fuzzy.py, knowledge.py 无单元测试
- **建议**:
  - 为 knowledge.py 添加分词 + BM25 单测
  - 为 engine.py 添加 CPM 精度测试
  - 为 fuzzy.py 添加意图识别用例

---

## 🚨 现有的架构问题

### 问题 1: 循环依赖隐患
```
engine.py ←→ project_map.py (都用 build_graph)
risk.py ←→ prompt.py (都用 engine + cpm)
```
**影响**: 难以单独测试
**方案**: 提取 `graph_utils.py` 作为共享库

### 问题 2: 命令参数散乱
- 有的命令用 `args.project_id`，有的用 `args.id`
- 有的支持 `--json`，有的没有
- 错误消息格式不统一

**方案**: 建立 `command_base.py` 统一基类

### 问题 3: 数据模型与 Schema 脱离
- project_model.py 是纯函数，无类型保证
- Schema 在 project_constants.py，但 mypy 无法强制执行
- 迁移逻辑分散在 3 个地方 (core, onboard, project_constants)

**方案**: 引入 dataclass + TypedDict，配合 mypy 严格模式

### 问题 4: 测试数据和 fixtures 混乱
- conftest.py 中的 fixture 不完整
- 各测试文件自定义 mock project，难以维护

**方案**: 建立 `tests/fixtures/` 目录，统一管理

---

## 📈 推荐优化路线

### 第一阶段 (1-2 周): 清债
1. **删除低价值模块**
   - ❌ conflict.py + conflict_cmd.py
   - ⚠️ guide.py 降级为文档 + 可选 `--guide` 参数
   - 预期: 减少 ~400 行，降低维护成本

2. **合并命令层冗余**
   - risk_cmd.py, notify_cmd.py 并入 analysis.py
   - 预期: 减少 ~100 行，简化导航

### 第二阶段 (2-3 周): 重构核心
1. **拆分 core.py**
   - core_io.py (YAML I/O)
   - core_migration.py (版本管理)
   - core_api.py (Internal API)
   - 预期: 单文件 < 500 行，可独立测试

2. **统一命令框架**
   - CommandContext 基类
   - 统一异常处理
   - 预期: 新命令开发时间 -40%

### 第三阶段 (3-4 周): 增强测试
1. **补充单元测试**
   - engine.py: CPM 精度验证
   - knowledge.py: BM25 + 分词单测
   - fuzzy.py: 意图识别用例
   - 预期: 覆盖率 > 70%

2. **添加集成测试**
   - E2E 场景: init → add tasks → compute CPM → prompt

---

## 🎯 总结矩阵

| 维度 | 评分 | 备注 |
|------|------|------|
| 代码组织 | 6/10 | core.py 过大，命令层冗余 |
| 功能完整性 | 9/10 | DAG + CPM + 知识库 + 门禁很强 |
| 可测试性 | 5/10 | 缺基础设施，多个模块无测试 |
| 文档清晰度 | 7/10 | 架构文档好，代码注释可改进 |
| 扩展性 | 6/10 | 需要重构才能加新渲染器/集成 |
| 性能 | 8/10 | YAML I/O 可优化，总体轻量 |
| **总体健康度** | **6.8/10** | **高价值、高复杂、中等腐坏度** |

# 图论架构重构设计文档
# 基于超级 LLM 分析 + Nova 项目经验的最终决策

## 核心变更

### 旧模型
```yaml
phases:                    # 阶段是容器
  - id: DETAIL
    tasks:                 # 任务嵌套在阶段里
      - id: schematic_design
        depends: [...]     # 依赖只能在阶段内
```

### 新模型
```yaml
nodes:                     # 扁平节点列表
  - id: schematic_design
    name: 原理图设计
    type: task             # task | milestone
    phase: DETAIL          # 阶段是标签，不是容器
    owner: 硬件工程师
    depends: [new_component_selection]  # 跨阶段依赖自由
    days: 5
    deliverables: [原理图DSN文件]
    gate: 电源树和框图审核通过

  - id: design_freeze      # 里程碑节点
    name: 设计冻结
    type: milestone         # 工时=0，逻辑控制门
    phase: DETAIL
    depends: [pcb_review, design_archive]

phases:                    # 阶段元数据（仅用于分组展示）
  - id: DETAIL
    name: 详细设计
  - id: SAMPLE
    name: 制样阶段
    milestone: MS2
```

## 5 个决策

1. **阶段 = 标签 + 里程碑节点**
   - phase 字段是分组标签，不影响引擎逻辑
   - 里程碑是 type=milestone 的特殊节点（days=0）
   - 引擎只看 nodes + depends，不看 phases

2. **子任务 = 扁平化展开**
   - sub-load 时子任务提升为一等节点（加前缀 parent.sub）
   - 父节点被替换，不保留
   - Roll-up 在展示层做，不影响计算

3. **项目 = 单文件自包含**
   - 创建时从模板 deep copy 完整图
   - 项目文件包含 nodes + 状态 + 日志
   - 模板更新不影响已创建项目

4. **序列化 = 邻接表（depends 在节点里）**
   - 节点扁平存储，phase 是属性
   - 不用 edges 分离列表
   - 人类可读，Git 友好

5. **关键路径 = CPM（基于工时）**
   - 前向推导(ES/EF) + 反向推导(LS/LF)
   - Slack = LS - ES
   - Slack=0 的节点 = 关键路径
   - 子图展平后参与全局计算

## 影响范围

### 需要重写
- flow.py — 新的流程加载（扁平节点）
- engine.py — CPM 算法替换当前的步数算法
- core.py — 项目数据结构（单文件自包含）
- timeline.py — 基于 CPM 结果渲染

### 需要适配
- risk.py — 用 Slack 替代当前的启发式评分
- conflict.py — 从新数据结构读取 owner
- prompt.py — 从新数据结构提取上下文
- formatter.py — 适配新输出
- 所有 commands — 适配新 API

### 不变
- CLI 命令接口（用户体验不变）
- 子任务模板格式（但加载逻辑变）

## 迁移策略
- 写转换脚本：旧 phases→tasks 格式 → 新 nodes 格式
- 旧版备份在 git tag v1.0-pre-graph

# LLM 回复处理架构

## 流程

```
pt prompt --auto          → 生成问题
pt prompt "问题" --full   → 生成 prompt，复制给超级 LLM
                          → 超级 LLM 回复
pt review <task> --from <source> --save   → 处理回复
```

## pt review 命令设计

```bash
# 从 Notion 页面读取回复，整理+分析+保存
pt review <task_id> --from notion:<page_id> --save

# 从本地文件读取
pt review <task_id> --from file:path/to/reply.md --save

# 从剪贴板读取
pt review <task_id> --from clipboard --save
```

## 处理流程（三步）

### Step 1: 格式整理
- 统一 markdown 格式（标题层级、表格、列表）
- 提取结构化数据（决策结论、选型结果、风险清单）
- 生成摘要（一句话结论 + 关键要点）

### Step 2: 批判性分析
- 基于项目上下文（已完成任务的 note_file）自动生成分析框架
- 标注：✅ 认同 / ⚠️ 质疑 / ❌ 反对 / 🎯 补充
- 检查是否有遗漏（对照 pt guide 的问题清单）

### Step 3: 保存与关联
- 保存到仓库 `docs/<phase>/<序号>-<主题>-result.md`
- 自动 `pt docs --attach` 关联到对应任务
- 提取关键结论更新任务 note
- `pt docs --sync --push` 同步到仓库

## 文件命名规范

```
docs/concept/
  market-research.md              # 原始调研
  01-decision-result.md           # 决策拍板结果
  02-concept-design-result.md     # 概念设计方案结果
  03-risk-analysis-result.md      # 风险分析结果
  ...
```

## 数据流

```
Notion/文件/剪贴板
    ↓ pt review --from
格式整理 → 批判分析 → 保存到 docs/
    ↓                    ↓
更新任务 note          pt docs --attach
    ↓                    ↓
pt docs --sync --push → GitHub
```

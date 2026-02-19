"""更新 Notion 架构文档"""
import json
import urllib.request
from pathlib import Path

NOTION_KEY = Path("~/.config/notion/api_key").expanduser().read_text().strip()
PARENT_ID = "30b07a52-cb64-810a-918c-fa4245003583"

def notion_append(blocks):
    data = json.dumps({"children": blocks}).encode()
    req = urllib.request.Request(
        f"https://api.notion.com/v1/blocks/{PARENT_ID}/children",
        data=data,
        headers={
            "Authorization": f"Bearer {NOTION_KEY}",
            "Notion-Version": "2025-09-03",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())

def h1(text):
    return {"object":"block","type":"heading_1","heading_1":{"rich_text":[{"text":{"content":text}}]}}

def h2(text):
    return {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"text":{"content":text}}]}}

def h3(text):
    return {"object":"block","type":"heading_3","heading_3":{"rich_text":[{"text":{"content":text}}]}}

def p(text):
    return {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"text":{"content":text}}]}}

def code(text, lang="yaml"):
    return {"object":"block","type":"code","code":{"language":lang,"rich_text":[{"text":{"content":text}}]}}

def bullet(text):
    return {"object":"block","type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"text":{"content":text}}]}}

def divider():
    return {"object":"block","type":"divider","divider":{}}

# ── 第1批：概述 + 架构 ──
batch1 = [
    divider(),
    h1("v2.0 架构（图论重构后）"),
    p("⚠️ 以下内容为 v2.0 最新架构，旧版四层架构文档在上方保留作为历史参考。"),
    divider(),

    h1("1. 系统定位"),
    p("通用电子产品硬件项目智能推进 CLI 工具。基于全局 DAG（有向无环图）+ CPM（关键路径法）进行多维分析。"),
    p("核心价值：不是列任务清单，而是在任意项目状态下，基于全局依赖图分析出最优行动方案、关键路径、松弛时间、风险评分。"),
    bullet("支持任意流程定义（YAML），零硬编码"),
    bullet("跨阶段依赖建模 — 真实反映硬件项目的并行工程"),
    bullet("子任务作为一等节点参与全局 CPM 计算"),
    bullet("单文件自包含项目 — Git 友好，无数据库依赖"),

    h1("2. 核心架构：全局 DAG + CPM"),
    h2("2.1 数据模型"),
    p("v1.0 用「阶段容器 → 任务列表」的树形结构，阶段是硬边界，依赖只能在阶段内表达。\nv2.0 改为「扁平节点列表 + 阶段标签」的 DAG 模型，依赖可以跨越任意阶段。"),
    code("""# v2.0 数据模型
phases:                    # 阶段元数据（仅用于分组展示）
  - id: DETAIL
    name: 详细设计

nodes:                     # 扁平节点列表（核心）
  - id: schematic_design
    name: 原理图设计
    type: task             # task | milestone
    phase: DETAIL          # 阶段是标签，不是容器
    owner: 硬件工程师
    depends: [new_component_selection]  # 跨阶段依赖自由
    days: 10
    deliverables: [原理图DSN文件]
    gate: 电源树和框图审核通过

  - id: design_freeze      # 里程碑节点
    name: 设计冻结
    type: milestone         # 工时=0，逻辑控制门
    phase: DETAIL
    depends: [pcb_review, design_archive]"""),
]
notion_append(batch1)
print("✅ 第1批写入完成")

# ── 第2批：5个架构决策 ──
batch2 = [
    h2("2.2 五个架构决策"),
    p("基于超级 LLM 分析（参考 MS Project、Primavera P6、Jira Advanced Roadmaps）+ Nova 项目经验："),
    bullet("① 阶段 = 标签 + 里程碑节点 — phase 字段是分组标签，不影响引擎逻辑；里程碑是 type=milestone 的特殊节点（days=0），作为阶段门控"),
    bullet("② 子任务 = 扁平化展开 — 子任务提升为一等节点（ID: parent.sub_id），参与全局 CPM 计算；Roll-up 在展示层做"),
    bullet("③ 项目 = 单文件自包含 — 创建时从模板 deep copy 完整图，模板更新不影响已创建项目"),
    bullet("④ 序列化 = 邻接表 — depends 写在节点里，人类可读，Git 友好"),
    bullet("⑤ 关键路径 = CPM（基于工时）+ Slack — 前向推导(ES/EF) + 反向推导(LS/LF)，Slack=0 即关键路径"),

    h2("2.3 CPM 关键路径算法"),
    p("标准关键路径法（Critical Path Method），时间复杂度 O(V+E)："),
    bullet("Step 1: 拓扑排序（Kahn 算法）+ 环检测"),
    bullet("Step 2: 前向推导 — ES(最早开始) = max(所有前驱的EF)，EF = ES + days"),
    bullet("Step 3: 反向推导 — LF(最晚结束) = min(所有后继的LS)，LS = LF - days"),
    bullet("Step 4: Slack = LS - ES，Slack=0 的节点 = 关键路径"),
    bullet("Step 5: Roll-up — 父节点 Start=min(子节点ES), End=max(子节点EF)"),
    p("Slack 的实际价值：控制加急费（slack>20天走海运不走空运）、设备调度（slack=0的任务优先用测试设备）、供应链风险缓冲。"),
]
notion_append(batch2)
print("✅ 第2批写入完成")

# ── 第3批：模块架构 ──
batch3 = [
    h1("3. 模块架构"),
    p("v2.0 共 2635 行 Python，17 个模块，24 个命令。"),

    h2("3.1 核心模块"),
    bullet("flow.py (86行) — 流程定义加载，扁平节点访问，兼容 v1/v2 格式"),
    bullet("engine.py (314行) — 全局 DAG 构建 + CPM + 拓扑排序 + 环检测 + Slack + 任务分类 + 优先级 + 阻塞分析"),
    bullet("core.py (469行) — 项目 CRUD + 单文件自包含 + 节点直接操作 + 子任务一等节点"),
    bullet("risk.py (173行) — 基于 Slack 的多维风险评分（替代旧版启发式）"),
    bullet("conflict.py (118行) — 多项目资源冲突检测"),
    bullet("prompt.py (351行) — 实体驱动 Prompt 引擎（任务/人员/阶段提取 + 信号检测）"),
    bullet("guide.py (257行) — 启发式项目引导"),

    h2("3.2 命令模块"),
    bullet("cli.py (153行) — 参数解析和路由"),
    bullet("commands/project.py (135行) — init, list, switch, status, phases, note, log"),
    bullet("commands/tasks.py (226行) — tasks, next, start, done, block, unblock, sub*"),
    bullet("commands/analysis.py (244行) — plan, digest, timeline, estimate"),
    bullet("commands/risk_cmd.py (24行) — risk"),
    bullet("commands/conflict_cmd.py (8行) — conflict"),
    bullet("commands/prompt_cmd.py (37行) — prompt"),
    bullet("commands/guide_cmd.py (37行) — guide"),

    h2("3.3 数据文件"),
    bullet("flows/duxin_v2.yaml — 度信平台流程（88节点, 14阶段, 29条跨阶段依赖）"),
    bullet("flows/generic_v2.yaml — 通用电子产品流程（24节点, 5阶段）"),
    bullet("flows/minimal_v2.yaml — 极简测试流程（5节点, 2阶段）"),
    bullet("flows/subtasks/*.yaml — 子任务模板（原理图设计14任务, MCU固件14任务）"),
    bullet("flows/guide_questions.yaml — 启发式引导问题模板"),
]
notion_append(batch3)
print("✅ 第3批写入完成")

# ── 第4批：使用方法 ──
batch4 = [
    h1("4. 使用方法"),

    h2("4.1 项目管理"),
    code("""# 创建项目（从模板 deep copy）
pt init DX --name "度信摄像头" -f duxin

# 查看项目状态（进度 + 关键路径 + 可执行任务）
pt status    # 别名: pt s

# 查看阶段进度
pt phases    # 别名: pt ph

# 列出/切换项目
pt list      # 别名: pt ls
pt switch DX2""", "bash"),

    h2("4.2 任务操作"),
    code("""# 查看任务列表
pt tasks                    # 所有主任务
pt tasks --phase DETAIL     # 按阶段过滤
pt tasks --all              # 包含子任务

# 查看下一步行动（CPM 优先级排序 + 并行建议）
pt next      # 别名: pt n

# 任务状态变更
pt start schematic_design
pt done schematic_design --note "设计完成"
pt done pcb_layout --force   # 跳过依赖检查
pt block schematic_design -r "等待电源芯片样品"
pt unblock schematic_design""", "bash"),

    h2("4.3 子任务"),
    code("""# 列出可用模板
pt sub-load --list

# 从模板加载子任务（作为一等节点插入）
pt sub-load schematic_design schematic_design

# 查看子任务
pt sl schematic_design

# 手动添加子任务
pt sub schematic_design test_circuit -n "测试电路设计" -o "硬件工程师"

# 完成/阻塞子任务
pt sd schematic_design.block_diagram --note "框图完成"
pt sb schematic_design.arch_design -r "等待芯片手册" """, "bash"),

    h2("4.4 分析工具"),
    code("""# 作战地图（全局 DAG 视图 + Slack）
pt plan

# 时间线（CPM 甘特图）
pt timeline --start 2026-02-19
pt timeline --phase DETAIL

# 风险评估（基于 Slack + 下游影响 + 资源瓶颈）
pt risk

# 多项目资源冲突检测
pt conflict

# 项目摘要
pt digest
pt digest --json

# 工时估算
pt estimate schematic_design 10
pt estimate --show""", "bash"),

    h2("4.5 AI 辅助"),
    code("""# Prompt 导出（自动注入项目上下文）
pt prompt "原理图设计被阻塞了怎么办"
pt prompt "如何加速项目进度"
pt prompt --list              # 列出支持的问题类型
pt prompt "..." --system      # 显示 system prompt
pt prompt "..." --save out.md # 保存到文件

# 启发式项目引导
pt guide --overview
pt guide --phase REQ --product "摄像头测试设备" """, "bash"),
]
notion_append(batch4)
print("✅ 第4批写入完成")

# ── 第5批：数据流 + 版本历史 ──
batch5 = [
    h1("5. 数据流"),
    code("""用户输入 → CLI (cli.py)
              ↓
         参数解析 → Commands
              ↓
         Core (core.py) ← 项目 YAML (单文件自包含)
              ↓
         Engine (engine.py) ← 全局 DAG + CPM
              ↓
         输出: 关键路径 / Slack / 优先级 / 风险 / 时间线""", "plain text"),

    h1("6. 设计原则"),
    bullet("零硬编码 — 引擎适配任意 YAML 流程定义"),
    bullet("全局 DAG — 依赖不受阶段边界限制，跨阶段并行自然表达"),
    bullet("CPM 驱动 — 所有分析基于关键路径和 Slack，不是启发式猜测"),
    bullet("单文件自包含 — 项目创建时 deep copy 模板，之后独立演化"),
    bullet("子任务一等公民 — 子任务参与全局 CPM，不是二等数据"),
    bullet("Git 友好 — YAML 存储，一个项目一个文件，版本控制无冲突"),

    h1("7. 版本历史"),
    bullet("v0.2-v0.9: 基础功能迭代（依赖图/子任务/plan/digest/guide/timeline/risk/conflict）"),
    bullet("v0.9.1: 系统性验证（23场景）+ bug修复"),
    bullet("v0.9.2: 通用性验证（3种流程）+ 关键路径修复"),
    bullet("v1.0: Prompt 引擎（实体驱动 + 信号检测 + 中文模糊匹配）"),
    bullet("v2.0: 图论架构重构 — 全局 DAG + CPM + 单文件自包含 + 19场景闭环验证"),
    bullet("v2.1: 度信流程跨阶段依赖（29条，总工期 24→132天）"),
    bullet("v2.2: 死代码清理（-526行）"),

    h1("8. 下一步"),
    bullet("v2.3: 子任务跨边界依赖 + 更多模板（PCB Layout, FPGA）"),
    bullet("v3.0: Skills 版本 — LLM 意图理解替代关键词匹配，打包为 OpenClaw Skill"),
    bullet("远期: pip install 分发 / 多人协作 / Web UI"),

    divider(),
    p("GitHub: https://github.com/joyhpc/project-tracker (私有)"),
    p("代码量: 2635行 Python | 17模块 | 24命令"),
    p("最后更新: 2026-02-19"),
]
notion_append(batch5)
print("✅ 第5批写入完成")
print("\n🎉 Notion 文档更新完成！")

# AGENT_TASKS.md — 三大增强模块隔离并行开发契约

> 由主控架构师签发 | 2026-03-09

---

## 全局红线

1. **零依赖原则**: 仅允许 Python 3.10+ 标准库 + PyYAML，禁止引入任何第三方包
2. **只读消费核心层**: 所有新模块只能通过 `tracker.core` / `tracker.project_model` / `tracker.project_query` / `tracker.engine` 的公开函数读取数据，**绝对禁止**直接修改 YAML 文件或 `project["nodes"]`
3. **物理隔离**: 三个模块各自在独立子目录中开发，Worker 间不得交叉修改同一文件
4. **Hook 注入点**: 唯一允许触碰 `core.py` 的模块是 Task A (Webhook)，且仅限在 `mutate()` 上下文管理器的 `_save()` 调用后添加通知钩子

---

## Task A: Webhook 通知层 (Worker-Webhook)

| 属性 | 值 |
|------|-----|
| **分支** | `feat/webhook-notify` |
| **负责目录** | `tracker/notify/` (新建) |
| **允许修改的已有文件** | `tracker/core.py` (仅限 `mutate()` 函数内添加 hook 调用，不超过 5 行) |
| **禁止触碰** | 其他所有现有文件 |

### 职责
- 监听 `mutate()` 中的状态变更事件（start/done/block/add_node/remove_node）
- 通过 `urllib.request` (标准库) 向外部 Webhook URL 发送 JSON 通知
- 支持钉钉、飞书、企业微信三种 Webhook 格式
- 配置文件: `tracker/notify/config.yaml` (Webhook URL + 开关)
- 失败静默（通知失败不影响核心流程）

### 接口契约
```python
# tracker/notify/__init__.py
def fire_event(event_type: str, payload: dict) -> None:
    """无侵入式事件通知，失败静默"""
```

---

## Task B: Web 看板 (Worker-WebUI)

| 属性 | 值 |
|------|-----|
| **分支** | `feat/web-dashboard` |
| **负责目录** | `tracker/web/` (新建) |
| **允许修改的已有文件** | 无 (零修改现有代码) |
| **禁止触碰** | `tracker/` 下的所有现有 .py 文件 |

### 职责
- 基于 `http.server` (标准库) 提供只读 Web 看板
- 读取 `projects/*.yaml` 和 `.pt_history/` 渲染项目状态
- 通过 `tracker.core._load()` / `tracker.engine.compute_cpm()` 获取数据
- 输出静态 HTML (内嵌 CSS/JS，无需前端构建工具)
- 新增 CLI 入口: `pt web [--port PORT]`

### 接口契约
```python
# tracker/web/server.py
def start_server(host: str = "localhost", port: int = 8080) -> None:
    """启动只读 Web 看板服务"""

# tracker/web/render.py
def render_dashboard(project: dict) -> str:
    """将项目数据渲染为完整 HTML 页面"""
```

### 红线
- **绝对只读**: 任何 HTTP 请求都不得触发 YAML 写入
- 不得导入 `project_mutation`

---

## Task C: 数据分析与报表 (Worker-DataX)

| 属性 | 值 |
|------|-----|
| **分支** | `feat/data-analysis` |
| **负责目录** | `tracker/datax/` (新建) |
| **允许修改的已有文件** | `tracker/commands/analysis.py` (仅限追加新子命令注册) |
| **禁止触碰** | `core.py`, `engine.py`, `project_mutation.py` 等核心文件 |

### 职责
- 基于 `engine.compute_cpm()` 的 CPM 数据进行统计分析
- 计算各阶段耗时统计（平均/P50/P90/最大）
- 导出 Mermaid Gantt 图语法（可粘贴到 Markdown 渲染）
- 导出 Mermaid 依赖关系图
- 新增 CLI 子命令: `pt analysis gantt`, `pt analysis stats`, `pt analysis deps`

### 接口契约
```python
# tracker/datax/stats.py
def compute_phase_stats(project: dict) -> dict:
    """统计各阶段耗时"""

# tracker/datax/gantt.py
def export_gantt_mermaid(project: dict) -> str:
    """导出 Mermaid Gantt 图"""

# tracker/datax/deps_graph.py
def export_deps_mermaid(project: dict) -> str:
    """导出 Mermaid 依赖关系图"""
```

---

## 分支与合并策略

```
main ─────────────────────────────────────────► main (合并后)
  ├── feat/webhook-notify   (Worker A worktree)
  ├── feat/web-dashboard    (Worker B worktree)
  └── feat/data-analysis    (Worker C worktree)
```

- 各 Worker 在独立 worktree 中工作
- 完成后由主控架构师逐一审查 `git diff main..feat/xxx`
- 审查通过后合入 main，按 A → B → C 顺序合并以最小化冲突

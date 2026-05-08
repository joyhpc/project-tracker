# Project-Tracker 架构优化 - 可执行方案

## 📋 第一阶段: 快速清债 (1-2周)

### 任务 1.1: 删除 conflict.py 模块
```bash
# 1. 验证无外部依赖
git grep "from.*conflict import" -- '*.py'
git grep "import.*conflict" -- '*.py'

# 2. 检查测试覆盖
ls -la tests/*conflict* 2>/dev/null || echo "无测试文件"

# 3. 检查命令是否被使用
git log --oneline --grep="conflict" | head -5

# 4. 删除文件
rm /home/ubuntu/project-tracker/tracker/conflict.py
rm /home/ubuntu/project-tracker/tracker/commands/conflict_cmd.py

# 5. 从 cli.py 移除导入
# 编辑 cli.py，删除:
#   from .commands.conflict_cmd import cmd_conflict
#   p_conflict = sub.add_parser(...)
#   p_conflict.set_defaults(func=cmd_conflict)

# 6. 回归测试
pytest tests/ -q
```

### 任务 1.2: 降级 guide.py
```bash
# 1. 备份到文档
cp /home/ubuntu/project-tracker/tracker/guide.py \
   /home/ubuntu/project-tracker/docs/legacy_guide.py

# 2. 在 README 中添加初始化检查清单
# 编辑 README.md，添加:
# ```
# ## 项目初始化检查清单
# 使用 `pt init` 创建项目后，建议回答以下问题:
# - [ ] 产品定位与目标市场
# - [ ] 关键技术风险点
# - [ ] 资源与时间约束
# - [ ] 成功标准与验收指标
# ```

# 3. 简化 guide_cmd.py，改为仅展示检查清单
# 编辑 guide_cmd.py:
# def cmd_guide(args):
#     print(CHECKLIST)

# 4. 删除 flows/guide_questions.yaml（或保留为参考）
```

### 任务 1.3: 合并命令层冗余
```bash
# 1. 检查 risk_cmd.py, notify_cmd.py 内容
head -20 /home/ubuntu/project-tracker/tracker/commands/risk_cmd.py
head -20 /home/ubuntu/project-tracker/tracker/commands/notify_cmd.py

# 2. 将 risk 功能整合到 analysis.py
# 编辑 analysis.py，添加:
# def cmd_risk(args):
#     from ..risk import assess_project_risk
#     # ... 实现

# 3. 从 cli.py 移除 risk_cmd, notify_cmd 导入
# 更新为:
# from .commands.analysis import cmd_risk, cmd_notify, ...

# 4. 删除文件
rm /home/ubuntu/project-tracker/tracker/commands/risk_cmd.py
rm /home/ubuntu/project-tracker/tracker/commands/notify_cmd.py

# 5. 回归测试
pytest tests/ -q
```

**预期收益**: 删除 ~400 行代码，简化导航

---

## 🏗️ 第二阶段: 核心重构 (2-3周)

### 任务 2.1: 拆分 core.py

#### Step 1: 提取 core_io.py (YAML I/O)
```python
# tracker/core_io.py (~200行)
"""
数据 I/O 层 — YAML 文件读写
"""
from pathlib import Path
import yaml

PROJECTS_DIR = Path(__file__).parent.parent / "projects"
CONFIG_FILE = PROJECTS_DIR / ".active"

def _project_file(project_id: str) -> Path:
    return PROJECTS_DIR / f"{project_id}.yaml"

def load_project(project_id: str) -> dict | None:
    """从文件加载项目 YAML"""
    fpath = _project_file(project_id)
    if not fpath.exists():
        return None
    with open(fpath, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}

def save_project(project: dict) -> None:
    """保存项目 YAML（带备份）"""
    project_id = project.get('id')
    if not project_id:
        raise ValueError('project 缺少 id')

    fpath = _project_file(project_id)
    backup_path = fpath.with_suffix('.yaml.backup')

    # 备份
    if fpath.exists():
        fpath.rename(backup_path)

    # 保存
    with open(fpath, 'w', encoding='utf-8') as f:
        yaml.dump(project, f, allow_unicode=True, sort_keys=False)

def list_all_projects() -> list[dict]:
    """列出所有项目"""
    projects = []
    for f in PROJECTS_DIR.glob('*.yaml'):
        if f.name.startswith('.'):
            continue
        try:
            p = yaml.safe_load(f.read_text(encoding='utf-8'))
            if isinstance(p, dict) and 'id' in p:
                projects.append(p)
        except Exception:
            continue
    return projects

def get_active_project_id() -> str | None:
    """读取活跃项目 ID"""
    if CONFIG_FILE.exists():
        return CONFIG_FILE.read_text(encoding='utf-8').strip()
    return None

def set_active_project_id(project_id: str) -> None:
    """设置活跃项目 ID"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(project_id, encoding='utf-8')
```

#### Step 2: 提取 core_migration.py (版本迁移)
```python
# tracker/core_migration.py (~300行)
"""
数据迁移层 — Schema 版本管理与演进
"""
import copy
from .project_constants import PROJECT_SCHEMA_VERSION

def migrate_project_data(project: dict | None) -> tuple[dict | None, bool]:
    """将历史项目数据迁移到当前 schema

    Returns:
        (迁移后的project, 是否有变动)
    """
    if not isinstance(project, dict):
        return project, False

    changed = False
    migrated = copy.deepcopy(project)

    if migrated.get("schema_version") != PROJECT_SCHEMA_VERSION:
        migrated["schema_version"] = PROJECT_SCHEMA_VERSION
        changed = True

    # ... (其他迁移逻辑)
    return migrated, changed
```

#### Step 3: 重构 core.py
```python
# tracker/core.py (~400行，重构后)
"""
项目中枢 — 持久化 Façade
"""
from . import core_io
from . import core_migration
from . import core_api

# 公开 API
def load_project(project_id: str) -> dict | None:
    """加载项目"""
    p = core_io.load_project(project_id)
    if p:
        p, _ = core_migration.migrate_project_data(p)
    return p

def save_project(project: dict) -> None:
    """保存项目"""
    core_io.save_project(project)
    # 后续钩子
    from . import post_save
    post_save.run_post_save_hooks(project, event="save")

def list_projects() -> list[dict]:
    """列出所有项目"""
    return core_io.list_all_projects()

def get_active_project_id() -> str | None:
    """获取活跃项目 ID"""
    return core_io.get_active_project_id()

def set_active_project_id(project_id: str) -> None:
    """设置活跃项目 ID"""
    core_io.set_active_project_id(project_id)

# Internal API (保留兼容性)
# 这些前缀为 _ 的函数保留在此文件中，用于内部调用
_project_as_flow = core_api._project_as_flow
_get_task_status = core_api._get_task_status
# ... 其他
```

### 任务 2.2: 建立 command_base.py
```python
# tracker/commands/base.py (~100行)
"""
命令基类 — 统一参数验证与异常处理
"""
from typing import Optional
from .. import core

class CommandContext:
    """命令执行上下文"""

    def __init__(self, args):
        self.args = args
        # 获取项目 ID（从参数或活跃项目）
        self.project_id = getattr(args, 'project_id', None) \
                         or getattr(args, 'id', None) \
                         or core.get_active_project_id()
        if not self.project_id:
            raise ValueError("未指定项目，请用 pt switch <id> 设置活跃项目")

        # 加载项目
        self.project = core.load_project(self.project_id)
        if not self.project:
            raise ValueError(f"项目不存在: {self.project_id}")

    def save(self):
        """保存项目"""
        core.save_project(self.project)

def require_project(func):
    """装饰器：自动初始化 CommandContext"""
    def wrapper(args):
        try:
            ctx = CommandContext(args)
            return func(args, ctx)
        except ValueError as e:
            print(f"❌ {e}", file=sys.stderr)
            sys.exit(1)
    return wrapper
```

#### 示例：简化后的命令
```python
# tracker/commands/tasks.py
from .base import require_project

@require_project
def cmd_tasks(args, ctx):
    """查看任务列表"""
    flow = ctx.project.get('nodes', [])
    phase = getattr(args, 'phase', None)

    tasks = [
        t for t in flow
        if not phase or t.get('phase') == phase
    ]

    for t in tasks:
        print(f"  {t['id']:20s} {t.get('name', 'Untitled')}")
```

### 任务 2.3: 提取 graph_utils.py
```python
# tracker/graph_utils.py (~150行)
"""
共享 DAG 工具库
"""
from typing import Dict, List, Set

def build_graph(flow: dict) -> dict:
    """构建全局 DAG (从 engine.py 提取)"""
    # ... 实现
    pass

def topo_sort(graph: dict) -> List[str]:
    """拓扑排序 (从 engine.py 提取)"""
    # ... 实现
    pass

def count_downstream(node_id: str, rdeps: Dict) -> int:
    """计算下游节点数"""
    # ... 实现
    pass
```

然后更新导入：
```python
# engine.py
from .graph_utils import build_graph, topo_sort, count_downstream

# project_map.py
from .graph_utils import build_graph

# risk.py
from .graph_utils import build_graph, count_downstream
```

**预期收益**:
- core.py 从 1865 → ~400 行
- 新增 3 个单一职责文件
- 改动影响范围↓，便于独立测试

---

## 🧪 第三阶段: 测试强化 (2-3周)

### 任务 3.1: 补充 knowledge.py 单测
```python
# tests/test_knowledge.py

import pytest
from tracker.knowledge import tokenize, parse_markdown, BM25

class TestTokenize:
    def test_hardware_components(self):
        """测试硬件术语分词"""
        text = "U4/TPS56C215 的 pin 脚配置"
        tokens = tokenize(text)
        assert "u4/tps56c215" in tokens
        assert "u4" in tokens
        assert "tps56c215" in tokens

    def test_units(self):
        """测试带单位规格分词"""
        text = "3.5Gbps 的 MIPI 接口, 0.1uF 电容"
        tokens = tokenize(text)
        assert "3.5gbps" in tokens
        assert "0.1uf" in tokens

class TestBM25:
    def test_relevance_ranking(self):
        """测试 BM25 相关性排序"""
        docs = [
            ("doc1", "MIPI CSI-2 接口验证"),
            ("doc2", "PCB 走线设计"),
            ("doc3", "MIPI DSI 显示接口"),
        ]
        bm25 = BM25([d[1] for d in docs])

        query = "MIPI 接口"
        scores = bm25.get_scores(query)

        # doc1 和 doc3 应该排在 doc2 前
        assert scores[0] > scores[1]
        assert scores[2] > scores[1]
```

### 任务 3.2: 补充 engine.py CPM 单测
```python
# tests/test_engine_cpm.py

import pytest
from tracker.engine import compute_cpm, build_graph

class TestCPM:
    @pytest.fixture
    def simple_flow(self):
        """简单的线性项目 DAG"""
        return {
            "nodes": [
                {"id": "a", "name": "Task A", "depends": [], "days": 3},
                {"id": "b", "name": "Task B", "depends": ["a"], "days": 5},
                {"id": "c", "name": "Task C", "depends": ["b"], "days": 2},
            ]
        }

    def test_project_duration(self, simple_flow):
        """测试项目总工期计算"""
        graph = build_graph(simple_flow)
        task_status = {"a": "pending", "b": "pending", "c": "pending"}
        cpm = compute_cpm(simple_flow, task_status)

        # 线性 DAG: 3 + 5 + 2 = 10 天
        assert cpm["project_duration"] == 10

    def test_critical_path(self, simple_flow):
        """测试关键路径识别"""
        graph = build_graph(simple_flow)
        task_status = {"a": "pending", "b": "pending", "c": "pending"}
        cpm = compute_cpm(simple_flow, task_status)

        # 所有任务都在关键路径上
        assert set(cpm["critical_path"]) == {"a", "b", "c"}

    def test_slack_calculation(self, simple_flow):
        """测试松弛时间计算"""
        graph = build_graph(simple_flow)
        task_status = {"a": "pending", "b": "pending", "c": "pending"}
        cpm = compute_cpm(simple_flow, task_status)

        # 关键路径上的任务 slack = 0
        for node_id in cpm["critical_path"]:
            assert cpm["nodes"][node_id]["slack"] == 0
```

### 任务 3.3: 建立测试 fixtures
```bash
# 创建目录
mkdir -p /home/ubuntu/project-tracker/tests/fixtures

# 创建标准项目模板
cat > /home/ubuntu/project-tracker/tests/fixtures/sample_project.yaml << 'YAML'
id: sample
name: 示例项目
schema_version: 2
nodes:
  - id: req
    name: 需求评审
    status: done
    depends: []
    phase: REQ
    days: 3
  - id: design
    name: 总体设计
    status: in_progress
    depends: [req]
    phase: FEAS
    days: 10
  - id: layout
    name: PCB 布局
    status: pending
    depends: [design]
    phase: DETAIL
    days: 15
    owner: Alice
YAML

# 更新 conftest.py
cat >> /home/ubuntu/project-tracker/tests/conftest.py << 'PYTHON'

import yaml
from pathlib import Path

@pytest.fixture
def sample_project():
    """加载标准示例项目"""
    fixture_file = Path(__file__).parent / "fixtures" / "sample_project.yaml"
    return yaml.safe_load(fixture_file.read_text(encoding="utf-8"))
PYTHON
```

**预期收益**: 覆盖率 40% → 70%+

---

## ✅ 验证清单

### 第一阶段验证
```bash
# 1. 代码质量
pytest tests/ -q --tb=short

# 2. 静态分析
flake8 tracker/ --max-line-length=120 --exclude=__pycache__

# 3. 代码行数统计
wc -l tracker/*.py | tail -1
# 预期: 从 ~7700 → ~7300 行

# 4. 命令文件数
ls tracker/commands/*.py | wc -l
# 预期: 从 27 → 24 个文件
```

### 第二阶段验证
```bash
# 1. core.py 行数
wc -l tracker/core.py
# 预期: 从 1865 → ~400 行

# 2. 循环依赖检查
pydeps tracker/ --show-cycles
# 预期: 0 个循环

# 3. 导入一致性
python3 -c "from tracker import core; print('✅ core 导入正常')"
python3 -c "from tracker.commands import *; print('✅ 所有命令导入正常')"
```

### 第三阶段验证
```bash
# 1. 覆盖率
pytest tests/ --cov=tracker --cov-report=term-missing
# 预期: > 70%

# 2. 特定模块覆盖
pytest tests/test_knowledge.py tests/test_engine_cpm.py -v
```

---

## 📊 预期时间与收益

| 阶段 | 工作量 | 代码删除 | 代码重构 | 覆盖率提升 | 关键指标改善 |
|------|--------|--------|--------|----------|------------|
| 第一 | 1-2 周 | 400 行 | - | - | 命令数 -3 |
| 第二 | 2-3 周 | - | 2000 行 | - | 最大文件 -75% |
| 第三 | 2-3 周 | - | +500 行 | 40%→70% | 风险回归 ↓ |
| **总计** | **6-8 周** | **400 行** | **2000 行** | **+30%** | **健康度: 6.8→8.2** |

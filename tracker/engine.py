"""智能推进引擎 v2 — 全局 DAG + CPM 关键路径

核心变更：
- 从阶段内分析 → 全局 DAG 分析
- 从步数关键路径 → 基于工时的 CPM
- 新增 Slack（松弛时间）计算
"""

DEFAULT_DAYS = 3  # 未估算工时的 fallback

# 按任务名称关键词给出更合理的默认工时估算
# 避免所有未估算任务统一 3 天导致 CPM 失真
_SMART_DEFAULTS = {
    # 硬件设计
    "原理图": 10, "schematic": 10,
    "pcb布局": 15, "pcb_layout": 15, "layout": 15, "pcb走线": 10, "pcb_routing": 10,
    "评审": 2, "review": 2, "审核": 2,
    # 制样
    "打样": 7, "pcb_sample": 7, "pcb_fab": 7, "smt": 5, "贴片": 5, "stencil": 2, "钢网": 2,
    # 固件
    "fpga": 30, "mcu": 20, "固件": 20,
    # 软件
    "sdk": 25, "驱动": 20, "app": 25,
    # 测试
    "联调": 10, "integration": 10, "测试": 10, "test": 10,
    "调试": 7, "bringup": 7, "debug": 7,
    # 试产
    "试产": 5, "trial": 5,
    # 其他
    "验证": 5, "verify": 5, "选型": 3, "估算": 2, "封装": 3,
}


# ── DAG 构建 ──────────────────────────────────────────

def build_graph(flow: dict) -> dict:
    """构建全局 DAG

    Returns:
        {
            "nodes": {id: node_dict},
            "deps": {id: [dep_ids]},       # 前驱
            "rdeps": {id: [successor_ids]}, # 后继
            "sources": [ids],               # 无前驱的节点
            "sinks": [ids],                 # 无后继的节点
        }
    """
    nodes = {n["id"]: n for n in flow.get("nodes", [])
             if n.get("status") != "expanded"}  # 跳过已展开的父节点
    deps = {}
    rdeps = {nid: [] for nid in nodes}
    missing_deps = {}

    for nid, node in nodes.items():
        dep_list = list(node.get("depends", []))
        deps[nid] = dep_list
        for d in dep_list:
            if d in nodes:
                rdeps[d].append(nid)
            else:
                missing_deps.setdefault(nid, []).append(d)

    sources = [nid for nid in nodes if not deps.get(nid)]
    sinks = [nid for nid in nodes if not rdeps.get(nid)]

    return {
        "nodes": nodes, "deps": deps, "rdeps": rdeps,
        "sources": sources, "sinks": sinks,
        "missing_deps": missing_deps,
    }


def topo_sort(graph: dict) -> list[str]:
    """拓扑排序（Kahn 算法），同时检测环"""
    if graph.get("missing_deps"):
        node_id, deps = next(iter(graph["missing_deps"].items()))
        raise ValueError(f"检测到悬空依赖: [{node_id}] → {', '.join(deps)}")

    in_degree = {nid: len(graph["deps"].get(nid, [])) for nid in graph["nodes"]}
    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    order = []

    while queue:
        # 稳定排序：同层级按 ID 排
        queue.sort()
        nid = queue.pop(0)
        order.append(nid)
        for succ in graph["rdeps"].get(nid, []):
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    if len(order) != len(graph["nodes"]):
        visited = set(order)
        cycle_nodes = [nid for nid in graph["nodes"] if nid not in visited]
        raise ValueError(f"检测到循环依赖: {', '.join(cycle_nodes[:5])}")

    return order


def stable_node_order(graph: dict) -> list[str]:
    """用于展示/分类的稳定顺序；容忍 missing deps。"""
    if not graph.get("missing_deps"):
        return topo_sort(graph)

    in_degree = {
        nid: sum(1 for dep in graph["deps"].get(nid, []) if dep in graph["nodes"])
        for nid in graph["nodes"]
    }
    queue = sorted([nid for nid, degree in in_degree.items() if degree == 0])
    order = []

    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for succ in sorted(graph["rdeps"].get(nid, [])):
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)
                queue.sort()

    for nid in sorted(graph["nodes"]):
        if nid not in order:
            order.append(nid)
    return order


# ── CPM 关键路径 ──────────────────────────────────────

def node_days(node: dict, custom_estimates: dict = None) -> float:
    """获取节点工时（天）

    优先级：custom_estimates > node.days > 智能默认 > DEFAULT_DAYS
    """
    if custom_estimates and node["id"] in custom_estimates:
        return custom_estimates[node["id"]]
    if node.get("type") == "milestone":
        return 0
    if "days" in node:
        return node["days"]

    # 智能默认：按任务名/ID 关键词匹配
    name_lower = (node.get("name", "") + " " + node.get("id", "")).lower()
    for keyword, days in _SMART_DEFAULTS.items():
        if keyword in name_lower:
            return days

    return DEFAULT_DAYS


def compute_cpm(flow: dict, task_status: dict = None,
                custom_estimates: dict = None) -> dict:
    """CPM 关键路径计算

    Returns:
        {
            "nodes": {id: {es, ef, ls, lf, slack, critical, days}},
            "critical_path": [ids],      # 关键路径节点（按拓扑序）
            "total_days": float,         # 项目总工期
            "topo_order": [ids],
        }
    """
    if task_status is None:
        task_status = {}
    if custom_estimates is None:
        custom_estimates = {}

    graph = build_graph(flow)
    topo = topo_sort(graph)

    result = {}
    for nid in graph["nodes"]:
        node = graph["nodes"][nid]
        status = task_status.get(nid, {}).get("status", "pending")
        days = 0 if status in ("done", "skipped") else node_days(node, custom_estimates)
        result[nid] = {"days": days, "es": 0, "ef": 0, "ls": 0, "lf": 0,
                       "slack": 0, "critical": False}

    # Step 1: 前向推导 (Forward Pass)
    for nid in topo:
        r = result[nid]
        dep_ids = graph["deps"].get(nid, [])
        if dep_ids:
            r["es"] = max(result[d]["ef"] for d in dep_ids)
        else:
            r["es"] = 0
        r["ef"] = r["es"] + r["days"]

    # 项目总工期
    total_days = max(r["ef"] for r in result.values()) if result else 0

    # Step 2: 反向推导 (Backward Pass)
    for nid in reversed(topo):
        r = result[nid]
        succ_ids = graph["rdeps"].get(nid, [])
        if succ_ids:
            r["lf"] = min(result[s]["ls"] for s in succ_ids)
        else:
            r["lf"] = total_days
        r["ls"] = r["lf"] - r["days"]

    # Step 3: 计算 Slack，标记关键路径
    for nid, r in result.items():
        r["slack"] = r["ls"] - r["es"]
        r["critical"] = abs(r["slack"]) < 0.001  # float 精度

    # 提取关键路径（按拓扑序）
    critical_path = [nid for nid in topo if result[nid]["critical"]
                     and result[nid]["days"] > 0]  # 排除已完成的

    return {
        "nodes": result,
        "critical_path": critical_path,
        "total_days": total_days,
        "topo_order": topo,
    }


# ── 任务分类 ──────────────────────────────────────────

def classify_tasks(flow: dict, task_status: dict,
                   phase_id: str = None) -> dict:
    """分类任务状态

    Args:
        flow: 流程定义
        task_status: 项目任务状态
        phase_id: 可选，只看某个阶段

    Returns:
        {ready, in_progress, blocked, waiting, done}
    """
    graph = build_graph(flow)
    nodes = graph["nodes"]

    topo_order = stable_node_order(graph)
    if phase_id:
        node_ids = [nid for nid in topo_order if nodes[nid].get("phase") == phase_id]
    else:
        node_ids = list(topo_order)

    result = {"ready": [], "in_progress": [], "blocked": [], "waiting": [], "done": []}

    for nid in node_ids:
        node = nodes[nid]
        s = task_status.get(nid, {}).get("status", "pending")

        if s in ("done", "skipped"):
            result["done"].append(node)
        elif s == "blocked":
            result["blocked"].append(node)
        elif s == "in_progress":
            result["in_progress"].append(node)
        else:
            # 检查依赖是否全部完成（全局依赖，不限阶段）
            dep_ids = graph["deps"].get(nid, [])
            all_done = all(
                task_status.get(d, {}).get("status") == "done"
                for d in dep_ids
            )
            if all_done:
                result["ready"].append(node)
            else:
                waiting_for = [d for d in dep_ids
                              if task_status.get(d, {}).get("status") != "done"]
                node = dict(node)  # copy
                node["_waiting_for"] = waiting_for
                result["waiting"].append(node)

    return result


# ── 优先级 ──────────────────────────────────────────

def count_downstream(nid: str, rdeps: dict, visited: set = None) -> int:
    """递归计算下游任务总数"""
    if visited is None:
        visited = set()
    count = 0
    for child in rdeps.get(nid, []):
        if child not in visited:
            visited.add(child)
            count += 1 + count_downstream(child, rdeps, visited)
    return count


def compute_priority(node: dict, graph: dict, cpm_result: dict) -> int:
    """计算任务优先级（结合 CPM）"""
    score = 0
    nid = node["id"]
    cpm_node = cpm_result["nodes"].get(nid, {})

    # 关键路径上的任务最高优先
    if cpm_node.get("critical"):
        score += 200

    # Slack 越小越紧急
    slack = cpm_node.get("slack", 999)
    if slack <= 3:
        score += 100
    elif slack <= 7:
        score += 50

    # 下游任务越多越重要
    score += count_downstream(nid, graph["rdeps"]) * 10

    # 有准入条件的需要提前关注
    if node.get("gate"):
        score += 5
    if node.get("deliverables"):
        score += 3
    if node.get("critical"):
        score += 20

    return score


# ── 阻塞分析 ──────────────────────────────────────────

def analyze_blockers(flow: dict, task_status: dict, blockers: list) -> list:
    """分析阻塞影响"""
    graph = build_graph(flow)
    active = [b for b in blockers if not b.get("resolved")]
    result = []

    for b in active:
        tid = b["task_id"]
        downstream = count_downstream(tid, graph["rdeps"])
        direct = [graph["nodes"][s]["name"]
                  for s in graph["rdeps"].get(tid, [])
                  if s in graph["nodes"]]
        result.append({
            "task_id": tid,
            "task_name": graph["nodes"].get(tid, {}).get("name", tid),
            "reason": b["reason"],
            "downstream_count": downstream,
            "direct_downstream": direct[:5],
        })

    return result


def find_alternatives(flow: dict, task_status: dict, blockers: list) -> list:
    """找到不受阻塞影响的可执行任务"""
    classified = classify_tasks(flow, task_status)
    blocked_ids = {b["task_id"] for b in blockers if not b.get("resolved")}
    return [t for t in classified["ready"] if t["id"] not in blocked_ids]


# ── 综合分析 ──────────────────────────────────────────

def analyze(flow: dict, task_status: dict, blockers: list = None,
            phase_id: str = None, custom_estimates: dict = None) -> dict:
    """综合分析：返回结构化数据"""
    if blockers is None:
        blockers = []
    if custom_estimates is None:
        custom_estimates = {}

    graph = build_graph(flow)
    cpm = compute_cpm(flow, task_status, custom_estimates)
    classified = classify_tasks(flow, task_status, phase_id)

    # 按优先级排序 ready 任务
    for task in classified["ready"]:
        task["_priority"] = compute_priority(task, graph, cpm)
    classified["ready"].sort(key=lambda t: t.get("_priority", 0), reverse=True)

    # 阻塞分析
    blocker_analysis = analyze_blockers(flow, task_status, blockers)
    alternatives = find_alternatives(flow, task_status, blockers)

    # 并行推荐：按 owner 分组
    parallel = {}
    for t in classified["ready"]:
        owner = t.get("owner", "未分配")
        parallel.setdefault(owner, []).append(t)

    return {
        "classified": classified,
        "cpm": cpm,
        "blockers": blocker_analysis,
        "alternatives": alternatives,
        "parallel": parallel,
        "graph": graph,
    }

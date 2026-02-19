"""风险评估引擎 v2 — 基于全局 DAG + CPM

多维度风险评分:
1. Slack — 松弛时间越小，风险越高（关键路径 slack=0 最高）
2. 下游影响 — 下游任务越多，延误影响越大
3. Gate 准入 — 有审批/准入条件的任务不确定性高
4. 资源瓶颈 — 某个 owner 负载过重
5. 长周期 — 预估工时长的任务风险高
6. 外部依赖 — 涉及采购/送样/认证等外部环节
"""
from .engine import build_graph, compute_cpm, count_downstream

EXTERNAL_KEYWORDS = ["申请", "审批", "送样", "制样", "采购", "知识产权", "新品承认", "认证", "EQ"]


def assess_task_risk(node: dict, graph: dict, cpm_result: dict,
                     owner_load: dict) -> dict:
    """评估单个任务的风险"""
    nid = node["id"]
    name = node.get("name", "")
    factors = []
    score = 0
    cpm_node = cpm_result["nodes"].get(nid, {})

    # 1. Slack（最重要的指标）
    slack = cpm_node.get("slack", 999)
    if slack == 0:
        score += 30
        factors.append("关键路径上 (slack=0)")
    elif slack <= 3:
        score += 20
        factors.append(f"近关键路径 (slack={slack:.0f}天)")
    elif slack <= 7:
        score += 10
        factors.append(f"缓冲有限 (slack={slack:.0f}天)")

    # 2. 下游影响
    downstream = count_downstream(nid, graph["rdeps"])
    if downstream >= 5:
        score += 25
        factors.append(f"阻塞下游 {downstream} 个任务")
    elif downstream >= 3:
        score += 12
        factors.append(f"阻塞下游 {downstream} 个任务")

    # 3. Gate 准入
    if node.get("gate"):
        score += 15
        factors.append(f"准入: {node['gate']}")

    # 4. Critical 标记
    if node.get("critical"):
        score += 15
        factors.append("关键节点")

    # 5. 资源瓶颈
    owner = node.get("owner", "")
    for o in owner.replace("/", ",").replace("、", ",").split(","):
        o = o.strip()
        if o and owner_load.get(o, 0) >= 8:
            score += 10
            factors.append(f"{o} 负载过重 ({owner_load[o]} 个任务)")
            break

    # 6. 长周期
    days = cpm_node.get("days", 3)
    if days >= 14:
        score += 15
        factors.append(f"预估 {days:.0f} 天")
    elif days >= 7:
        score += 5

    # 7. 外部依赖
    for kw in EXTERNAL_KEYWORDS:
        if kw in name:
            score += 10
            factors.append("涉及外部环节")
            break

    level = "🔴 高" if score >= 40 else "🟡 中" if score >= 20 else "🟢 低"

    return {
        "task_id": nid,
        "name": name,
        "score": score,
        "level": level,
        "factors": factors,
        "owner": owner,
        "slack": slack,
        "days": days,
    }


def assess_project_risk(flow: dict, task_status: dict,
                        custom_estimates: dict = None) -> dict:
    """评估整个项目的风险"""
    if custom_estimates is None:
        custom_estimates = {}

    graph = build_graph(flow)
    cpm = compute_cpm(flow, task_status, custom_estimates)

    # 计算 owner 负载
    owner_load = {}
    for nid, node in graph["nodes"].items():
        if task_status.get(nid, {}).get("status") == "done":
            continue
        for o in node.get("owner", "").replace("/", ",").replace("、", ",").split(","):
            o = o.strip()
            if o:
                owner_load[o] = owner_load.get(o, 0) + 1

    # 评估每个未完成任务
    all_risks = []
    for nid, node in graph["nodes"].items():
        if task_status.get(nid, {}).get("status") == "done":
            continue
        if node.get("type") == "milestone":
            continue
        r = assess_task_risk(node, graph, cpm, owner_load)
        all_risks.append(r)

    all_risks.sort(key=lambda x: x["score"], reverse=True)

    # 按阶段汇总
    phase_risks = {}
    for r in all_risks:
        node = graph["nodes"].get(r["task_id"], {})
        pid = node.get("phase", "未分类")
        if pid not in phase_risks:
            phase_risks[pid] = {"high": 0, "medium": 0, "risks": []}
        if r["score"] >= 40:
            phase_risks[pid]["high"] += 1
        elif r["score"] >= 20:
            phase_risks[pid]["medium"] += 1
        phase_risks[pid]["risks"].append(r)

    bottlenecks = sorted(owner_load.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "top_risks": all_risks[:10],
        "phase_risks": phase_risks,
        "bottlenecks": bottlenecks,
        "total_high": sum(pr["high"] for pr in phase_risks.values()),
        "total_medium": sum(pr["medium"] for pr in phase_risks.values()),
        "cpm": cpm,
    }


def format_risk_report(result: dict) -> str:
    """格式化风险报告"""
    lines = []

    lines.append(f"🔴 高风险: {result['total_high']} 个  🟡 中风险: {result['total_medium']} 个")
    lines.append("")

    # Top 10 风险
    lines.append("📊 风险排行 (Top 10):\n")
    for i, r in enumerate(result["top_risks"], 1):
        lines.append(f"  {i}. {r['level']} [{r['task_id']}] {r['name']}  (分数: {r['score']})")
        if r["factors"]:
            lines.append(f"     原因: {'; '.join(r['factors'])}")
    lines.append("")

    # 资源瓶颈
    if result["bottlenecks"]:
        lines.append("👥 资源瓶颈:\n")
        for owner, count in result["bottlenecks"]:
            bar = "█" * min(count, 20)
            lines.append(f"  {owner:16s} {bar} {count}个任务")
    lines.append("")

    return "\n".join(lines)

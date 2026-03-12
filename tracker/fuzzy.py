"""fuzzy — 模糊匹配 + 自然语言意图解析

让用户可以用自然语言描述项目变动，pt 自动推断意图和目标节点。

示例：
  pt update "FMC改线完了"          → pt done dcurx_fmc_ecn
  pt update "CPHY验证没过"         → pt block cphy_bridge_verify.verdict
  pt update "开始做CAMRX Pin分配"  → pt start camrx_pin_assign
  pt update "PMU的P0修了 加个备注"  → pt note on related node
  pt find "MIPI"                   → list matching nodes
"""

import re
from typing import List, Tuple, Optional


# ── 意图关键词 ──────────────────────────────────────

_INTENT_DONE = {
    "完了", "完成", "搞定", "做完", "结束", "通过", "关闭", "闭合",
    "ok了", "已完成", "已通过", "收工", "验证通过", "评审通过",
    "done", "finish", "pass", "close", "fixed", "修了", "改好",
}

_INTENT_START = {
    "开始", "启动", "着手", "动工", "开搞", "开干", "在做",
    "start", "begin", "进行中", "已开始",
}

_INTENT_BLOCK = {
    "卡住", "阻塞", "等待", "停了", "暂停", "没过", "不通过",
    "block", "stuck", "wait", "hold", "fail", "失败", "不行",
    "有问题", "出问题",
}

_INTENT_NOTE = {
    "备注", "记录", "记一下", "补充", "说明", "note",
}

_INTENT_ADD = {
    "新增", "加一个", "添加", "需要做", "还要做", "插入", "add",
}


def detect_intent(text: str) -> str:
    """从自然语言中检测意图。

    Returns: "done" | "start" | "block" | "note" | "add" | "unknown"
    """
    t = text.lower().strip()
    # 按优先级检测（block 优先于 done，因为"验证没过"应该是 block）
    for kw in _INTENT_BLOCK:
        if kw in t:
            return "block"
    for kw in _INTENT_DONE:
        if kw in t:
            return "done"
    for kw in _INTENT_START:
        if kw in t:
            return "start"
    for kw in _INTENT_ADD:
        if kw in t:
            return "add"
    for kw in _INTENT_NOTE:
        if kw in t:
            return "note"
    return "unknown"


def extract_block_reason(text: str) -> str:
    """从阻塞描述中提取原因。"""
    # 去掉意图关键词，剩下的就是原因
    reason = text
    for kw in _INTENT_BLOCK:
        reason = reason.replace(kw, "")
    reason = reason.strip(" ，,。.：:—-")
    return reason if reason else text


# ── 模糊匹配 ──────────────────────────────────────

def _tokenize_query(query: str) -> List[str]:
    """将查询拆分为匹配 token。"""
    q = query.lower()
    tokens = []
    # 英文+数字连字
    tokens.extend(re.findall(r'[a-z0-9_.-]+', q))
    # 中文字符
    cjk = re.findall(r'[\u4e00-\u9fa5]+', q)
    tokens.extend(cjk)
    return [t for t in tokens if len(t) > 0]


def _score_node(node: dict, query_tokens: List[str]) -> float:
    """计算节点与查询的匹配分数。"""
    name = (node.get("name", "") + " " + node.get("id", "")).lower()
    note = (node.get("note", "") or "").lower()
    owner = (node.get("owner", "") or "").lower()
    full_text = f"{name} {note} {owner}"

    score = 0.0
    for token in query_tokens:
        if token in node.get("id", "").lower():
            score += 3.0  # ID 精确匹配权重最高
        if token in name:
            score += 2.0  # 名称匹配
        if token in note:
            score += 0.5  # 备注匹配
        if token in owner:
            score += 0.5

    # 状态加权：进行中/可推进的节点优先
    status = node.get("status", "pending")
    if status == "in_progress":
        score *= 1.5
    elif status == "pending":
        score *= 1.2
    elif status == "done":
        score *= 0.3  # 已完成的节点降权

    return score


def fuzzy_match(project: dict, query: str, top_k: int = 5,
                exclude_done: bool = False) -> List[Tuple[dict, float]]:
    """模糊匹配项目节点。

    Args:
        project: 项目 dict
        query: 用户输入的自然语言查询
        top_k: 返回前 N 个匹配
        exclude_done: 是否排除已完成节点

    Returns:
        [(node, score), ...] 按分数降序
    """
    # 去掉意图关键词，只保留目标描述
    clean = query
    for kw_set in (_INTENT_DONE, _INTENT_START, _INTENT_BLOCK, _INTENT_NOTE, _INTENT_ADD):
        for kw in kw_set:
            clean = clean.replace(kw, " ")
    clean = clean.strip()
    if not clean:
        clean = query  # fallback to original if all keywords removed

    tokens = _tokenize_query(clean)
    if not tokens:
        return []

    nodes = project.get("nodes", [])
    scored = []
    for node in nodes:
        if exclude_done and node.get("status") in ("done", "skipped", "expanded"):
            continue
        s = _score_node(node, tokens)
        if s > 0:
            scored.append((node, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def resolve_node(project: dict, query: str) -> Optional[dict]:
    """尝试解析用户输入为单个节点。

    优先精确 ID 匹配，然后模糊匹配取最高分。
    """
    # 1) 精确 ID
    for n in project.get("nodes", []):
        if n["id"] == query:
            return n

    # 2) 模糊匹配
    matches = fuzzy_match(project, query, top_k=3)
    if matches and matches[0][1] >= 2.0:  # 至少要有一个 token 完整命中名称
        # 如果前两名分数差距大，直接返回；否则需要用户确认
        if len(matches) == 1 or matches[0][1] > matches[1][1] * 1.5:
            return matches[0][0]
    return None


def parse_update(project: dict, text: str) -> dict:
    """解析自然语言更新描述。

    Returns:
        {
            "intent": "done" | "start" | "block" | "note" | "add" | "unknown",
            "node": node_dict or None,
            "candidates": [(node, score), ...],  # 多个候选时
            "reason": str,  # block 原因
            "note": str,    # 备注内容
            "raw": str,     # 原始输入
            "confidence": "high" | "medium" | "low",
        }
    """
    intent = detect_intent(text)
    matches = fuzzy_match(project, text, top_k=5, exclude_done=(intent != "note"))

    node = None
    confidence = "low"

    if matches:
        top_score = matches[0][1]
        if top_score >= 4.0:
            confidence = "high"
            node = matches[0][0]
        elif top_score >= 2.0:
            if len(matches) == 1 or matches[0][1] > matches[1][1] * 1.5:
                confidence = "medium"
                node = matches[0][0]
            else:
                confidence = "low"  # 多个候选，需要确认
        # else: low

    reason = extract_block_reason(text) if intent == "block" else ""

    return {
        "intent": intent,
        "node": node,
        "candidates": matches,
        "reason": reason,
        "note": text,
        "raw": text,
        "confidence": confidence,
    }

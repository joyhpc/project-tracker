"""Pure project-model helpers shared across services."""

from __future__ import annotations


def _find_node_in_project(project: dict, node_id: str) -> dict | None:
    for node in project.get("nodes", []):
        if node.get("id") == node_id:
            return node
    return None



def _get_task_status(project: dict) -> dict:
    """构建 {node_id: {status, ...}} 映射，兼容引擎接口。"""
    result = {}
    for node in project.get("nodes", []):
        result[node["id"]] = {"status": node.get("status", "pending")}
        if node.get("started"):
            result[node["id"]]["started"] = node["started"]
        if node.get("completed"):
            result[node["id"]]["completed"] = node["completed"]
    return result



def _project_as_flow(project: dict) -> dict:
    """将项目数据转为引擎可用的 flow 格式。"""
    return {
        "phases": project.get("phases", []),
        "nodes": project.get("nodes", []),
    }



def _effective_nodes(project: dict) -> list[dict]:
    """获取参与统计/调度的有效节点（排除 expanded 父节点）。"""
    return [node for node in project.get("nodes", []) if node.get("status") != "expanded"]



def _progress_counts(project: dict) -> tuple[int, int]:
    """返回 (done_count, total) 统计口径。"""
    nodes = _effective_nodes(project)
    total = len(nodes)
    done_count = sum(1 for node in nodes if node.get("status") == "done")
    return done_count, total



def _undone_dependencies(project: dict, node: dict) -> list[str]:
    """返回尚未完成的依赖节点 ID 列表。"""
    undone = []
    for dep_id in node.get("depends", []):
        dep_node = _find_node_in_project(project, dep_id)
        if dep_node is None or dep_node.get("status") != "done":
            undone.append(dep_id)
    return undone

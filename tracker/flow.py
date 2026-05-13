"""流程定义加载 v2 — 扁平 DAG 模型"""
import yaml
from pathlib import Path


def _flow_dirs() -> list[Path]:
    """候选 flow 目录：优先使用打包到 tracker 内的资源。"""
    candidates = [
        Path(__file__).resolve().parent / "flows",
        Path(__file__).resolve().parent.parent / "flows",
    ]
    result = []
    seen = set()
    for path in candidates:
        if path.exists() and path not in seen:
            seen.add(path)
            result.append(path)
    return result


def load_flow(name: str = "duxin") -> dict:
    """加载流程定义，优先加载 v2 格式"""
    for flows_dir in _flow_dirs():
        v2_file = flows_dir / f"{name}_v2.yaml"
        if v2_file.exists():
            with open(v2_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)

        v1_file = flows_dir / f"{name}.yaml"
        if v1_file.exists():
            with open(v1_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            # 如果是旧格式（有 phases[].tasks），自动转换
            if data.get("phases") and data["phases"][0].get("tasks"):
                from .convert_flow import convert_flow
                return convert_flow(data)
            return data

    raise FileNotFoundError(f"流程定义不存在: {name}")


def list_flows() -> list[str]:
    """列出所有可用流程"""
    names = set()
    for flows_dir in _flow_dirs():
        for f in flows_dir.glob("*.yaml"):
            name = f.stem.replace("_v2", "")
            names.add(name)
    return sorted(names)


# ── 节点访问 ──────────────────────────────────────────

def get_nodes(flow: dict) -> dict:
    """获取节点映射 {id: node}"""
    return {n["id"]: n for n in flow.get("nodes", [])}


def get_node(flow: dict, node_id: str) -> dict | None:
    """获取单个节点"""
    for n in flow.get("nodes", []):
        if n["id"] == node_id:
            return n
    return None


def get_phases(flow: dict) -> list[dict]:
    """获取阶段元数据列表"""
    return flow.get("phases", [])


def get_phase_map(flow: dict) -> dict:
    """获取阶段映射 {id: phase_meta}"""
    return {p["id"]: p for p in flow.get("phases", [])}


def get_nodes_by_phase(flow: dict, phase_id: str) -> list[dict]:
    """获取某阶段的所有节点"""
    return [n for n in flow.get("nodes", []) if n.get("phase") == phase_id]


def get_all_task_ids(flow: dict) -> set[str]:
    """获取所有节点 ID"""
    return {n["id"] for n in flow.get("nodes", [])}


def find_task(flow: dict, task_id: str) -> tuple[dict | None, dict | None]:
    """兼容旧接口：返回 (phase_meta, node)"""
    node = get_node(flow, task_id)
    if not node:
        return None, None
    phase_map = get_phase_map(flow)
    phase = phase_map.get(node.get("phase", ""), {})
    return phase, node


def get_phase_order(flow: dict) -> list[str]:
    """获取阶段顺序"""
    return [p["id"] for p in flow.get("phases", [])]

"""流程定义加载"""
import yaml
from pathlib import Path

FLOWS_DIR = Path(__file__).parent.parent / "flows"


def load_flow(name: str = "duxin") -> dict:
    """加载流程定义"""
    flow_file = FLOWS_DIR / f"{name}.yaml"
    if not flow_file.exists():
        raise FileNotFoundError(f"流程定义不存在: {flow_file}")
    with open(flow_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_flows() -> list[str]:
    """列出所有可用流程"""
    return [f.stem for f in FLOWS_DIR.glob("*.yaml")]


def get_phase_order(flow: dict) -> list[str]:
    """获取阶段顺序"""
    return [p["id"] for p in flow.get("phases", [])]


def get_phases(flow: dict) -> dict:
    """获取阶段映射 {id: phase_dict}"""
    return {p["id"]: p for p in flow.get("phases", [])}


def get_all_task_ids(flow: dict) -> set[str]:
    """获取所有任务 ID"""
    ids = set()
    for phase in flow.get("phases", []):
        for task in phase.get("tasks", []):
            ids.add(task["id"])
    return ids


def find_task(flow: dict, task_id: str) -> tuple[dict | None, dict | None]:
    """根据 task_id 查找任务和所属阶段，返回 (phase, task)"""
    for phase in flow.get("phases", []):
        for task in phase.get("tasks", []):
            if task["id"] == task_id:
                return phase, task
    return None, None

"""将旧格式流程（phases→tasks）转换为新格式（扁平 nodes）"""
import yaml
import sys
from pathlib import Path


def convert_flow(old_flow: dict) -> dict:
    """旧格式 → 新格式"""
    nodes = []
    phases = []

    for phase in old_flow.get("phases", []):
        pid = phase["id"]

        # 阶段元数据
        phase_meta = {"id": pid, "name": phase.get("name", pid)}
        if phase.get("milestone"):
            phase_meta["milestone"] = phase["milestone"]
        phases.append(phase_meta)

        for task in phase.get("tasks", []):
            node = {
                "id": task["id"],
                "name": task["name"],
                "type": "task",
                "phase": pid,
            }

            # 可选字段
            if task.get("owner"):
                node["owner"] = task["owner"]
            if task.get("depends"):
                node["depends"] = task["depends"]
            if task.get("deliverables"):
                node["deliverables"] = task["deliverables"]
            if task.get("gate"):
                node["gate"] = task["gate"]
            if task.get("critical"):
                node["critical"] = True
            if task.get("reviewer"):
                node["reviewer"] = task["reviewer"]
            if task.get("description"):
                node["description"] = task["description"]

            nodes.append(node)

        # 如果阶段有里程碑，生成里程碑节点
        if phase.get("milestone"):
            ms_id = f"ms_{pid.lower()}"
            # 里程碑依赖该阶段所有无下游的任务（叶子节点）
            phase_task_ids = {t["id"] for t in phase.get("tasks", [])}
            depended_by = set()
            for t in phase.get("tasks", []):
                for d in t.get("depends", []):
                    if d in phase_task_ids:
                        depended_by.add(d)
            leaf_tasks = [t["id"] for t in phase.get("tasks", [])
                         if t["id"] not in depended_by]

            nodes.append({
                "id": ms_id,
                "name": f"{phase.get('name', pid)} 里程碑",
                "type": "milestone",
                "phase": pid,
                "depends": leaf_tasks if leaf_tasks else [phase["tasks"][-1]["id"]],
            })

    return {"phases": phases, "nodes": nodes}


def main():
    if len(sys.argv) < 2:
        print("用法: python convert_flow.py <old_flow.yaml> [output.yaml]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    with open(input_path, "r", encoding="utf-8") as f:
        old = yaml.safe_load(f)

    new = convert_flow(old)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(new, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        print(f"✅ 转换完成: {output_path}")
        print(f"   {len(new['nodes'])} 个节点, {len(new['phases'])} 个阶段")
    else:
        print(yaml.dump(new, allow_unicode=True, default_flow_style=False, sort_keys=False))


if __name__ == "__main__":
    main()

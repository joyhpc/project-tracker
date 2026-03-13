"""domain_sync — 通用领域工具包同步桥

从工具包的 pt-sync.yaml manifest 中读取同步规则，
将工具输出（如审核报告、评分卡）自动映射到 pt 的 decisions/pocs/reviews。

Manifest 格式:
    name: opportunity-detector
    scan_dir: ./outputs
    file_pattern: "*.md"
    extract:
      type: verdict_keyword   # 或 severity_tag
      keywords: {GO: "GO", KILL: "KILL", MAYBE: "MAYBE"}
    target: decisions          # 或 reviews, pocs

支持的 extract 类型:
  - verdict_keyword: 从文件内容中匹配关键词决定 verdict
  - severity_tag:    匹配 P0/P1/P2 标签 (sch-review 模式)
"""
import os
import re
from datetime import datetime
from pathlib import Path

try:
    import yaml as _yaml
except ImportError:
    _yaml = None


def discover_manifests(search_dirs: list[str] = None) -> list[dict]:
    """发现所有 pt-sync.yaml manifest 文件。

    默认搜索 ~/sch-review, ~/opportunity-detector, ~/hardware-copilot 等。
    也支持自定义搜索路径。
    """
    if _yaml is None:
        return []

    if search_dirs is None:
        home = Path.home()
        search_dirs = [
            str(home / "sch-review"),
            str(home / "opportunity-detector"),
            str(home / "hardware-copilot"),
        ]
        # 也支持 ~/.pt/sync.d/ 目录
        extra_dir = home / ".pt" / "sync.d"
        if extra_dir.is_dir():
            search_dirs.extend(str(p.parent) for p in extra_dir.glob("*.yaml"))

    manifests = []
    for dir_path in search_dirs:
        manifest_file = Path(dir_path).expanduser() / "pt-sync.yaml"
        if manifest_file.is_file():
            try:
                data = _yaml.safe_load(manifest_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data["_manifest_path"] = str(manifest_file)
                    data["_base_dir"] = str(Path(dir_path).expanduser())
                    manifests.append(data)
            except Exception:
                continue

    return manifests


def _resolve_scan_dir(manifest: dict) -> Path:
    """解析 manifest 中的 scan_dir 为绝对路径。"""
    scan_dir = manifest.get("scan_dir", ".")
    base = Path(manifest.get("_base_dir", "."))
    resolved = (base / scan_dir).resolve()
    return resolved


def _extract_verdict_keyword(content: str, keywords: dict) -> str | None:
    """从内容中匹配 verdict 关键词。

    keywords 格式: {"GO": "GO", "KILL": "KILL", "MAYBE": "MAYBE"}
    按优先级匹配第一个出现的。
    """
    for verdict, pattern in keywords.items():
        if re.search(rf'\b{re.escape(pattern)}\b', content, re.IGNORECASE):
            return verdict
    return None


def _extract_severity_tag(content: str) -> dict:
    """从内容中提取 P0/P1/P2 标签计数 (sch-review 模式)。"""
    counts = {}
    for sev in ("P0", "P1", "P2", "P3", "P4"):
        counts[sev] = len(re.findall(rf'\b{sev}\b', content))

    if counts["P0"] > 0:
        verdict = "NO-GO"
    elif counts["P1"] > 0:
        verdict = "CAUTION"
    else:
        verdict = "GO"

    return {"counts": counts, "verdict": verdict}


def _extract_title(content: str) -> str:
    """提取 Markdown 文件标题。"""
    for line in content.split("\n")[:20]:
        m = re.match(r'^#\s+(.*)', line)
        if m:
            return m.group(1).strip()
    return ""


def sync_manifest(manifest: dict, project: dict, dry_run: bool = False) -> list[dict]:
    """执行单个 manifest 的同步。

    Returns:
        新同步的条目列表。
    """
    scan_dir = _resolve_scan_dir(manifest)
    if not scan_dir.is_dir():
        return []

    file_pattern = manifest.get("file_pattern", "*.md")
    extract_config = manifest.get("extract", {})
    extract_type = extract_config.get("type", "verdict_keyword")
    target = manifest.get("target", "decisions")
    source_name = manifest.get("name", "unknown")

    # 收集已有条目避免重复
    existing_files = set()
    for entry in project.get(target, []):
        existing_files.add(entry.get("file", ""))
        existing_files.add(entry.get("source_file", ""))

    synced = []

    for fpath in sorted(scan_dir.rglob(file_pattern)):
        abs_path = str(fpath)
        if abs_path in existing_files:
            continue

        try:
            content = fpath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue

        title = _extract_title(content) or fpath.name

        entry = None

        if extract_type == "verdict_keyword":
            keywords = extract_config.get("keywords", {})
            verdict = _extract_verdict_keyword(content, keywords)
            if verdict is None:
                continue

            if target == "decisions":
                entry = {
                    "text": f"[{source_name}] {title}",
                    "source": f"domain-sync/{source_name}",
                    "source_file": abs_path,
                    "verdict": verdict,
                    "status": "active",
                    "synced": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
            elif target == "reviews":
                entry = {
                    "file": abs_path,
                    "source": f"domain-sync/{source_name}",
                    "title": title,
                    "verdicts": [{"verdict": verdict}],
                    "synced": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }

        elif extract_type == "severity_tag":
            sev = _extract_severity_tag(content)
            total = sum(sev["counts"].get(s, 0) for s in ("P0", "P1", "P2"))
            if total == 0:
                continue

            entry = {
                "file": abs_path,
                "source": f"domain-sync/{source_name}",
                "title": title,
                "verdicts": [{"verdict": sev["verdict"]}],
                "synced": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "p0_count": sev["counts"]["P0"],
                "p1_count": sev["counts"]["P1"],
                "p2_count": sev["counts"]["P2"],
            }
            target = "reviews"  # severity_tag 始终同步到 reviews

        if entry is None:
            continue

        synced.append({"entry": entry, "target": target, "file": abs_path, "title": title})

        if not dry_run:
            if target not in project:
                project[target] = []
            project[target].append(entry)
            existing_files.add(abs_path)

    return synced


def sync_all(project: dict, dry_run: bool = False,
             search_dirs: list[str] = None) -> dict:
    """执行所有已发现 manifest 的同步。

    Returns:
        {"manifests_found": N, "total_synced": N, "details": [...]}
    """
    manifests = discover_manifests(search_dirs)
    results = {
        "manifests_found": len(manifests),
        "total_synced": 0,
        "details": [],
    }

    for manifest in manifests:
        synced = sync_manifest(manifest, project, dry_run)
        results["details"].append({
            "name": manifest.get("name", "unknown"),
            "manifest": manifest.get("_manifest_path", ""),
            "synced_count": len(synced),
            "items": synced,
        })
        results["total_synced"] += len(synced)

    return results

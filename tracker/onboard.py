"""中途导入模块 — 将已有项目接入 pt 的标准化流程

职责：
1. 扫描仓库文档，识别 review/决策/PoC 文件
2. 注册 review 文件（复用 review 系统的标准格式）
3. 生成导入 prompt（喂给 LLM 生成 pt 命令序列）

设计原则：
- 独立模块，不影响现有功能
- 通过 core 层操作数据，不直接修改项目 YAML
- review 注册复用标准 verdicts 格式 (list[{verdict, topic}])
"""
import os
import re
from pathlib import Path


# ── 文档扫描 ──────────────────────────────────────────

VERDICT_PATTERNS = re.compile(
    r'\b(GO|NO-GO|CAUTION|CONDITIONAL\s*GO|HIGH\s*RISK|HIGHLY\s*FEASIBLE)\b',
    re.IGNORECASE
)
DECISION_PATTERNS = re.compile(
    r'(决策|拍板|Decision|D[1-9]|已决定|确定方案|选定)',
    re.IGNORECASE
)
POC_PATTERNS = re.compile(
    r'(PoC|验证|红线|Go.No.Go|原型|Prototype|MVP)',
    re.IGNORECASE
)

EXCLUDE_DIRS = {".git", "node_modules", ".pt", "__pycache__", ".venv", "venv"}
EXCLUDE_FILES = {
    "onboard-prompt.md",
    "arch-prompt.md",
    "propose-prompt.md",
    "feasibility-report.md",
}


def scan_repo(repo_path: str) -> dict:
    """扫描仓库，返回分类结果

    Returns:
        {
            "repo": str,
            "files": list[FileInfo],
            "reviews": list[FileInfo],
            "decisions": list[FileInfo],
            "pocs": list[FileInfo],
            "docs": list[FileInfo],
        }
    """
    repo = Path(repo_path)
    if not repo.exists():
        raise FileNotFoundError(f"路径不存在: {repo}")

    md_files = sorted(repo.rglob("*.md"))
    md_files = [f for f in md_files if not any(
        p in f.parts for p in EXCLUDE_DIRS
    )]
    md_files = [f for f in md_files if f.name not in EXCLUDE_FILES and "prompts" not in f.parts]

    results = []
    for f in md_files:
        info = _scan_file(f)
        if info:
            results.append(info)

    return {
        "repo": str(repo),
        "files": results,
        "reviews": [r for r in results if r["type"] == "review"],
        "decisions": [r for r in results if r["has_decisions"]],
        "pocs": [r for r in results if r["has_poc"]],
        "docs": [r for r in results if r["type"] == "doc"],
    }


def _scan_file(path: Path) -> dict | None:
    """扫描单个 markdown 文件，返回分类信息"""
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return None

    lines = content.split("\n")
    title = ""
    for line in lines[:10]:
        m = re.match(r'^#\s+(.*)', line)
        if m:
            title = m.group(1).strip()
            break

    raw_verdicts = VERDICT_PATTERNS.findall(content)
    has_decisions = bool(DECISION_PATTERNS.search(content))
    has_poc = bool(POC_PATTERNS.search(content))

    # 标准化 verdicts 为 list[{verdict, topic}] 格式
    verdicts = _extract_scan_verdicts(content, raw_verdicts)

    file_type = "doc"
    if verdicts:
        file_type = "review"
    elif has_decisions:
        file_type = "decision"
    elif has_poc:
        file_type = "poc"

    return {
        "path": str(path),
        "title": title,
        "type": file_type,
        "size": len(content),
        "lines": len(lines),
        "verdicts": verdicts,  # 标准格式: list[{verdict, topic}]
        "has_decisions": has_decisions,
        "has_poc": has_poc,
    }


def _extract_scan_verdicts(content: str, raw_matches: list[str]) -> list[dict]:
    """从扫描结果提取标准格式的 verdicts

    与 review_cmd._extract_verdicts 不同：这里是粗粒度扫描，
    只知道文件里出现了哪些判定关键词，不知道具体上下文。
    """
    if not raw_matches:
        return []

    # 去重计数
    counts = {}
    for v in raw_matches:
        v_upper = v.upper().replace(" ", "-")
        if v_upper == "CONDITIONAL-GO":
            v_upper = "CONDITIONAL GO"
        counts[v_upper] = counts.get(v_upper, 0) + 1

    # 转为标准格式
    verdicts = []
    for verdict_str, count in counts.items():
        verdicts.append({
            "verdict": verdict_str,
            "topic": f"(扫描发现, 出现{count}次)",
        })
    return verdicts


# ── Review 注册 ──────────────────────────────────────

def register_reviews(project: dict, scan_result: dict) -> int:
    """将扫描发现的 review 文件注册到项目

    复用标准 verdicts 格式，确保与 review --add 的数据一致。

    Returns:
        注册数量
    """
    from . import core

    repo = Path(scan_result["repo"])
    reviews = scan_result["reviews"]

    if "reviews" not in project:
        project["reviews"] = []

    existing = {r["file"] for r in project["reviews"]}
    registered = 0

    for r in reviews:
        rel = os.path.relpath(r["path"], repo)
        if rel in existing:
            continue

        # 使用标准格式 — verdicts 已经是 list[{verdict, topic}]
        review_entry = {
            "file": rel,
            "task": None,
            "verdicts": r["verdicts"],  # 标准格式
            "source": "onboard-scan",
        }
        project["reviews"].append(review_entry)
        registered += 1

    if registered:
        core._save(project)

    return registered


# ── Onboard Prompt 生成 ──────────────────────────────

def generate_onboard_prompt(repo_path: str, scan_result: dict) -> str:
    """生成项目导入 prompt，用于喂给 LLM 生成 pt 命令序列

    Returns:
        prompt 文本
    """
    repo = Path(repo_path)
    results = scan_result["files"]
    reviews = scan_result["reviews"]

    lines = []
    lines.append("**角色**：你是一位项目管理专家，精通硬件产品开发全流程。")
    lines.append("你的任务是：基于以下已有项目文档，生成一个 project-tracker 项目配置文件（YAML 格式）。")
    lines.append("")
    lines.append("## 已有文档清单")
    lines.append("")

    for r in results:
        rel = os.path.relpath(r["path"], repo)
        type_icon = {"review": "📋", "decision": "📌", "poc": "🧪", "doc": "📄"}.get(r["type"], "📄")
        extra = ""
        if r["verdicts"]:
            v_str = " ".join(f'{v["verdict"]}' for v in r["verdicts"])
            extra = f" [{v_str}]"
        lines.append(f"- {type_icon} `{rel}` — {r['title'] or '(无标题)'}{extra}")

    lines.append("")

    # 注入 review 文件的摘要内容
    if reviews:
        lines.append("## Review 文件内容摘要")
        lines.append("")
        for r in reviews[:5]:
            rel = os.path.relpath(r["path"], repo)
            try:
                content = Path(r["path"]).read_text(encoding="utf-8")
                if len(content) > 1500:
                    content = content[:1500] + "\n... (截断)"
                lines.append(f'<file path="{rel}">')
                lines.append(content)
                lines.append("</file>")
                lines.append("")
            except Exception:
                pass

    lines.append("## 你的任务")
    lines.append("")
    lines.append("基于以上文档，生成以下内容：")
    lines.append("")
    lines.append("1. **项目名称和 ID**")
    lines.append("2. **当前阶段判断**（概念/设计/原型/测试/量产）")
    lines.append("3. **已完成任务列表**（每个任务附 note 摘要）")
    lines.append("4. **已拍板决策列表**（从文档中提取）")
    lines.append("5. **PoC 验证项**（如果有）")
    lines.append("6. **下一步建议**")
    lines.append("")
    lines.append("输出格式：直接给出可执行的 pt 命令序列，例如：")
    lines.append("```bash")
    lines.append('pt init PROJECT_ID --name "项目名称" --repo /path/to/repo')
    lines.append('pt done market_research --note "市场调研完成:..." --force')
    lines.append("pt review --add docs/feasibility/01-xxx-result.md")
    lines.append('pt decision --add "决策标题" --source feasibility-01 --impact "影响"')
    lines.append('pt poc --add "验证项" --metric "红线指标"')
    lines.append("```")

    return "\n".join(lines)


def save_onboard_prompt(repo_path: str, prompt_text: str) -> str:
    """保存 onboard prompt 到仓库

    Returns:
        保存路径（相对于仓库根）
    """
    repo = Path(repo_path)
    save_path = repo / "docs" / "onboard-prompt.md"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_text(prompt_text, encoding="utf-8")
    return os.path.relpath(save_path, repo)


# ── 架构理解 Prompt ──────────────────────────────────

def generate_arch_prompt(repo_path: str, scan_result: dict) -> str:
    """生成项目架构理解 prompt — 中途介入项目时的第一步

    扫描仓库目录结构和文档内容，生成一个 prompt 让 LLM 输出结构化的
    项目架构理解文档，供人工确认后存档。

    Returns:
        prompt 文本
    """
    repo = Path(repo_path)
    results = scan_result["files"]

    lines = []
    lines.append("**角色**：你是一位资深硬件系统架构师，精通多产品线项目的架构分析。")
    lines.append("")
    lines.append("## 任务")
    lines.append("基于以下项目仓库的目录结构和文档内容，输出一份**项目架构理解文档**。")
    lines.append("这是中途介入项目时的第一步，目的是建立正确的全局理解，避免错误假设。")
    lines.append("")

    # 目录树（只展示前3层）
    lines.append("## 仓库目录结构")
    lines.append("```")
    dir_tree = _build_dir_tree(repo, max_depth=3)
    lines.append(dir_tree)
    lines.append("```")
    lines.append("")

    # 关键文档内容摘要
    lines.append("## 关键文档内容")
    lines.append("")

    # 优先读 README、架构、需求、接口定义等关键文件
    priority_keywords = ["readme", "架构", "architecture", "需求", "requirement",
                         "接口", "interface", "差异", "总览", "overview", "dashboard",
                         "设计说明", "功能需求"]
    key_files = []
    other_files = []
    for r in results:
        rel = os.path.relpath(r["path"], repo)
        is_key = any(kw in rel.lower() or kw in r.get("title", "").lower()
                     for kw in priority_keywords)
        if is_key:
            key_files.append(r)
        else:
            other_files.append(r)

    # 注入关键文件内容（最多10个，每个最多1500字符）
    for r in key_files[:10]:
        rel = os.path.relpath(r["path"], repo)
        try:
            content = Path(r["path"]).read_text(encoding="utf-8")
            if len(content) > 1500:
                content = content[:1500] + "\n... (截断)"
            lines.append(f'<file path="{rel}" title="{r.get("title", "")}">')
            lines.append(content)
            lines.append("</file>")
            lines.append("")
        except Exception:
            pass

    # 列出其他文件（仅路径和标题）
    if other_files:
        lines.append("## 其他文档（仅列出路径）")
        for r in other_files[:30]:
            rel = os.path.relpath(r["path"], repo)
            lines.append(f"- `{rel}` — {r.get('title', '(无标题)')}")
        if len(other_files) > 30:
            lines.append(f"- ... 还有 {len(other_files) - 30} 个")
        lines.append("")

    # 输出要求
    lines.append("## 输出要求")
    lines.append("")
    lines.append("请输出一份 **PROJECT_STRUCTURE.md**，必须包含以下章节：")
    lines.append("")
    lines.append("### 1. 产品定位")
    lines.append("一句话描述这个项目是什么。")
    lines.append("")
    lines.append("### 2. 产品线/子系统")
    lines.append("列出所有独立的产品线或子系统，每个包含：")
    lines.append("- 名称和缩写")
    lines.append("- 是独立产品还是共用模块？")
    lines.append("- 核心硬件（主芯片、连接器等）")
    lines.append("- 当前状态")
    lines.append("")
    lines.append("### 3. 模块关系图")
    lines.append("用文本描述各子系统/模块之间的关系（共用什么、独立什么、接口是什么）。")
    lines.append("特别注意：哪些是独立 PCB？哪些共用 PCB？哪些共用固件？")
    lines.append("")
    lines.append("### 4. 接口定义")
    lines.append("列出关键接口（板间连接器、通信协议、电源域）。")
    lines.append("")
    lines.append("### 5. 待确认项")
    lines.append("列出你不确定的地方，标注 `[待确认]`。")
    lines.append("")
    lines.append("**关键原则**：")
    lines.append("- 不确定的就标 `[待确认]`，绝对不要猜")
    lines.append("- 区分「独立产品」和「共用模块」是最重要的判断")
    lines.append("- 输出 markdown 格式，可直接保存为 `docs/PROJECT_STRUCTURE.md`")

    return "\n".join(lines)


def _build_dir_tree(root: Path, max_depth: int = 3, prefix: str = "") -> str:
    """生成目录树字符串（只展示目录，不展示文件）"""
    lines = []
    if not prefix:
        lines.append(root.name + "/")

    try:
        entries = sorted(root.iterdir())
    except PermissionError:
        return "\n".join(lines)

    dirs = [e for e in entries if e.is_dir() and e.name not in EXCLUDE_DIRS
            and not e.name.startswith(".")]
    files_md = [e for e in entries if e.is_file() and e.suffix == ".md"]

    items = dirs + files_md
    for i, item in enumerate(items):
        is_last = (i == len(items) - 1)
        connector = "└── " if is_last else "├── "
        if item.is_dir():
            lines.append(f"{prefix}{connector}{item.name}/")
            if max_depth > 1:
                extension = "    " if is_last else "│   "
                subtree = _build_dir_tree(item, max_depth - 1, prefix + extension)
                if subtree:
                    lines.append(subtree)
        else:
            lines.append(f"{prefix}{connector}{item.name}")

    return "\n".join(lines)

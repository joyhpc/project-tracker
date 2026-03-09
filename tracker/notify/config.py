"""Webhook 配置加载器 — 从 config.yaml 读取 webhook 配置"""
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

# 缓存
_config_cache: dict | None = None
_config_mtime: float = 0.0


def load_config() -> dict:
    """加载 webhook 配置，带文件修改时间缓存。

    Returns:
        配置字典，包含 enabled 和 webhooks 列表。
        如果文件不存在或解析失败，返回 disabled 配置。
    """
    global _config_cache, _config_mtime

    if not _CONFIG_PATH.exists():
        return {"enabled": False, "webhooks": []}

    if yaml is None:
        return {"enabled": False, "webhooks": []}

    try:
        current_mtime = _CONFIG_PATH.stat().st_mtime
        if _config_cache is not None and current_mtime == _config_mtime:
            return _config_cache

        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        result = {
            "enabled": bool(cfg.get("enabled", False)),
            "webhooks": cfg.get("webhooks", []) or [],
        }
        _config_cache = result
        _config_mtime = current_mtime
        return result
    except Exception:
        return {"enabled": False, "webhooks": []}


def get_webhooks_for_event(event_type: str) -> list[dict]:
    """获取订阅了指定事件类型的 webhook 列表。

    Args:
        event_type: 事件类型 (如 start, done, block, mutation 等)

    Returns:
        匹配的 webhook 配置列表
    """
    cfg = load_config()
    if not cfg["enabled"]:
        return []

    result = []
    for wh in cfg["webhooks"]:
        events = wh.get("events") or []
        # 空列表 = 订阅所有事件
        if not events or event_type in events:
            result.append(wh)
    return result

"""Commands package — shared CLI utilities."""
import sys
from .. import core


def _icon(status: str) -> str:
    """返回状态对应的图标"""
    return {"done": "✅", "in_progress": "🔄", "blocked": "🚫", "pending": "⏳", "expanded": "📦"}.get(status, "❓")


def _require():
    """加载当前活跃项目，不存在则报错退出"""
    try:
        return core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

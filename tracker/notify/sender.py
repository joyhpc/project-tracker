"""Webhook 发送器 — 使用 urllib.request 发送 HTTP POST，3 秒超时，失败静默"""
import json
import urllib.request


def format_dingtalk(event_type: str, payload: dict) -> dict:
    """钉钉 Markdown 消息格式"""
    project_id = payload.get("project_id", "unknown")
    task_id = payload.get("task_id", "")
    report = payload.get("report", {})

    title = f"项目通知: {event_type}"
    lines = [f"### {title}", f"- **项目**: {project_id}"]
    if task_id:
        lines.append(f"- **任务**: {task_id}")
    if report.get("duration_diff"):
        lines.append(f"- **工期变化**: {report['duration_diff']:+.1f} 天")
    if report.get("warnings"):
        for w in report["warnings"][:3]:
            lines.append(f"- ⚠️ {w}")

    return {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": "\n".join(lines),
        },
    }


def format_feishu(event_type: str, payload: dict) -> dict:
    """飞书卡片消息格式"""
    project_id = payload.get("project_id", "unknown")
    task_id = payload.get("task_id", "")
    report = payload.get("report", {})

    elements = []
    fields = [{"is_short": True, "text": {"tag": "lark_md", "content": f"**项目**: {project_id}"}}]
    if task_id:
        fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**任务**: {task_id}"}})
    if report.get("duration_diff"):
        fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**工期变化**: {report['duration_diff']:+.1f} 天"}})
    elements.append({"tag": "div", "fields": fields})

    if report.get("warnings"):
        for w in report["warnings"][:3]:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"⚠️ {w}"}})

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"项目通知: {event_type}"},
                "template": "blue",
            },
            "elements": elements,
        },
    }


def format_wecom(event_type: str, payload: dict) -> dict:
    """企微 Markdown 消息格式"""
    project_id = payload.get("project_id", "unknown")
    task_id = payload.get("task_id", "")
    report = payload.get("report", {})

    lines = [f"### 项目通知: {event_type}", f"> **项目**: {project_id}"]
    if task_id:
        lines.append(f"> **任务**: {task_id}")
    if report.get("duration_diff"):
        lines.append(f"> **工期变化**: {report['duration_diff']:+.1f} 天")
    if report.get("warnings"):
        for w in report["warnings"][:3]:
            lines.append(f"> ⚠️ {w}")

    return {
        "msgtype": "markdown",
        "markdown": {
            "content": "\n".join(lines),
        },
    }


_FORMATTERS = {
    "dingtalk": format_dingtalk,
    "feishu": format_feishu,
    "wecom": format_wecom,
}


def send(url: str, webhook_type: str, event_type: str, payload: dict) -> None:
    """发送 webhook 通知，3 秒超时，失败静默。

    Args:
        url: Webhook URL
        webhook_type: 平台类型 (dingtalk / feishu / wecom)
        event_type: 事件类型
        payload: 事件数据
    """
    try:
        formatter = _FORMATTERS.get(webhook_type, format_dingtalk)
        body = formatter(event_type, payload)
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass

"""无侵入式 Webhook 通知层

所有通知均为尽力而为 (best-effort)，失败静默，绝不影响核心流程。
"""


def fire_event(event_type: str, payload: dict) -> None:
    """无侵入式事件通知，失败静默。

    Args:
        event_type: 事件类型 (如 start, done, block, unblock, mutation 等)
        payload: 事件数据字典，通常包含 project_id, task_id, report 等
    """
    try:
        from .config import get_webhooks_for_event
        from .sender import send

        webhooks = get_webhooks_for_event(event_type)
        for wh in webhooks:
            url = wh.get("url", "")
            wh_type = wh.get("type", "dingtalk")
            if url:
                send(url, wh_type, event_type, payload)
    except Exception:
        pass

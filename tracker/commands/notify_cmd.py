def cmd_notify(args):
    """测试 webhook 通知配置"""
    action = getattr(args, "action", "status")

    if action == "test":
        # 发送测试通知
        from ..notify import fire_event
        fire_event("test", {"project_id": "test", "message": "Webhook 测试通知"})
        print("测试通知已发送 (请检查 Webhook 接收端)")
    elif action == "status":
        # 显示当前配置状态
        from ..notify.config import load_config
        cfg = load_config()
        if not cfg["enabled"]:
            print("通知状态: 已禁用")
            print(f"配置文件: tracker/notify/config.yaml")
            return
        print("通知状态: 已启用")
        for wh in cfg["webhooks"]:
            name = wh.get("name", "unnamed")
            wh_type = wh.get("type", "unknown")
            events = wh.get("events", []) or ["全部"]
            url = wh.get("url", "")
            # 隐藏 URL 中间部分
            if len(url) > 30:
                masked = url[:20] + "****" + url[-10:]
            else:
                masked = url
            print(f"  - {name} ({wh_type}): {masked}")
            print(f"    事件: {', '.join(str(e) for e in events)}")

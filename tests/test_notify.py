"""Tests for the tracker.notify package (config, sender, fire_event).

All tests are pure offline — no real HTTP requests are made.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock, PropertyMock


class NotifyConfigTests(unittest.TestCase):
    """Tests for notify/config.py"""

    def setUp(self):
        # Reset the module-level cache before each test so tests are independent.
        import tracker.notify.config as _cfg

        _cfg._config_cache = None
        _cfg._config_mtime = 0.0

    def test_load_config_returns_disabled_when_file_missing(self):
        """config.yaml 不存在时返回 disabled"""
        import tracker.notify.config as cfg

        with patch.object(type(cfg._CONFIG_PATH), "exists", return_value=False):
            result = cfg.load_config()
        self.assertFalse(result["enabled"])
        self.assertEqual(result["webhooks"], [])

    def test_load_config_returns_disabled_when_yaml_not_installed(self):
        """yaml 模块不可用时返回 disabled"""
        import tracker.notify.config as cfg

        original_yaml = cfg.yaml
        try:
            cfg.yaml = None
            with patch.object(type(cfg._CONFIG_PATH), "exists", return_value=True):
                result = cfg.load_config()
            self.assertFalse(result["enabled"])
            self.assertEqual(result["webhooks"], [])
        finally:
            cfg.yaml = original_yaml

    def test_load_config_caches_by_mtime(self):
        """相同 mtime 时返回缓存结果"""
        import tracker.notify.config as cfg

        fake_config = {"enabled": True, "webhooks": [{"url": "http://x", "type": "dingtalk"}]}

        # Seed the cache
        cfg._config_cache = fake_config
        cfg._config_mtime = 12345.0

        # Mock: file exists, stat returns same mtime
        mock_stat = MagicMock()
        mock_stat.st_mtime = 12345.0

        with patch.object(type(cfg._CONFIG_PATH), "exists", return_value=True), \
             patch.object(type(cfg._CONFIG_PATH), "stat", return_value=mock_stat):
            result = cfg.load_config()

        # Should return the cached object without re-reading the file
        self.assertIs(result, fake_config)

    def test_get_webhooks_for_event_filters_by_event_type(self):
        """events 列表过滤正确"""
        import tracker.notify.config as cfg

        fake_config = {
            "enabled": True,
            "webhooks": [
                {"url": "http://a", "type": "dingtalk", "events": ["start", "done"]},
                {"url": "http://b", "type": "feishu", "events": ["block"]},
            ],
        }

        with patch.object(cfg, "load_config", return_value=fake_config):
            matched = cfg.get_webhooks_for_event("done")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["url"], "http://a")

    def test_get_webhooks_for_event_empty_list_matches_all(self):
        """events 为空列表时匹配所有事件"""
        import tracker.notify.config as cfg

        fake_config = {
            "enabled": True,
            "webhooks": [
                {"url": "http://all", "type": "dingtalk", "events": []},
                {"url": "http://specific", "type": "feishu", "events": ["block"]},
            ],
        }

        with patch.object(cfg, "load_config", return_value=fake_config):
            matched = cfg.get_webhooks_for_event("mutation")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["url"], "http://all")

    def test_get_webhooks_for_event_returns_empty_when_disabled(self):
        """通知禁用时返回空列表"""
        import tracker.notify.config as cfg

        fake_config = {
            "enabled": False,
            "webhooks": [{"url": "http://a", "type": "dingtalk"}],
        }

        with patch.object(cfg, "load_config", return_value=fake_config):
            matched = cfg.get_webhooks_for_event("done")
        self.assertEqual(matched, [])


class NotifySenderTests(unittest.TestCase):
    """Tests for notify/sender.py"""

    def test_format_dingtalk_produces_valid_structure(self):
        """钉钉格式包含 msgtype 和 markdown"""
        from tracker.notify.sender import format_dingtalk

        payload = {"project_id": "PROJ", "task_id": "t1", "report": {}}
        result = format_dingtalk("done", payload)

        self.assertEqual(result["msgtype"], "markdown")
        self.assertIn("markdown", result)
        self.assertIn("title", result["markdown"])
        self.assertIn("text", result["markdown"])
        self.assertIn("PROJ", result["markdown"]["text"])

    def test_format_dingtalk_includes_duration_diff(self):
        """钉钉格式包含工期变化信息"""
        from tracker.notify.sender import format_dingtalk

        payload = {"project_id": "P", "report": {"duration_diff": 2.5}}
        result = format_dingtalk("mutation", payload)
        self.assertIn("+2.5", result["markdown"]["text"])

    def test_format_dingtalk_includes_warnings(self):
        """钉钉格式包含告警信息"""
        from tracker.notify.sender import format_dingtalk

        payload = {"project_id": "P", "report": {"warnings": ["w1", "w2", "w3", "w4"]}}
        result = format_dingtalk("mutation", payload)
        text = result["markdown"]["text"]
        # Only first 3 warnings should appear
        self.assertIn("w1", text)
        self.assertIn("w3", text)
        self.assertNotIn("w4", text)

    def test_format_feishu_produces_valid_structure(self):
        """飞书格式包含 msg_type 和 card"""
        from tracker.notify.sender import format_feishu

        payload = {"project_id": "PROJ", "task_id": "t1", "report": {}}
        result = format_feishu("start", payload)

        self.assertEqual(result["msg_type"], "interactive")
        self.assertIn("card", result)
        self.assertIn("header", result["card"])
        self.assertIn("elements", result["card"])

    def test_format_wecom_produces_valid_structure(self):
        """企微格式包含 msgtype 和 markdown"""
        from tracker.notify.sender import format_wecom

        payload = {"project_id": "PROJ", "task_id": "t1", "report": {}}
        result = format_wecom("block", payload)

        self.assertEqual(result["msgtype"], "markdown")
        self.assertIn("markdown", result)
        self.assertIn("content", result["markdown"])
        self.assertIn("PROJ", result["markdown"]["content"])

    def test_send_catches_exceptions_silently(self):
        """发送失败时不抛异常"""
        from tracker.notify.sender import send

        # urlopen will raise because no real HTTP, but send should catch it
        with patch("tracker.notify.sender.urllib.request.urlopen", side_effect=Exception("boom")):
            # Should NOT raise
            send("http://example.com/hook", "dingtalk", "done", {"project_id": "P"})

    def test_send_posts_json_body(self):
        """send 正确发送 JSON POST 请求"""
        from tracker.notify.sender import send
        import json

        with patch("tracker.notify.sender.urllib.request.urlopen") as mock_urlopen:
            send("http://example.com/hook", "dingtalk", "done", {"project_id": "P"})

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_method(), "POST")
        self.assertIn("application/json", req.get_header("Content-type"))
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["msgtype"], "markdown")

    def test_send_uses_feishu_formatter_for_feishu_type(self):
        """webhook_type=feishu 时使用飞书格式"""
        from tracker.notify.sender import send
        import json

        with patch("tracker.notify.sender.urllib.request.urlopen") as mock_urlopen:
            send("http://example.com/hook", "feishu", "done", {"project_id": "P"})

        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["msg_type"], "interactive")


class NotifyFireEventTests(unittest.TestCase):
    """Tests for notify/__init__.py fire_event"""

    def test_fire_event_silent_when_disabled(self):
        """通知禁用时静默返回"""
        from tracker.notify import fire_event

        with patch("tracker.notify.config.get_webhooks_for_event", return_value=[]):
            # Should not raise and should not call send
            with patch("tracker.notify.sender.send") as mock_send:
                fire_event("done", {"project_id": "P"})
                mock_send.assert_not_called()

    def test_fire_event_calls_send_for_matching_webhooks(self):
        """有匹配 webhook 时调用 send"""
        from tracker.notify import fire_event

        webhooks = [
            {"url": "http://a", "type": "dingtalk"},
            {"url": "http://b", "type": "feishu"},
        ]

        with patch("tracker.notify.config.get_webhooks_for_event", return_value=webhooks), \
             patch("tracker.notify.sender.send") as mock_send:
            fire_event("done", {"project_id": "P"})

        self.assertEqual(mock_send.call_count, 2)
        # Check arguments of the two calls
        calls = mock_send.call_args_list
        self.assertEqual(calls[0][0], ("http://a", "dingtalk", "done", {"project_id": "P"}))
        self.assertEqual(calls[1][0], ("http://b", "feishu", "done", {"project_id": "P"}))

    def test_fire_event_skips_webhook_without_url(self):
        """没有 url 的 webhook 被跳过"""
        from tracker.notify import fire_event

        webhooks = [
            {"type": "dingtalk"},  # no url
            {"url": "", "type": "feishu"},  # empty url
            {"url": "http://c", "type": "wecom"},  # valid
        ]

        with patch("tracker.notify.config.get_webhooks_for_event", return_value=webhooks), \
             patch("tracker.notify.sender.send") as mock_send:
            fire_event("done", {"project_id": "P"})

        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(mock_send.call_args[0][0], "http://c")

    def test_fire_event_catches_all_exceptions(self):
        """fire_event 内部异常不外抛"""
        from tracker.notify import fire_event

        with patch("tracker.notify.config.get_webhooks_for_event", side_effect=RuntimeError("crash")):
            # Should NOT raise
            fire_event("done", {"project_id": "P"})


if __name__ == "__main__":
    unittest.main()

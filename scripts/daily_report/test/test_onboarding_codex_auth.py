import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from collector import CodexCollector
from feishu.auth import parse_oauth_callback_query
from setup_wizard import build_config, build_next_steps, write_config


class CodexCollectorTest(unittest.TestCase):
    def test_collects_and_summarizes_codex_sessions_for_a_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            sessions_root = Path(tmp) / "sessions"
            date_dir = sessions_root / "2026" / "06" / "05"
            date_dir.mkdir(parents=True)
            session_path = date_dir / "rollout-example.jsonl"
            rows = [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "session-1",
                        "cwd": "/Users/liangjiayu/projects/work/example",
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-06-05T01:00:00Z",
                    "payload": {
                        "type": "user_message",
                        "message": "请帮我检查日报采集逻辑",
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-06-05T01:01:00Z",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "已完成检查，并发现 Codex 会话需要纳入日报。",
                            }
                        ],
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-06-05T01:02:00Z",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "真实 Codex 日志中的 assistant 消息也应纳入总结。",
                            }
                        ],
                    },
                },
            ]
            session_path.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
                encoding="utf-8",
            )

            collector = CodexCollector(sessions_path=str(sessions_root))

            collected = collector.collect_for_date(datetime(2026, 6, 5))
            summary = collector.summarize_for_date(datetime(2026, 6, 5))

        self.assertIn("--- Codex 会话: rollout-example", collected)
        self.assertIn("请帮我检查日报采集逻辑", collected)
        self.assertIn("# Codex 会话总结 - 2026-06-05", summary)
        self.assertIn("会话数: 1", summary)
        self.assertIn("用户消息: 1", summary)
        self.assertIn("AI 回复: 2", summary)
        self.assertIn("/Users/liangjiayu/projects/work/example", summary)


class SetupWizardTest(unittest.TestCase):
    def test_build_config_uses_env_backed_credentials_and_enables_codex(self):
        config = build_config(
            enable_feishu=True,
            enable_codex=True,
            redirect_uri="http://localhost:8080/callback",
        )

        self.assertTrue(config["feishu"]["enabled"])
        self.assertEqual(config["feishu"]["app_id"], "os.environ/FEISHU_APP_ID")
        self.assertEqual(config["feishu"]["app_secret"], "os.environ/FEISHU_APP_SECRET")
        self.assertEqual(config["feishu"]["redirect_uri"], "http://localhost:8080/callback")
        self.assertTrue(config["codex"]["enabled"])
        self.assertEqual(config["codex"]["sessions_path"], "~/.codex/sessions")

    def test_write_config_does_not_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("existing: true\n", encoding="utf-8")

            wrote = write_config(path, {"new": True}, force=False)

            self.assertFalse(wrote)
            self.assertEqual(path.read_text(encoding="utf-8"), "existing: true\n")

    def test_next_steps_include_auth_callback_without_codex_summary_command(self):
        steps = "\n".join(build_next_steps())

        self.assertIn("python daily_report.py --init", steps)
        self.assertIn("python -m feishu auth --callback", steps)
        self.assertIn("Codex 会话会自动纳入日报", steps)
        self.assertNotIn("--codex-summary", steps)


class FeishuOAuthCallbackTest(unittest.TestCase):
    def test_parse_callback_extracts_auth_code(self):
        result = parse_oauth_callback_query("/callback?code=abc123&state=xyz")

        self.assertEqual(result["code"], "abc123")
        self.assertIsNone(result["error"])

    def test_parse_callback_extracts_error(self):
        result = parse_oauth_callback_query("/callback?error=access_denied&error_description=no")

        self.assertIsNone(result["code"])
        self.assertEqual(result["error"], "access_denied")
        self.assertEqual(result["error_description"], "no")


if __name__ == "__main__":
    unittest.main()

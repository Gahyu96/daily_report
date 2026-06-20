import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from collector import CodexCollector
from feishu.auth import parse_oauth_callback_query
from setup_wizard import (
    build_config,
    build_local_next_steps,
    build_next_steps,
    collect_local_doctor_checks,
    choose_callback_port,
    rewrite_local_callback_uri,
    write_config,
)


class CodexCollectorTest(unittest.TestCase):
    def test_default_collector_does_not_filter_project_paths(self):
        collector = CodexCollector()

        self.assertFalse(
            collector._should_exclude_cwd(
                "/Users/example/projects/private-project"
            )
        )

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
    def test_public_configs_do_not_include_private_exclude_keywords(self):
        config = build_config()
        example_config = Path("config.example.yaml").read_text(encoding="utf-8")

        self.assertNotIn("exclude_keywords", config["codex"])
        self.assertNotIn("exclude_keywords", example_config)

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
        self.assertEqual(config["llm"]["model"], "deepseek-v4-flash-260425")

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

    def test_local_next_steps_point_to_doctor_and_callback_auth(self):
        steps = "\n".join(build_local_next_steps())

        self.assertIn("python daily_report.py doctor", steps)
        self.assertIn("python -m feishu auth --callback", steps)
        self.assertIn("python daily_report.py --yesterday", steps)

    def test_local_doctor_reports_ready_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token_dir = root / "feishu_env"
            token_dir.mkdir()
            (token_dir / "token_cache.json").write_text(
                json.dumps({
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "expires_at": 2_000_000_000,
                    "refresh_expires_at": 2_000_000_000,
                }),
                encoding="utf-8",
            )
            claude_projects = root / "claude_projects"
            codex_sessions = root / "codex_sessions"
            claude_projects.mkdir()
            codex_sessions.mkdir()

            config = build_config()
            config["feishu"]["env_dir"] = str(token_dir)
            config["claude"]["projects_path"] = str(claude_projects)
            config["codex"]["sessions_path"] = str(codex_sessions)

            checks = collect_local_doctor_checks(
                config,
                env={
                    "ARK_API_KEY": "ark-key",
                    "FEISHU_APP_ID": "app-id",
                    "FEISHU_APP_SECRET": "app-secret",
                    "FEISHU_REDIRECT_URI": "http://localhost:8080/callback",
                },
                port_checker=lambda host, port: port == 8080,
                endpoint_checker=lambda llm_config: (True, "endpoint ok"),
                now=1_900_000_000,
            )

        self.assertTrue(all(check["ok"] for check in checks), checks)
        self.assertEqual(
            [check["name"] for check in checks],
            [
                "Feishu app id/secret",
                "Feishu redirect URI",
                "OAuth callback port",
                "Feishu token",
                "Claude projects directory",
                "Codex sessions directory",
                "LLM endpoint",
            ],
        )

    def test_choose_callback_port_falls_back_when_8080_is_busy(self):
        port = choose_callback_port(
            "127.0.0.1",
            8080,
            port_checker=lambda host, candidate: candidate == 8082,
            max_attempts=5,
        )

        self.assertEqual(port, 8082)

    def test_rewrite_local_callback_uri_uses_fallback_port(self):
        redirect_uri = rewrite_local_callback_uri(
            "http://localhost:8080/callback",
            8082,
        )

        self.assertEqual(redirect_uri, "http://localhost:8082/callback")

    def test_rewrite_local_callback_uri_falls_back_for_unresolved_env_reference(self):
        redirect_uri = rewrite_local_callback_uri(
            "os.environ/FEISHU_REDIRECT_URI",
            8082,
        )

        self.assertEqual(redirect_uri, "http://localhost:8082/callback")

    def test_local_doctor_reports_actionable_failures(self):
        config = build_config()
        config["feishu"]["redirect_uri"] = "http://localhost:9999/callback"
        config["feishu"]["env_dir"] = "/tmp/daily-report-missing-token-dir"
        config["claude"]["projects_path"] = "/tmp/daily-report-missing-claude"
        config["codex"]["sessions_path"] = "/tmp/daily-report-missing-codex"

        checks = collect_local_doctor_checks(
            config,
            env={},
            port_checker=lambda host, port: False,
            endpoint_checker=lambda llm_config: (False, "missing api key"),
            now=1_900_000_000,
        )

        failed = {check["name"]: check["message"] for check in checks if not check["ok"]}
        self.assertIn("FEISHU_APP_ID", failed["Feishu app id/secret"])
        self.assertIn("http://localhost:8080/callback", failed["Feishu redirect URI"])
        self.assertIn("可用端口", failed["OAuth callback port"])
        self.assertIn("python -m feishu auth --callback", failed["Feishu token"])
        self.assertIn("不存在", failed["Claude projects directory"])
        self.assertIn("不存在", failed["Codex sessions directory"])
        self.assertIn("missing api key", failed["LLM endpoint"])


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

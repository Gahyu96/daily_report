#!/usr/bin/env python3
"""测试对比新旧两种方式获取消息数量"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from feishu.auth import FeishuAuthenticator
from feishu.collector import FeishuCollector
from daily_report import load_config


def main():
    config = load_config("config.yaml")
    feishu_config = config.get("feishu", {})

    # 初始化认证
    auth = FeishuAuthenticator(
        feishu_config["app_id"],
        feishu_config["app_secret"],
        feishu_config.get("env_dir", "~/.feishu_env"),
        feishu_config.get("redirect_uri", "http://localhost:8080/callback"),
        feishu_config.get("scope", "")
    )
    access_token = auth.get_access_token()

    collector = FeishuCollector(access_token, feishu_config.get("chat_cache_dir", "cache/feishu_chat_cache"))

    # 测试日期：2026-04-16
    date = datetime(2026, 4, 16)
    start_time = datetime(date.year, date.month, date.day, 0, 0, 0)
    end_time = datetime(date.year, date.month, date.day, 23, 59, 59)

    print("=" * 80)
    print("方式 1: 新智能并发策略 (smart_concurrency=True)")
    print("=" * 80)
    messages1 = collector.search_messages_enhanced(
        start_time=start_time,
        end_time=end_time,
        max_messages=10000,
        smart_concurrency=True
    )
    print(f"获取到 {len(messages1)} 条消息\n")

    print("=" * 80)
    print("方式 2: 旧时间切片策略 (smart_concurrency=False)")
    print("=" * 80)
    messages2 = collector.search_messages_enhanced(
        start_time=start_time,
        end_time=end_time,
        max_messages=10000,
        smart_concurrency=False
    )
    print(f"获取到 {len(messages2)} 条消息\n")

    print("=" * 80)
    print("对比结果")
    print("=" * 80)
    print(f"新策略: {len(messages1)} 条")
    print(f"旧策略: {len(messages2)} 条")
    print(f"差异: {len(messages2) - len(messages1)} 条")


if __name__ == "__main__":
    main()

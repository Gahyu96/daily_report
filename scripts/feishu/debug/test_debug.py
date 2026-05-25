#!/usr/bin/env python3
"""调试新策略的问题"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from feishu.auth import FeishuAuthenticator
from feishu.collector import FeishuCollector
from daily_report import load_config


def test_fetch_chat_type(collector, chat_type, start_time, end_time):
    """测试单独获取某个 chat_type"""
    print(f"\n--- 测试 chat_type={chat_type} ---")
    messages = []
    page_token = ""
    max_iterations = 200
    iterations = 0
    seen_message_ids = set()

    while iterations < max_iterations and len(messages) < 10000:
        iterations += 1
        print(f"  第 {iterations} 次请求, page_token={page_token or 'None'}")
        try:
            result = collector.search_messages(
                start_time=start_time,
                end_time=end_time,
                chat_type=chat_type,
                page_size=50,
                page_token=page_token if page_token else None
            )

            batch = result.get("messages", [])
            print(f"    本批次获取到 {len(batch)} 条消息")

            for msg in batch:
                msg_id = msg.get("message_id")
                if msg_id and msg_id not in seen_message_ids:
                    seen_message_ids.add(msg_id)
                    messages.append(msg)

            has_more = result.get("has_more", False)
            page_token = result.get("page_token", "")
            print(f"    has_more={has_more}, next_page_token={page_token or 'None'}")

            if not has_more or not page_token:
                print(f"  停止翻页")
                break

        except Exception as e:
            print(f"  异常: {e}")
            break

    print(f"  总计: {len(messages)} 条消息 (迭代 {iterations} 次)")
    return messages


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
    print("调试新策略")
    print("=" * 80)

    # 分别测试 group 和 p2p
    group_messages = test_fetch_chat_type(collector, "group", start_time, end_time)
    p2p_messages = test_fetch_chat_type(collector, "p2p", start_time, end_time)

    print("\n" + "=" * 80)
    print("汇总")
    print("=" * 80)
    print(f"group: {len(group_messages)} 条")
    print(f"p2p: {len(p2p_messages)} 条")
    print(f"总计: {len(group_messages) + len(p2p_messages)} 条")


if __name__ == "__main__":
    main()

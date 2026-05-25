#!/usr/bin/env python3
"""用 lark-cli 测试搜索消息"""
import subprocess
import json
import sys
from datetime import datetime, timedelta


def run_search(start, end, chat_type=None):
    """运行一次搜索"""
    cmd = [
        "lark-cli", "im", "+messages-search",
        "--start", start,
        "--end", end,
        "--page-size", "50",
        "--format", "json"
    ]
    if chat_type:
        cmd.extend(["--chat-type", chat_type])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return None
    return json.loads(result.stdout)


def main():
    # 测试日期
    date = "2026-04-16"
    start = f"{date}T00:00:00+08:00"
    end = f"{date}T23:59:59+08:00"

    print("=" * 80)
    print("测试 1: 不指定 chat-type")
    print("=" * 80)

    page_token = ""
    total = 0
    iterations = 0

    while iterations < 20:
        iterations += 1
        print(f"\n第 {iterations} 次请求, page_token={page_token or 'None'}")

        cmd = [
            "lark-cli", "im", "+messages-search",
            "--start", start,
            "--end", end,
            "--page-size", "50",
            "--format", "json"
        ]
        if page_token:
            cmd.extend(["--page-token", page_token])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            break

        data = json.loads(result.stdout)
        items = data.get("items", [])
        print(f"  获取到 {len(items)} 条")
        total += len(items)

        has_more = data.get("has_more", False)
        page_token = data.get("page_token", "")
        print(f"  has_more={has_more}, next_page_token={page_token or 'None'}")

        if not has_more or not page_token:
            print("  停止翻页")
            break

    print(f"\n总计: {total} 条")


if __name__ == "__main__":
    main()

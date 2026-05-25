#!/usr/bin/env python3
"""直接调用 search/v2/message API 测试"""
import subprocess
import json
from datetime import datetime, timedelta


def call_api(start_ts, end_ts, chat_type=None, page_token=None):
    """直接调用 search/v2/message API"""
    data = {
        "query": "",
        "start_time": start_ts,
        "end_time": end_ts
    }
    if chat_type:
        data["chat_type"] = chat_type

    params = {
        "user_id_type": "open_id",
        "page_size": 50
    }
    if page_token:
        params["page_token"] = page_token

    cmd = [
        "lark-cli", "api", "POST", "/open-apis/search/v2/message",
        "--params", json.dumps(params),
        "--data", json.dumps(data)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return None
    return json.loads(result.stdout)


def main():
    # 测试日期
    date = datetime(2026, 4, 16)
    start_dt = datetime(date.year, date.month, date.day, 0, 0, 0)
    end_dt = datetime(date.year, date.month, date.day, 23, 59, 59)

    start_ts = str(int(start_dt.timestamp()))
    end_ts = str(int(end_dt.timestamp()))

    print("=" * 80)
    print("测试 1: 不指定 chat_type")
    print("=" * 80)

    page_token = ""
    total = 0
    iterations = 0

    while iterations < 20:
        iterations += 1
        print(f"\n第 {iterations} 次请求, page_token={page_token or 'None'}")

        data = call_api(start_ts, end_ts, chat_type=None, page_token=page_token if page_token else None)
        if not data:
            break

        items = data.get("data", {}).get("items", [])
        print(f"  获取到 {len(items)} 条")
        total += len(items)

        has_more = data.get("data", {}).get("has_more", False)
        page_token = data.get("data", {}).get("page_token", "")
        print(f"  has_more={has_more}, next_page_token={page_token or 'None'}")

        if not has_more or not page_token:
            print("  停止翻页")
            break

    print(f"\n总计: {total} 条")

    print("\n" + "=" * 80)
    print("测试 2: 指定 chat_type=group_chat")
    print("=" * 80)

    page_token = ""
    total = 0
    iterations = 0

    while iterations < 20:
        iterations += 1
        print(f"\n第 {iterations} 次请求, page_token={page_token or 'None'}")

        data = call_api(start_ts, end_ts, chat_type="group_chat", page_token=page_token if page_token else None)
        if not data:
            break

        items = data.get("data", {}).get("items", [])
        print(f"  获取到 {len(items)} 条")
        total += len(items)

        has_more = data.get("data", {}).get("has_more", False)
        page_token = data.get("data", {}).get("page_token", "")
        print(f"  has_more={has_more}, next_page_token={page_token or 'None'}")

        if not has_more or not page_token:
            print("  停止翻页")
            break

    print(f"\n总计: {total} 条")

    print("\n" + "=" * 80)
    print("测试 3: 指定 chat_type=p2p_chat")
    print("=" * 80)

    page_token = ""
    total = 0
    iterations = 0

    while iterations < 20:
        iterations += 1
        print(f"\n第 {iterations} 次请求, page_token={page_token or 'None'}")

        data = call_api(start_ts, end_ts, chat_type="p2p_chat", page_token=page_token if page_token else None)
        if not data:
            break

        items = data.get("data", {}).get("items", [])
        print(f"  获取到 {len(items)} 条")
        total += len(items)

        has_more = data.get("data", {}).get("has_more", False)
        page_token = data.get("data", {}).get("page_token", "")
        print(f"  has_more={has_more}, next_page_token={page_token or 'None'}")

        if not has_more or not page_token:
            print("  停止翻页")
            break

    print(f"\n总计: {total} 条")


if __name__ == "__main__":
    main()

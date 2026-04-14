#!/usr/bin/env python3
"""
自动日报生成工具
"""
import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import yaml

from cache_manager import CacheManager
from collector import ClaudeCollector
from generator import ReportGenerator

# 新增导入
from feishu import FeishuAuthenticator, FeishuCollector, ChatFilter, FeishuDocExporter
from feishu.filter import ChatCategory
from feishu.auth import RefreshTokenExpiredError
from inheritance import TaskInheritanceManager


def load_config(config_path: str = "config.yaml") -> dict:
    """加载配置文件，支持 os.environ/VAR_NAME 格式引用环境变量"""
    import os

    def _resolve_value(value):
        """递归解析配置值中的环境变量引用"""
        if isinstance(value, str) and value.startswith("os.environ/"):
            env_var = value[len("os.environ/"):]
            return os.environ.get(env_var, value)
        elif isinstance(value, dict):
            return {k: _resolve_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [_resolve_value(v) for v in value]
        return value

    path = Path(config_path)
    if not path.exists():
        print(f"Warning: Config file not found: {config_path}, using defaults")
        config = {
            "claude": {
                "history_path": "~/.claude/history.jsonl",
                "projects_path": "~/.claude/projects",
            },
            "llm": {
                "arkplan_settings": "~/.claude/arkplan.json",
            },
            "report": {
                "base_dir": "reports",
            },
        }
    else:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

    # 递归解析所有环境变量引用
    config = _resolve_value(config)

    return config


def validate_feishu_config(config: dict) -> bool:
    """验证飞书配置是否完整"""
    feishu_config = config.get("feishu", {})
    if not feishu_config.get("enabled", False):
        return True  # 未启用，无需验证
    required_keys = ["app_id", "app_secret"]
    for key in required_keys:
        if not feishu_config.get(key):
            print(f"Warning: feishu.{key} 未配置，飞书集成将不可用")
            return False
    return True


def build_combined_text(structured_data: Dict[str, str]) -> str:
    """
    构建传给 LLM 的聚合文本，保留来源标识
    """
    parts = []
    if structured_data.get("claude_history"):
        parts.append("=== Claude 历史会话 ===\n" + structured_data["claude_history"])
    if structured_data.get("claude_projects"):
        parts.append("=== Claude 项目会话 ===\n" + structured_data["claude_projects"])
    if structured_data.get("feishu_chats"):
        parts.append("=== 飞书会话 ===\n" + structured_data["feishu_chats"])
    if structured_data.get("feishu_docs"):
        parts.append("=== 飞书文档 ===\n" + structured_data["feishu_docs"])
    if structured_data.get("feishu_calendar"):
        parts.append("=== 飞书日程 ===\n" + structured_data["feishu_calendar"])
    if structured_data.get("inherited_tasks"):
        parts.append(structured_data["inherited_tasks"])
    return "\n\n".join(parts)


def collect_all_sources(
    date: datetime,
    config: dict,
    force: bool = False
) -> Tuple[str, Dict[str, str]]:
    """
    收集所有数据源

    Returns: (聚合文本, 结构化数据字典)
    """
    cache_mgr = CacheManager()
    structured_data = {}
    parts = []

    # 1. Claude 历史会话
    claude_collector = ClaudeCollector(
        config["claude"]["history_path"],
        config["claude"]["projects_path"],
    )

    source = "claude_history"
    if force or not cache_mgr.has_cache(date, source):
        content = claude_collector.collect_history_for_date(date)
        session_count = content.count("\n--- 会话:") if content else 0
        # 计算时间范围
        time_range = claude_collector._get_time_range_from_content(content)
        metadata = {"条数": str(session_count)}
        if time_range:
            metadata["时间范围"] = time_range
        cache_mgr.write_cache(date, source, content, metadata)
    else:
        content = cache_mgr.read_cache(date, source) or ""
    structured_data[source] = content
    if content:
        parts.append("=== Claude 历史会话 ===\n" + content)

    # 2. Claude 项目会话
    source = "claude_projects"
    if force or not cache_mgr.has_cache(date, source):
        content = claude_collector.collect_projects_for_date(date)
        content = claude_collector._truncate_long_content(content)
        session_count = content.count("\n--- 会话:") if content else 0
        # 计算时间范围
        time_range = claude_collector._get_time_range_from_content(content)
        metadata = {"条数": str(session_count)}
        if time_range:
            metadata["时间范围"] = time_range
        cache_mgr.write_cache(date, source, content, metadata)
    else:
        content = cache_mgr.read_cache(date, source) or ""
    structured_data[source] = content
    if content:
        parts.append("=== Claude 项目会话 ===\n" + content)

    # 3. 飞书集成
    if config.get("feishu", {}).get("enabled", False) and validate_feishu_config(config):
        feishu_structured = collect_feishu_sources(date, config, cache_mgr, force)
        if feishu_structured:
            # 构建聚合文本并填充 structured_data
            if feishu_structured.get("feishu_chats"):
                structured_data["feishu_chats"] = feishu_structured["feishu_chats"]
                parts.append("=== 飞书会话 ===\n" + feishu_structured["feishu_chats"])
            if feishu_structured.get("feishu_docs"):
                structured_data["feishu_docs"] = feishu_structured["feishu_docs"]
                parts.append("=== 飞书文档 ===\n" + feishu_structured["feishu_docs"])
            if feishu_structured.get("feishu_calendar"):
                structured_data["feishu_calendar"] = feishu_structured["feishu_calendar"]
                parts.append("=== 飞书日程 ===\n" + feishu_structured["feishu_calendar"])

    # 4. 继承任务
    inheritance_mgr = TaskInheritanceManager(config["report"]["base_dir"])
    yesterday = date - timedelta(days=1)
    inherited_tasks = inheritance_mgr.get_incomplete_tasks_from_daily(yesterday)
    if inherited_tasks:
        tasks_text = inheritance_mgr._format_tasks_for_prompt(inherited_tasks)
        parts.append(tasks_text)
        structured_data["inherited_tasks"] = tasks_text

    combined_text = "\n\n".join(parts)
    return combined_text, structured_data


def collect_feishu_sources(date: datetime, config: dict, cache_mgr: CacheManager, force: bool = False) -> Dict[str, str]:
    """收集飞书数据源，返回结构化数据

    Returns: {
        "feishu_chats": "飞书会话内容",
        "feishu_docs": "飞书文档内容",
        "feishu_calendar": "飞书日程内容"
    }
    """
    result = {}
    feishu_config = config.get("feishu", {})

    # 认证
    auth = FeishuAuthenticator(
        feishu_config["app_id"],
        feishu_config["app_secret"],
        feishu_config.get("env_dir", "~/.feishu_env"),
        feishu_config.get("redirect_uri", "http://localhost:8080/callback"),
        feishu_config.get("scope", "")
    )
    try:
        access_token = auth.get_access_token()
    except RefreshTokenExpiredError:
        print("飞书 refresh_token 已过期，请重新运行 'python -m feishu auth' 授权")
        return result
    except Exception as e:
        print(f"飞书认证失败: {e}")
        return result

    collector = FeishuCollector(access_token, feishu_config.get("chat_cache_dir", "cache/feishu_chat_cache"))

    # 严格的目标日期时间范围
    target_start = datetime(date.year, date.month, date.day, 0, 0, 0)
    target_end = datetime(date.year, date.month, date.day, 23, 59, 59)

    # 1. 采集日程
    source = "feishu_calendar"
    if force or not cache_mgr.has_cache(date, source):
        t0 = time.time()
        try:
            calendar_content = collector.collect_calendar_for_date(date)
            event_count = calendar_content.count("## ") if calendar_content else 0
            metadata = {"条数": str(event_count)}
            cache_mgr.write_cache(date, source, calendar_content or "", metadata)
            if calendar_content:
                result[source] = calendar_content
        except Exception as e:
            print(f"Warning: Failed to collect calendar: {e}")
        print(f"  [feishu_calendar] {time.time()-t0:.1f}s")
    else:
        content = cache_mgr.read_cache(date, source) or ""
        if content:
            result[source] = content
        print(f"  [feishu_calendar] cache hit")

    # 预检查：是否需要获取飞书会话（聊天或文档任一需要更新时）
    need_sessions = force or not cache_mgr.has_cache(date, "feishu_chats") or not cache_mgr.has_cache(date, "feishu_docs")
    sessions = None
    summarizer = None
    if need_sessions:
        t0 = time.time()
        try:
            from feishu.summarizer import FeishuSummarizer
            summarizer = FeishuSummarizer(collector, config.get("llm", {}))
            sessions = summarizer.fetch_sessions_with_time_range(
                start_time=target_start,
                end_time=target_end,
                max_messages=10000,
                use_enhanced=True
            )
            total_msgs = sum(len(s.messages) for s in sessions) if sessions else 0
            print(f"  [fetch_sessions] {time.time()-t0:.1f}s, {len(sessions) if sessions else 0} 会话 {total_msgs} 消息")
        except Exception as e:
            print(f"Warning: Failed to fetch feishu sessions: {e}")

    # 2. 采集并格式化原始飞书会话（带时间戳）
    source = "feishu_chats"
    filtered_source = "feishu_chats_filtered"
    if force or not cache_mgr.has_cache(date, source):
        t0 = time.time()
        try:
            if sessions is not None:
                chats_content = format_feishu_chats_with_timestamps(sessions, target_start, target_end, collector)
                if chats_content.strip():
                    message_count = chats_content.count("\n[")
                    metadata = {"条数": str(message_count)}
                    time_range = extract_time_range_from_chats(chats_content)
                    if time_range:
                        metadata["时间范围"] = time_range
                    cache_mgr.write_cache(date, source, chats_content, metadata)
                    result[source] = chats_content
        except Exception as e:
            print(f"Warning: Failed to collect feishu chats: {e}")
        print(f"  [feishu_chats] {time.time()-t0:.1f}s")
    else:
        content = cache_mgr.read_cache(date, source) or ""
        if content:
            result[source] = content
        print(f"  [feishu_chats] cache hit")

    # 3. 过滤并分类聊天记录，标记与我相关的内容
    if result.get("feishu_chats"):
        t0 = time.time()
        try:
            chat_filter = ChatFilter(config["llm"]["arkplan_settings"])
            chat_content = result["feishu_chats"]
            sessions = chat_filter._split_into_sessions(chat_content)
            filtered_parts = []
            stats = {
                ChatCategory.ALERT_GROUP: 0,
                ChatCategory.INVALID_CHAT: 0,
                ChatCategory.VALID_GROUP: 0,
                ChatCategory.VALID_DIRECT: 0,
                ChatCategory.UNKNOWN: 0
            }
            for session_header, session_content in sessions:
                category = chat_filter._classify_session(session_header, session_content)
                stats[category] += 1
                if category == ChatCategory.INVALID_CHAT:
                    continue
                if category == ChatCategory.ALERT_GROUP:
                    alert_summary = chat_filter._summarize_alerts(session_header, session_content)
                    if alert_summary:
                        filtered_parts.append(alert_summary)
                    continue
                # 有效内容：标记与我相关的消息（👤 我发的，📌 @我的）
                marked_content = chat_filter._mark_relevant_messages(session_header, session_content)
                filtered_parts.append(marked_content)
            filtered_content = "\n\n".join(filtered_parts)
            if filtered_content.strip():
                metadata = {
                    "告警群": str(stats[ChatCategory.ALERT_GROUP]),
                    "无效闲聊": str(stats[ChatCategory.INVALID_CHAT]),
                    "有效群聊": str(stats[ChatCategory.VALID_GROUP]),
                    "有效私聊": str(stats[ChatCategory.VALID_DIRECT])
                }
                cache_mgr.write_cache(date, filtered_source, filtered_content, metadata)
                result["feishu_chats"] = filtered_content  # 用过滤后的内容替换原始内容
                print(f"  [feishu_chats_filtered] 分类结果:告警群{stats[ChatCategory.ALERT_GROUP]}/无效{stats[ChatCategory.INVALID_CHAT]}/有效群{stats[ChatCategory.VALID_GROUP]}/有效私{stats[ChatCategory.VALID_DIRECT]}")
        except Exception as e:
            print(f"Warning: Failed to filter feishu chats, using original: {e}")
        print(f"  [feishu_chats_filter] {time.time()-t0:.1f}s")

    # 3. 采集飞书文档
    source = "feishu_docs"
    if force or not cache_mgr.has_cache(date, source):
        t0 = time.time()
        all_doc_urls = []
        try:
            if sessions is not None:
                for session in sessions:
                    for msg in session.messages:
                        content = msg.get("content", "")
                        links = collector.extract_doc_links_from_text(content)
                        all_doc_urls.extend(links)

            # 从智能纪要助手消息中提取文档链接
            t1 = time.time()
            minutes_messages = collector.search_minutes_assistant_messages(days=1)
            print(f"  [minutes_assistant] {time.time()-t1:.1f}s, {len(minutes_messages)} 条")
            for msg in minutes_messages:
                extracted_links = msg.get("extracted_doc_links", [])
                all_doc_urls.extend(extracted_links)

            # 从飞书 Drive 获取最近文档
            t1 = time.time()
            drive_docs = collector.get_recent_docs_from_drive(date=date, days=1)
            print(f"  [drive_docs] {time.time()-t1:.1f}s, {len(drive_docs)} 个文档")
            all_doc_urls.extend([d.doc_url for d in drive_docs])

            # 去重
            unique_doc_urls = list(dict.fromkeys(all_doc_urls))
            print(f"  [doc_urls] 共 {len(unique_doc_urls)} 个唯一文档链接")

            if unique_doc_urls:
                exporter = FeishuDocExporter(
                    feishu_config.get("temp_dir", "/tmp/feishu_docs"),
                    config["llm"]["arkplan_settings"],
                    feishu_config.get("doc_summary_threshold", 3500),
                    feishu_config.get("doc_cache_dir", "cache/feishu_doc_cache"),
                    feishu_config.get("doc_cache_ttl_days", 7),
                    feishu_config
                )
                try:
                    t1 = time.time()
                    doc_contents = exporter.export_docs(unique_doc_urls)
                    print(f"  [export_docs] {time.time()-t1:.1f}s, 导出 {len(doc_contents)} 个")
                finally:
                    exporter.cleanup()

                if doc_contents:
                    docs_parts = []
                    for url, content in doc_contents.items():
                        docs_parts.append(f"--- {url} ---\n{content}")
                    docs_content = "\n\n".join(docs_parts)
                    metadata = {"条数": str(len(doc_contents))}
                    cache_mgr.write_cache(date, source, docs_content, metadata)
                    result[source] = docs_content
        except Exception as e:
            print(f"Warning: Failed to collect feishu docs: {e}")
        print(f"  [feishu_docs] total {time.time()-t0:.1f}s")
    else:
        content = cache_mgr.read_cache(date, source) or ""
        if content:
            result[source] = content
        print(f"  [feishu_docs] cache hit")

    return result


def format_feishu_chats_with_timestamps(sessions, target_start: datetime, target_end: datetime, collector=None) -> str:
    """格式化飞书会话，带时间戳，只保留目标日期的消息"""
    lines = []

    for session in sessions:
        chat_type_label = "群聊" if session.chat_type == "group" else "私聊"
        lines.append(f"## {chat_type_label}：{session.chat_name}")

        # 过滤并排序消息
        filtered_messages = []
        for msg in session.messages:
            try:
                create_time_str = msg.get("create_time", "")
                if create_time_str:
                    # 兼容两种格式：带 Z 的 UTC 时间 和 带 +08:00 的北京时间
                    if create_time_str.endswith('Z'):
                        msg_time = datetime.fromisoformat(create_time_str.replace('Z', '+00:00'))
                    else:
                        msg_time = datetime.fromisoformat(create_time_str)
                    # 转换为本地时间比较（去掉时区信息）
                    msg_time_local = msg_time.replace(tzinfo=None)
                    if target_start <= msg_time_local <= target_end:
                        filtered_messages.append((msg_time_local, msg))
            except (ValueError, TypeError) as e:
                continue

        # 按时间排序
        filtered_messages.sort(key=lambda x: x[0])

        for msg_time, msg in filtered_messages:
            time_str = msg_time.strftime("%H:%M:%S")
            sender = msg.get("sender", {})
            sender_name = sender.get("name", "未知用户")

            # 消息内容已经在 _format_search_message_item 中解析过了
            content = msg.get("content", "")

            # 截断过长内容
            if len(content) > 500:
                content = content[:500] + "...[截断]"
            lines.append(f"[{time_str}] {sender_name}: {content}")

        lines.append("")

    return "\n".join(lines)


def extract_time_range_from_chats(chats_content: str) -> Optional[str]:
    """从格式化的聊天内容中提取时间范围"""
    import re
    time_pattern = r'\[(\d{2}:\d{2}:\d{2})\]'
    times = re.findall(time_pattern, chats_content)
    if times:
        return f"{times[0]} ~ {times[-1]}"
    return None


def get_dates_to_process(args) -> list:
    """获取要处理的日期列表"""
    dates = []

    if args.yesterday:
        # 昨天
        yesterday = datetime.now() - timedelta(days=1)
        dates.append(datetime(yesterday.year, yesterday.month, yesterday.day))
    elif args.date:
        # 指定日期
        try:
            date = datetime.strptime(args.date, "%Y-%m-%d")
            dates.append(date)
        except ValueError as e:
            print(f"Error: Invalid date format: {args.date}, use YYYY-MM-DD")
            sys.exit(1)
    elif args.start and args.end:
        # 日期范围
        try:
            start = datetime.strptime(args.start, "%Y-%m-%d")
            end = datetime.strptime(args.end, "%Y-%m-%d")
            current = start
            while current <= end:
                dates.append(current)
                current += timedelta(days=1)
        except ValueError as e:
            print(f"Error: Invalid date format: {e}")
            sys.exit(1)
    else:
        # 默认：今天
        today = datetime.now()
        dates.append(datetime(today.year, today.month, today.day))

    return dates


def main():
    parser = argparse.ArgumentParser(description="自动日报生成工具")

    # 日期选项
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument(
        "--date", "-d",
        help="生成指定日期的日报 (YYYY-MM-DD)",
    )
    date_group.add_argument(
        "--yesterday", "-y",
        action="store_true",
        help="生成昨天的日报",
    )
    date_group.add_argument(
        "--start",
        help="日期范围开始 (YYYY-MM-DD)",
    )
    date_group.add_argument(
        "--weekly",
        help="生成周报 (YYYY-Www, 如 2026-W12)",
    )
    date_group.add_argument(
        "--monthly",
        help="生成月报 (YYYY-MM, 如 2026-03)",
    )

    parser.add_argument(
        "--end",
        help="日期范围结束 (YYYY-MM-DD, 需要配合 --start 使用)",
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细日志",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="强制重新生成，即使已存在",
    )

    args = parser.parse_args()

    # 验证 --start/--end
    if args.start and not args.end:
        print("Error: --end is required when using --start")
        sys.exit(1)
    if args.end and not args.start:
        print("Error: --start is required when using --end")
        sys.exit(1)

    # 加载配置
    config = load_config(args.config)

    # 创建 collector 和 generator
    collector = ClaudeCollector(
        config["claude"]["history_path"],
        config["claude"]["projects_path"],
    )
    generator = ReportGenerator(
        config["llm"]["arkplan_settings"],
        config["report"]["base_dir"],
    )

    # 周报
    if args.weekly:
        try:
            # 解析 YYYY-Www
            year_str, week_str = args.weekly.split("-W")
            year = int(year_str)
            week = int(week_str)
            generator.generate_weekly(year, week)
        except Exception as e:
            print(f"Error: Failed to generate weekly report: {e}")
            sys.exit(1)
        return

    # 月报
    if args.monthly:
        try:
            # 解析 YYYY-MM
            year_str, month_str = args.monthly.split("-")
            year = int(year_str)
            month = int(month_str)
            generator.generate_monthly(year, month)
        except Exception as e:
            print(f"Error: Failed to generate monthly report: {e}")
            sys.exit(1)
        return

    # 日报
    dates = get_dates_to_process(args)

    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        print(f"Processing {date_str}...")

        # 检查是否已存在
        if not args.force and generator.daily_report_exists(date):
            print(f"  Skipped: already exists")
            continue

        # 采集所有数据源
        t0 = time.time()
        conversation_text, structured_data = collect_all_sources(date, config, args.force)
        collect_elapsed = time.time() - t0
        if args.verbose:
            print(f"  Collected {len(conversation_text)} chars of content ({collect_elapsed:.1f}s)")
            print(f"  Sources: {list(structured_data.keys())}")

        # 生成日报
        t0 = time.time()
        output_path = generator.generate_daily(date, conversation_text)
        print(f"  Generated: {output_path} (LLM {time.time()-t0:.1f}s)")

    print("\nDone!")


if __name__ == "__main__":
    main()

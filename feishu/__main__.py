"""
飞书模块入口，支持 python -m feishu 命令
"""
import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from feishu.auth import FeishuAuthenticator, RefreshTokenExpiredError
from feishu.collector import FeishuCollector
from daily_report import load_config


def search_messages(config, query=None, relative_time="today", page_size=20):
    """搜索飞书消息"""
    feishu_config = config.get("feishu", {})

    auth = FeishuAuthenticator(
        feishu_config["app_id"],
        feishu_config["app_secret"],
        feishu_config.get("env_dir", "~/.feishu_env"),
        feishu_config.get("redirect_uri", "http://localhost:8080/callback"),
        feishu_config.get("scope", "")
    )
    try:
        access_token = auth.get_access_token()
    except Exception as e:
        print(f"飞书认证失败: {e}")
        sys.exit(1)

    print("="*80)
    print(f"飞书消息搜索")
    print(f"  时间范围: {relative_time}")
    if query:
        print(f"  关键词: {query}")
    print("="*80)

    collector = FeishuCollector(access_token, feishu_config.get("chat_cache_dir", "cache/feishu_chat_cache"))

    try:
        result = collector.search_messages(
            query=query,
            relative_time=relative_time,
            page_size=page_size
        )

        print(f"\n找到 {len(result['messages'])} 条消息")
        if result.get('has_more'):
            print("(还有更多消息，可使用分页获取)")

        # 按会话分组显示
        chat_groups = {}
        for msg in result['messages']:
            chat_key = (msg.get('chat_id', 'unknown'), msg.get('chat_name', '未知会话'))
            if chat_key not in chat_groups:
                chat_groups[chat_key] = []
            chat_groups[chat_key].append(msg)

        for (chat_id, chat_name), msgs in chat_groups.items():
            print(f"\n{'='*80}")
            print(f"会话: {chat_name} (chat_id: {chat_id})")
            print(f"{'='*80}")

            for msg in msgs:
                sender = msg.get('sender', {})
                sender_name = sender.get('name', sender.get('id', '未知'))
                create_time = msg.get('create_time', '')
                content = msg.get('content', '')

                print(f"\n[{create_time}] {sender_name}:")
                print(f"  {content}")

    except Exception as e:
        print(f"搜索失败: {e}")
        import traceback
        traceback.print_exc()


def summarize_sessions(config, days=2, limit=10000, output=None):
    """独立会话总结命令"""
    feishu_config = config.get("feishu", {})

    # 初始化认证
    auth = FeishuAuthenticator(
        feishu_config["app_id"],
        feishu_config["app_secret"],
        feishu_config.get("env_dir", "~/.feishu_env"),
        feishu_config.get("redirect_uri", "http://localhost:8080/callback"),
        feishu_config.get("scope", "")
    )
    try:
        access_token = auth.get_access_token()
    except Exception as e:
        print(f"飞书认证失败: {e}")
        sys.exit(1)

    # 初始化 collector 和 summarizer
    from feishu.summarizer import FeishuSummarizer
    collector = FeishuCollector(
        access_token=access_token,
        cache_base_dir=feishu_config.get("chat_cache_dir", "cache/feishu_chat_cache")
    )
    summarizer = FeishuSummarizer(collector, config.get("llm", {}))

    print("=" * 80)
    print(f"飞书会话总结")
    print(f"  时间范围: 最近 {days} 天")
    print(f"  消息上限: {limit} 条")
    print("=" * 80)

    # 获取会话
    print("\n[1/3] 获取会话...")
    sessions = summarizer.fetch_sessions(days=days, max_messages=limit)
    print(f"找到 {len(sessions)} 个会话")

    # 按主题聚合
    print("\n[2/3] 按主题聚合...")
    topics = summarizer.group_by_topic(sessions)
    print(f"生成 {len(topics)} 个主题")

    # 格式化输出
    print("\n[3/3] 生成总结...")
    summary_text, extracted = summarizer.format_for_daily_report(topics)

    output_content = []
    output_content.append("# 飞书会话总结\n")
    output_content.append(f"- 时间范围: 最近 {days} 天")
    output_content.append(f"- 会话数: {len(sessions)}")
    output_content.append(f"- 主题数: {len(topics)}")
    output_content.append("")
    output_content.append(summary_text)

    final_output = "\n".join(output_content)

    # 输出
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_output)
        print(f"\n总结已保存到: {output_path}")
    else:
        print("\n" + final_output)


def collect_and_display_data(config, date_str=None):
    """收集并显示所有飞书数据"""
    feishu_config = config.get("feishu", {})

    auth = FeishuAuthenticator(
        feishu_config["app_id"],
        feishu_config["app_secret"],
        feishu_config.get("env_dir", "~/.feishu_env"),
        feishu_config.get("redirect_uri", "http://localhost:8080/callback"),
        feishu_config.get("scope", "")
    )
    try:
        access_token = auth.get_access_token()
    except Exception as e:
        print(f"飞书认证失败: {e}")
        sys.exit(1)

    if date_str:
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            print(f"错误: 日期格式无效 {date_str}，请使用 YYYY-MM-DD")
            sys.exit(1)
    else:
        date = datetime.now() - timedelta(days=1)

    print("="*80)
    print(f"飞书数据采集 - 目标日期: {date.strftime('%Y-%m-%d')}")
    print("="*80)

    collector = FeishuCollector(access_token, feishu_config.get("chat_cache_dir", "cache/feishu_chat_cache"))

    # 1. 聊天记录
    print("\n" + "="*80)
    print("1. 聊天记录")
    print("="*80)
    try:
        cache_path = collector.collect_chat_for_date(date, force=True)
        print(f"\n缓存文件: {cache_path}")
        if cache_path.exists():
            print("\n" + "-"*80)
            print("聊天内容:")
            print("-"*80)
            with open(cache_path, "r", encoding="utf-8") as f:
                content = f.read()
                print(content if content else "(空)")
    except Exception as e:
        print(f"收集聊天记录失败: {e}")

    # 2. 日历日程
    print("\n" + "="*80)
    print("2. 日历日程")
    print("="*80)
    try:
        calendar_content = collector.collect_calendar_for_date(date)
        print("\n" + (calendar_content if calendar_content else "(空)"))
    except Exception as e:
        print(f"收集日历失败: {e}")

    # 3. 文档链接
    print("\n" + "="*80)
    print("3. 飞书文档链接")
    print("="*80)
    try:
        cache_path = collector.cache_base_dir / f"{date.strftime('%Y-%m-%d')}.md"
        doc_links = collector.extract_doc_links_from_chat(cache_path)
        if doc_links:
            print(f"\n找到 {len(doc_links)} 个文档链接:")
            for link in doc_links:
                print(f"  - {link}")
        else:
            print("\n(无)")
    except Exception as e:
        print(f"提取文档链接失败: {e}")

    # 4. 最近访问文档（简化）
    print("\n" + "="*80)
    print("4. 最近访问文档")
    print("="*80)
    print("(简化实现: 暂未实现完整的最近访问文档获取)")

    # 5. 智能纪要（简化）
    print("\n" + "="*80)
    print("5. 智能纪要")
    print("="*80)
    print("(简化实现: 暂未实现完整的智能纪要获取)")

    print("\n" + "="*80)
    print("采集完成!")
    print("="*80)


def check_token_status(config):
    """检查 token 状态"""
    feishu_config = config.get("feishu", {})

    auth = FeishuAuthenticator(
        feishu_config["app_id"],
        feishu_config["app_secret"],
        feishu_config.get("env_dir", "~/.feishu_env"),
        feishu_config.get("redirect_uri", "http://localhost:8080/callback"),
        feishu_config.get("scope", "")
    )

    token_data = auth._load_token_cache()
    if not token_data:
        print("❌ 未找到 token 缓存，请先运行 'python -m feishu auth' 进行授权")
        return

    now = int(time.time())
    print("="*80)
    print("飞书 Token 状态")
    print("="*80)

    # Access token 状态
    access_expires_in = token_data["expires_at"] - now
    if access_expires_in > 0:
        print(f"✅ Access Token: 有效 (剩余 {access_expires_in//3600} 小时 {access_expires_in%3600//60} 分钟)")
        print(f"   过期时间: {datetime.fromtimestamp(token_data['expires_at'])}")
    else:
        print(f"❌ Access Token: 已过期 (过期 {abs(access_expires_in)//3600} 小时 {abs(access_expires_in)%3600//60} 分钟)")
        print(f"   过期时间: {datetime.fromtimestamp(token_data['expires_at'])}")

    # Refresh token 状态
    refresh_expires_in = token_data["refresh_expires_at"] - now
    if refresh_expires_in > 0:
        print(f"✅ Refresh Token: 有效 (剩余 {refresh_expires_in//86400} 天 {refresh_expires_in%86400//3600} 小时)")
        print(f"   过期时间: {datetime.fromtimestamp(token_data['refresh_expires_at'])}")
    else:
        print(f"❌ Refresh Token: 已过期 (过期 {abs(refresh_expires_in)//86400} 天 {abs(refresh_expires_in)%86400//3600} 小时)")
        print(f"   过期时间: {datetime.fromtimestamp(token_data['refresh_expires_at'])}")

    print("="*80)
    if refresh_expires_in > 0 and refresh_expires_in < 86400 * 7:
        print("⚠️  警告: Refresh Token 将在 7 天内过期，请及时刷新！")
    elif refresh_expires_in <= 0:
        print("❌ Refresh Token 已过期，请重新运行 'python -m feishu auth' 进行授权")


def main():
    parser = argparse.ArgumentParser(description="飞书工具")
    parser.add_argument("command", choices=["auth", "refresh", "status", "collect", "search", "summarize"], help="命令: auth-首次授权, refresh-刷新token, status-查看token状态, collect-收集并显示数据, search-搜索消息, summarize-会话总结")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--date", help="收集数据的日期 (YYYY-MM-DD)，默认昨天")
    parser.add_argument("--query", help="搜索关键词 (search 命令使用)")
    parser.add_argument("--time", default="today", help="时间范围: today/yesterday/this_week/last_week/last_3_days 等 (search 命令使用)")
    parser.add_argument("--limit", type=int, default=20, help="结果数量限制 (search 命令使用) / 最多 N 条消息 (summarize 命令使用)")
    parser.add_argument("--days", type=int, default=2, help="获取最近 N 天 (summarize 命令使用)")
    parser.add_argument("--output", help="输出文件路径 (summarize 命令使用)")
    parser.add_argument("-q", "--quiet", action="store_true", help="静默模式，只输出错误信息（适合 crontab）")
    args = parser.parse_args()

    config = load_config(args.config)
    feishu_config = config.get("feishu", {})

    if not feishu_config:
        print("错误: 配置文件中未找到 feishu 配置")
        sys.exit(1)

    if args.command == "collect":
        collect_and_display_data(config, args.date)
        return
    elif args.command == "search":
        search_messages(config, query=args.query, relative_time=args.time, page_size=args.limit)
        return
    elif args.command == "summarize":
        summarize_sessions(config, days=args.days, limit=args.limit, output=args.output)
        return
    elif args.command == "status":
        check_token_status(config)
        return

    auth = FeishuAuthenticator(
        feishu_config["app_id"],
        feishu_config["app_secret"],
        feishu_config.get("env_dir", "~/.feishu_env"),
        feishu_config.get("redirect_uri", "http://localhost:8080/callback"),
        feishu_config.get("scope", "")
    )

    if args.command == "auth":
        url = auth.get_authorization_url()
        print(f"请访问以下 URL 进行授权:\n{url}")
        code = input("请输入授权码: ")
        token_data = auth.exchange_code_for_token(code)
        print(f"授权成功! Token 已保存")
        print(f"Access token 过期时间: {datetime.fromtimestamp(token_data['expires_at'])}")
        print(f"Refresh token 过期时间: {datetime.fromtimestamp(token_data['refresh_expires_at'])}")
    elif args.command == "refresh":
        try:
            token_data = auth.refresh_access_token()
            if not args.quiet:
                print(f"Token 刷新成功!")
                print(f"Access token 新过期时间: {datetime.fromtimestamp(token_data['expires_at'])}")
                print(f"Refresh token 过期时间: {datetime.fromtimestamp(token_data['refresh_expires_at'])}")
            else:
                # 静默模式下只在出错时输出，成功不输出
                pass
        except RefreshTokenExpiredError:
            print("错误: refresh_token 已过期，请重新运行 'python -m feishu auth' 进行授权")
            sys.exit(1)


if __name__ == "__main__":
    main()

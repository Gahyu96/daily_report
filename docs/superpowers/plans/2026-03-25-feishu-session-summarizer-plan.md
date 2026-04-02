# 飞书会话总结功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现飞书会话总结功能，包括用户缓存、批量消息获取、主题聚合、独立命令和日报集成

**Architecture:** 渐进式增强方案 - 增强现有 FeishuCollector，新增 FeishuSummarizer 类，新增 summarize 命令，集成到日报流程

**Tech Stack:** Python, lark-oapi (飞书 SDK), requests, LLM API

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `feishu/collector.py` | 修改 | 增强用户缓存机制 + 添加批量用户/消息获取 |
| `feishu/summarizer.py` | 新建 | 会话分组 + 主题聚合 + 格式化 |
| `feishu/__main__.py` | 修改 | 添加 summarize 命令 |
| `daily_report.py` | 修改 | 集成会话总结到日报流程 |

---

## 实现任务

### Task 1: 增强 FeishuCollector - 用户缓存机制

**Files:**
- Modify: `feishu/collector.py:1-60` (顶部添加 UserInfo dataclass)
- Modify: `feishu/collector.py:48-58` (修改 `__init__` 中的缓存初始化)

- [ ] **Step 1: 添加 UserInfo dataclass**

在文件顶部 import 之后添加：

```python
@dataclass
class UserInfo:
    name: str
    updated_at: float  # timestamp in seconds
```

- [ ] **Step 2: 修改 `__init__` 中的缓存初始化**

修改 `FeishuCollector.__init__`：

```python
# 修改前
self._user_cache: Dict[str, str] = {}

# 修改后
self._user_cache: Dict[str, UserInfo] = {}
```

- [ ] **Step 3: 更新使用缓存的地方**

搜索 `self._user_cache\[` 并更新所有使用点：

```python
# 查找: self._user_cache[sender_id] = name
# 替换为: self._user_cache[sender_id] = UserInfo(name=name, updated_at=time.time())

# 查找: if sender_id in self._user_cache:
# 替换为: if sender_id in self._user_cache:
#        name = self._user_cache[sender_id].name
```

- [ ] **Step 4: 验证语法**

Run: `python -m py_compile feishu/collector.py`
Expected: No syntax errors

- [ ] **Step 5: Commit**

```bash
git add feishu/collector.py
git commit -m "feat: enhance user cache with UserInfo dataclass"
```

---

### Task 2: 实现批量获取用户 API (contact/v3/user/basic_batch)

**Files:**
- Modify: `feishu/collector.py` (添加 `_ensure_users_basic` 方法)

- [ ] **Step 1: 添加 `_ensure_users_basic` 方法**

在 `FeishuCollector` 类中添加新方法（建议放在 `_batch_get_user_names` 之后）：

```python
def _ensure_users_basic(self, user_ids: List[str]) -> None:
    """
    批量获取用户基本信息（使用 contact/v3/user/basic_batch）
    自动跳过已缓存且未过期的用户
    """
    if not user_ids:
        return

    now = time.time()
    cache_ttl = 30 * 60  # 30分钟缓存
    uncached_ids = []

    for uid in user_ids:
        if not uid:
            continue
        if uid not in self._user_cache:
            uncached_ids.append(uid)
        elif (now - self._user_cache[uid].updated_at) > cache_ttl:
            uncached_ids.append(uid)

    if not uncached_ids:
        return

    # 去重
    uncached_ids = list(dict.fromkeys(uncached_ids))

    url = "https://open.feishu.cn/open-apis/contact/v3/users/basic_batch"
    headers = {"Authorization": f"Bearer {self.access_token}"}

    # 分批请求，每批最多 50 个
    batch_size = 50
    for i in range(0, len(uncached_ids), batch_size):
        batch = uncached_ids[i:i+batch_size]
        try:
            resp = requests.post(url, headers=headers, json={
                "user_ids": batch,
                "user_id_type": "open_id"
            }, timeout=30)
            data = resp.json()

            if data.get("code") == 0:
                items = data.get("data", {}).get("items", [])
                for item in items:
                    user = item.get("user", {})
                    open_id = user.get("open_id", "")
                    name = user.get("name", "")
                    if open_id and name:
                        self._user_cache[open_id] = UserInfo(
                            name=name,
                            updated_at=time.time()
                        )
            else:
                print(f"Warning: basic_batch API error: {data}")

        except Exception as e:
            print(f"Warning: Failed to fetch users batch: {e}")
```

- [ ] **Step 2: 验证语法**

Run: `python -m py_compile feishu/collector.py`
Expected: No syntax errors

- [ ] **Step 3: Commit**

```bash
git add feishu/collector.py
git commit -m "feat: add _ensure_users_basic method using contact/v3/user/basic_batch"
```

---

### Task 3: 实现批量获取消息 (search_messages_all)

**Files:**
- Modify: `feishu/collector.py` (添加 `search_messages_all` 方法)

- [ ] **Step 1: 添加 `search_messages_all` 方法**

在 `search_messages` 方法之后添加：

```python
def search_messages_all(
    self,
    days: int = 2,
    max_messages: int = 10000
) -> List[Dict]:
    """
    分页获取所有消息

    Args:
        days: 获取最近几天的消息
        max_messages: 最多获取多少条消息

    Returns:
        消息列表
    """
    all_messages = []
    page_token = ""
    iterations = 0
    max_iterations = (max_messages // 100) + 2  # 安全边界

    while len(all_messages) < max_messages and iterations < max_iterations:
        iterations += 1

        try:
            result = self.search_messages(
                relative_time=f"last_{days}_days",
                page_size=min(100, max_messages - len(all_messages)),
                page_token=page_token if page_token else None
            )

            messages = result.get("messages", [])
            if not messages:
                break

            all_messages.extend(messages)

            has_more = result.get("has_more", False)
            page_token = result.get("page_token", "")

            if not has_more or not page_token:
                break

        except Exception as e:
            print(f"Warning: search iteration failed: {e}")
            break

    print(f"Total messages fetched: {len(all_messages)}")
    return all_messages[:max_messages]
```

- [ ] **Step 2: 验证语法**

Run: `python -m py_compile feishu/collector.py`
Expected: No syntax errors

- [ ] **Step 3: Commit**

```bash
git add feishu/collector.py
git commit -m "feat: add search_messages_all method for paginated fetch"
```

---

### Task 4: 新建 FeishuSummarizer 类

**Files:**
- Create: `feishu/summarizer.py`

- [ ] **Step 1: 创建 `feishu/summarizer.py` 文件**

```python
"""
飞书会话总结模块
"""
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple


@dataclass
class ChatSession:
    chat_id: str
    chat_name: str
    chat_type: str  # "group" or "p2p"
    messages: List[Dict]
    p2p_partner: Optional[Dict] = None  # 私聊时对方信息


@dataclass
class TopicSummary:
    topic_name: str
    related_sessions: List[ChatSession]
    summary: str
    key_points: List[str]
    action_items: List[str]


class FeishuSummarizer:
    def __init__(self, collector: Any, llm_config: Optional[Dict] = None):
        self.collector = collector
        self.llm_config = llm_config or {}

    def fetch_sessions(
        self,
        days: int = 2,
        max_messages: int = 10000
    ) -> List[ChatSession]:
        """
        获取并按会话分组消息

        Returns:
            ChatSession 列表
        """
        # 获取所有消息
        messages = self.collector.search_messages_all(days=days, max_messages=max_messages)

        # 收集所有用户 ID 并补充信息
        user_ids = set()
        for msg in messages:
            sender = msg.get("sender", {})
            sender_id = sender.get("id", "")
            if sender_id:
                user_ids.add(sender_id)
            # 从 mentions 中收集
            for mention in msg.get("mentions", []):
                mention_id = mention.get("id", "")
                if mention_id:
                    user_ids.add(mention_id)

        # 批量补充用户信息
        if user_ids:
            self.collector._ensure_users_basic(list(user_ids))

        # 按 chat_id 分组
        chat_groups: Dict[str, List[Dict]] = {}
        for msg in messages:
            chat_id = msg.get("chat_id", "")
            if not chat_id:
                continue
            if chat_id not in chat_groups:
                chat_groups[chat_id] = []
            chat_groups[chat_id].append(msg)

        # 构建 ChatSession 对象
        sessions = []
        for chat_id, msgs in chat_groups.items():
            # 获取会话信息
            chat_name = ""
            chat_type = "unknown"
            p2p_partner = None

            if msgs:
                first_msg = msgs[0]
                chat_name = first_msg.get("chat_name", "")
                chat_type = first_msg.get("chat_type", "unknown")

                if chat_type == "p2p":
                    p2p_partner = first_msg.get("chat_partner")

            sessions.append(ChatSession(
                chat_id=chat_id,
                chat_name=chat_name or f"会话 {chat_id[:12]}...",
                chat_type=chat_type,
                messages=msgs,
                p2p_partner=p2p_partner
            ))

        return sessions

    def group_by_topic(self, sessions: List[ChatSession]) -> List[TopicSummary]:
        """
        按主题聚合并调用 LLM 生成总结（占位实现）

        Returns:
            TopicSummary 列表
        """
        # TODO: 实际实现需要调用 LLM
        # 这里是占位实现：每个会话作为一个主题
        topics = []

        for session in sessions:
            # 简单提取前几条消息作为摘要
            msg_samples = session.messages[:5]
            summary_lines = []
            for msg in msg_samples:
                sender = msg.get("sender", {})
                sender_name = sender.get("name", sender.get("id", "未知"))
                content = msg.get("content", "")[:100]
                summary_lines.append(f"{sender_name}: {content}")

            topics.append(TopicSummary(
                topic_name=session.chat_name,
                related_sessions=[session],
                summary="\n".join(summary_lines),
                key_points=[],
                action_items=[]
            ))

        return topics

    def format_for_daily_report(
        self,
        topics: List[TopicSummary]
    ) -> Tuple[str, Dict]:
        """
        格式化为日报内容

        Returns:
            (独立章节文本, 提取到各章节的字典)
            提取字典结构: {
                "key_progress": [...],
                "action_items": [...],
                "problems": [...]
            }
        """
        # 生成独立章节
        section_lines = []
        for topic in topics:
            section_lines.append(f"### {topic.topic_name}")
            section_lines.append("")
            section_lines.append(topic.summary)
            section_lines.append("")
            if topic.key_points:
                section_lines.append("**关键点:**")
                for kp in topic.key_points:
                    section_lines.append(f"- {kp}")
                section_lines.append("")
            if topic.action_items:
                section_lines.append("**待办:**")
                for ai in topic.action_items:
                    section_lines.append(f"- [ ] {ai}")
                section_lines.append("")

        # 提取字典（占位实现）
        extracted = {
            "key_progress": [],
            "action_items": [],
            "problems": []
        }

        return "\n".join(section_lines), extracted
```

- [ ] **Step 2: 验证语法**

Run: `python -m py_compile feishu/summarizer.py`
Expected: No syntax errors

- [ ] **Step 3: 添加 __init__.py 导出**

修改 `feishu/__init__.py`，添加：

```python
from .summarizer import FeishuSummarizer, ChatSession, TopicSummary

__all__ = [
    # ... 现有导出 ...
    "FeishuSummarizer",
    "ChatSession",
    "TopicSummary",
]
```

- [ ] **Step 4: Commit**

```bash
git add feishu/summarizer.py feishu/__init__.py
git commit -m "feat: add FeishuSummarizer class with basic functionality"
```

---

### Task 5: 添加 summarize 命令

**Files:**
- Modify: `feishu/__main__.py`

- [ ] **Step 1: 添加 summarize_sessions 函数**

在 `search_messages` 函数之后添加：

```python
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
        cache_base_dir=feishu_config.get("chat_cache_dir", "reports/feishu_chat_cache")
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
```

- [ ] **Step 2: 更新 main() 的参数解析**

在 `argparse` 部分添加 `summarize` 命令和参数：

```python
# 在 choices 中添加 "summarize"
parser.add_argument("command", choices=["auth", "refresh", "collect", "search", "summarize"], ...)

# 添加新参数
parser.add_argument("--days", type=int, default=2, help="获取最近 N 天 (summarize 命令使用)")
parser.add_argument("--limit", type=int, default=10000, help="最多 N 条消息 (summarize 命令使用)")
```

- [ ] **Step 3: 添加命令处理分支**

在 `if args.command == "search":` 之后添加：

```python
elif args.command == "summarize":
    summarize_sessions(config, days=args.days, limit=args.limit, output=args.output)
    return
```

- [ ] **Step 4: 验证语法**

Run: `python -m py_compile feishu/__main__.py`
Expected: No syntax errors

- [ ] **Step 5: Commit**

```bash
git add feishu/__main__.py
git commit -m "feat: add summarize command to feishu module"
```

---

### Task 6: 集成到日报生成流程

**Files:**
- Modify: `daily_report.py`

- [ ] **Step 1: 更新 collect_feishu_sources() 函数**

在 `collect_feishu_sources()` 函数末尾添加：

```python
    # 新增：获取并总结最近 2 天的会话
    try:
        from feishu.summarizer import FeishuSummarizer
        summarizer = FeishuSummarizer(collector, config.get("llm", {}))
        sessions = summarizer.fetch_sessions(days=2, max_messages=10000)
        topics = summarizer.group_by_topic(sessions)
        summary_section, extracted = summarizer.format_for_daily_report(topics)

        if summary_section.strip():
            parts.append("=== 飞书会话总结 ===\n" + summary_section)

        # TODO: 将 extracted 传递给生成器使用
    except Exception as e:
        print(f"Warning: Failed to summarize feishu sessions: {e}")

    return "\n\n".join(parts)
```

- [ ] **Step 2: 验证语法**

Run: `python -m py_compile daily_report.py`
Expected: No syntax errors

- [ ] **Step 3: Commit**

```bash
git add daily_report.py
git commit -m "feat: integrate feishu session summarizer to daily report"
```

---

## 测试和验证

### Task 7: 测试和验证

- [ ] **Step 1: 测试 summarize 命令**

Run: `python -m feishu summarize --days 1 --limit 100`
Expected: 成功获取并展示会话总结

- [ ] **Step 2: 测试日报集成**

Run: `python daily_report.py --date "$(date +%Y-%m-%d)" --force`
Expected: 日报中包含飞书会话总结章节

- [ ] **Step 3: 最终提交**

```bash
git status
# 确认所有变更都已提交
```

---

## 完成标准

- [ ] 所有 6 个任务都已完成并提交
- [ ] `python -m feishu summarize` 命令可以正常工作
- [ ] `python daily_report.py` 可以正常生成包含飞书会话总结的日报
- [ ] 没有引入语法错误或破坏现有功能

---

## 后续优化（本期不做）

1. LLM 主题聚合的完整实现
2. 用户缓存持久化（可选加密）
3. 支持按人聚合视图
4. 消息去重和智能筛选
5. 支持导出多种格式

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
        return self._group_messages_to_sessions(messages)

    def fetch_sessions_with_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        max_messages: int = 10000,
        use_enhanced: bool = True
    ) -> List[ChatSession]:
        """
        使用时间范围获取并按会话分组消息

        Args:
            start_time: 起始时间
            end_time: 结束时间
            max_messages: 最多获取多少条消息
            use_enhanced: 是否使用增强的消息获取方法

        Returns:
            ChatSession 列表
        """
        # 获取所有消息
        if use_enhanced:
            messages = self.collector.search_messages_enhanced(
                start_time=start_time,
                end_time=end_time,
                max_messages=max_messages
            )
        else:
            messages = self.collector.search_messages_all(
                start_time=start_time,
                end_time=end_time,
                max_messages=max_messages
            )
        return self._group_messages_to_sessions(messages)

    def _group_messages_to_sessions(self, messages: List[Dict]) -> List[ChatSession]:
        """
        将消息列表分组为会话

        Args:
            messages: 消息列表

        Returns:
            ChatSession 列表
        """

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
                sender_name = sender.get("name", "")
                if not sender_name:
                    sender_id = sender.get("id", "")
                    if sender_id and sender_id.startswith("ou_"):
                        sender_name = f"用户({sender_id[-6:]})"
                    elif sender_id and sender_id.startswith("cli_"):
                        sender_name = f"机器人({sender_id[-6:]})"
                    else:
                        sender_name = sender_id or "未知"
                content = msg.get("content", "")[:200]
                # 替换 @_user_1 等占位符
                content = self._replace_mention_placeholders_in_summary(content, msg)
                summary_lines.append(f"{sender_name}: {content}")

            topics.append(TopicSummary(
                topic_name=session.chat_name,
                related_sessions=[session],
                summary="\n".join(summary_lines),
                key_points=[],
                action_items=[]
            ))

        return topics

    def _replace_mention_placeholders_in_summary(self, text: str, msg: dict) -> str:
        """在总结文本中替换 @_user_1 等占位符"""
        if not text or "@_user_" not in text:
            return text

        mentions = msg.get("mentions", [])
        if not mentions:
            return text

        result = text
        for mention in mentions:
            key = mention.get("key", "")
            name = mention.get("name", "")
            if key and name:
                placeholder = f"@{key}"
                if placeholder in result:
                    result = result.replace(placeholder, f"@{name}")
        return result

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

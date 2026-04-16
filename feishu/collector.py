"""
飞书聊天和文档采集模块
"""
import re
import time
import json
import concurrent.futures
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import requests


# 北京时间时区（UTC+8）
BEIJING_TZ = timezone(timedelta(hours=8))


@dataclass
class ChatMessage:
    chat_id: str
    chat_name: str
    chat_type: str
    sender_id: str
    sender_name: str
    content: str
    timestamp: datetime


@dataclass
class DocInfo:
    doc_url: str
    doc_title: str
    doc_type: str
    last_accessed: datetime


@dataclass
class UserInfo:
    name: str
    updated_at: float  # timestamp in seconds


class ChatListError(Exception):
    """获取会话列表失败"""
    pass


class MessageListError(Exception):
    """获取消息列表失败"""
    pass


class RateLimitError(Exception):
    """API 限流"""
    pass


class FeishuCollector:
    def __init__(self, access_token: str, cache_base_dir: str = "cache/feishu_chat_cache"):
        self.access_token = access_token
        self.cache_base_dir = Path(cache_base_dir)
        self.cache_base_dir.mkdir(parents=True, exist_ok=True)
        self.max_message_age_days = 7  # 最多获取7天内的消息
        self.max_pages_per_chat = 5  # 每个会话最多获取5页消息
        self.max_concurrent_chats = 10  # 并发获取消息的会话数
        self._user_cache: Dict[str, UserInfo] = {}  # 用户ID到名称的缓存
        self._chat_cache: Dict[str, Dict] = {}  # 会话ID到会话信息的缓存

    def collect_chat_for_date(self, date: datetime, force: bool = False) -> Path:
        """采集指定日期的聊天记录"""
        cache_path = self.cache_base_dir / f"{date.strftime('%Y-%m-%d')}.md"

        if not force and cache_path.exists():
            return cache_path

        # 计算目标日期的时间范围
        target_start = datetime(date.year, date.month, date.day, 0, 0, 0)
        target_end = datetime(date.year, date.month, date.day, 23, 59, 59)

        # 但只获取最近7天的消息（避免获取太旧的消息）
        seven_days_ago = datetime.now() - timedelta(days=self.max_message_age_days)
        start_time = max(target_start, seven_days_ago)
        end_time = target_end

        print("正在采集飞书聊天记录...")

        # 使用增强的按时间间隔搜索方法，获取更全的消息
        raw_messages = self.search_messages_enhanced(
            start_time=start_time,
            end_time=end_time,
            max_messages=10000,
        )

        if not raw_messages:
            print("未找到任何聊天记录")
            return self._save_chat_cache(date, [])

        print(f"获取到 {len(raw_messages)} 条原始消息")

        # 提取所有chat_id，批量获取会话信息
        chat_ids = list({msg.get("chat_id", "") for msg in raw_messages if msg.get("chat_id")})
        chat_infos = self._batch_query_chats(chat_ids)

        # 转换为ChatMessage对象并填充信息
        all_messages = []
        all_user_ids = set()

        for msg in raw_messages:
            try:
                # 提取基本信息
                msg_id = msg.get("message_id", "")
                chat_id = msg.get("chat_id", "")
                sender_id = msg.get("sender_id", "")
                create_time = msg.get("create_time", "")
                content = msg.get("body", {}).get("content", "")
                chat_type = msg.get("chat_type", "unknown")
                chat_name = msg.get("chat_name", "未知会话")

                # 优先从缓存的会话信息中获取会话名称
                if chat_id in chat_infos:
                    chat_info = chat_infos[chat_id]
                    chat_name = chat_info.get("name", chat_name)
                    chat_type = chat_info.get("chat_type", chat_type)

                # 转换时间戳
                try:
                    if create_time:
                        ts = int(create_time) / 1000
                        timestamp = datetime.fromtimestamp(ts)
                    else:
                        timestamp = datetime.now()
                except:
                    timestamp = datetime.now()

                # 创建ChatMessage对象
                chat_msg = ChatMessage(
                    chat_id=chat_id,
                    chat_name=chat_name,
                    chat_type=chat_type,
                    sender_id=sender_id,
                    sender_name="",  # 后面统一填充
                    content=content,
                    timestamp=timestamp
                )

                all_messages.append(chat_msg)
                if sender_id:
                    all_user_ids.add(sender_id)

            except Exception as e:
                continue

        # 批量获取用户信息
        if all_user_ids:
            self._ensure_users_basic(list(all_user_ids))

        # 更新消息中的发送者名称
        for msg in all_messages:
            if msg.sender_id and msg.sender_id in self._user_cache:
                msg.sender_name = self._user_cache[msg.sender_id].name

        print(f"处理完成，共 {len(all_messages)} 条有效消息")
        return self._save_chat_cache(date, all_messages)

    def _batch_get_user_names(self, user_ids: List[str]) -> None:
        """批量获取用户名称并缓存"""
        # 过滤掉已缓存的用户和机器人 ID（cli_ 开头）
        uncached_ids = [uid for uid in user_ids if uid and uid not in self._user_cache and not uid.startswith("cli_")]
        if not uncached_ids:
            return

        url = "https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        body = {
            "user_ids": uncached_ids,
            "user_id_type": "open_id"
        }

        try:
            resp = requests.post(url, headers=headers, json=body, timeout=30)
            data = resp.json()
            if data.get("code") == 0:
                users = data.get("data", {}).get("user_list", [])
                for user_item in users:
                    user = user_item.get("user", {})
                    user_id = user.get("open_id", "")
                    name = user.get("name", "")
                    if user_id and name:
                        self._user_cache[user_id] = UserInfo(name=name, updated_at=time.time())
        except Exception as e:
            pass

    def _ensure_users_basic(self, user_ids: List[str]) -> None:
        """
        批量获取用户基本信息（使用 contact/v3/user/basic_batch）
        自动跳过已缓存且未过期的用户
        自动过滤机器人 ID（cli_ 开头）
        """
        if not user_ids:
            return

        now = time.time()
        cache_ttl = 24 * 60 * 60  # 24小时缓存
        uncached_ids = []

        for uid in user_ids:
            if not uid:
                continue
            # 过滤机器人 ID（cli_ 开头的是机器人）
            if uid.startswith("cli_"):
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

        # 分批请求，每批最多 10 个
        batch_size = 10
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
                    pass

            except Exception as e:
                pass

    def _populate_cache_from_mentions(self, messages: List[Dict]) -> int:
        """
        从消息列表的 mentions 中提取用户信息并缓存

        Args:
            messages: 消息列表

        Returns:
            缓存的用户数量
        """
        cached_count = 0

        for msg in messages:
            mentions = msg.get("mentions", [])
            for mention in mentions:
                mention_id = mention.get("id", "")
                mention_name = mention.get("name", "")

                if not mention_id or not mention_name:
                    continue

                # 提取 open_id
                open_id = mention_id
                if mention_id.startswith("open_id:"):
                    open_id = mention_id.split(":", 1)[1]

                # 只缓存有效的 open_id（以 ou_ 开头）
                if open_id.startswith("ou_") and open_id not in self._user_cache:
                    self._user_cache[open_id] = UserInfo(
                        name=mention_name,
                        updated_at=time.time()
                    )
                    cached_count += 1

        return cached_count

    def _get_user_name(self, user_id: str) -> str:
        """获取用户名称"""
        if user_id in self._user_cache:
            return self._user_cache[user_id].name

        url = f"https://open.feishu.cn/open-apis/contact/v3/users/{user_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"user_id_type": "open_id"}

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            data = resp.json()
            if data.get("code") == 0:
                user = data.get("data", {}).get("user", {})
                name = user.get("name", "")
                if name:
                    self._user_cache[user_id] = UserInfo(name=name, updated_at=time.time())
                    return name
        except Exception:
            pass

        return "未知用户"

    def _get_chats_list(self) -> List[dict]:
        """获取会话列表"""
        url = "https://open.feishu.cn/open-apis/im/v1/chats"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        chats = []
        page_token = ""

        while True:
            params = {"page_size": 50}
            if page_token:
                params["page_token"] = page_token

            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                data = resp.json()
            except Exception as e:
                raise ChatListError(f"Failed to get chat list: {e}") from e

            if data.get("code") == 99991663:  # 限流码
                time.sleep(2)
                continue

            if data.get("code") != 0:
                raise ChatListError(f"API error: {data}")

            data_items = data.get("data", {})
            items = data_items.get("items", [])
            chats.extend(items)

            page_token = data_items.get("page_token", "")
            if not data_items.get("has_more", False) or not page_token:
                break

        return chats

    def _get_chat_messages(self, chat_id: str, start_time: int, end_time: int) -> List[ChatMessage]:
        """获取会话消息"""
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        messages = []
        page_token = ""
        page_count = 0
        found_older = False

        while page_count < self.max_pages_per_chat and not found_older:
            page_count += 1
            params = {
                "container_id_type": "chat",
                "container_id": chat_id,
                "sort_type": "ByCreateTimeDesc",
                "page_size": 20,
            }
            if page_token:
                params["page_token"] = page_token

            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                data = resp.json()
            except Exception as e:
                break

            if data.get("code") == 99991663:  # 限流码
                time.sleep(2)
                continue

            if data.get("code") != 0:
                break

            data_items = data.get("data", {})
            items = data_items.get("items", [])

            # First pass: cache all mentions user info
            for item in items:
                mentions = item.get("mentions", [])
                for mention in mentions:
                    mention_id = mention.get("id", "")
                    mention_name = mention.get("name", "")
                    if mention_id and mention_name:
                        self._user_cache[mention_id] = UserInfo(name=mention_name, updated_at=time.time())

            for item in items:
                create_time = int(item.get("create_time", 0))
                if create_time < start_time:
                    # 消息太旧，后面的会更旧，标记停止翻页
                    found_older = True
                    continue
                if create_time > end_time:
                    continue

                sender = item.get("sender", {})
                sender_id = sender.get("id", "")
                sender_name = "未知用户"

                # Try to find sender name from mentions (if sender is mentioned)
                mentions = item.get("mentions", [])
                for mention in mentions:
                    if mention.get("id") == sender_id:
                        sender_name = mention.get("name", "未知用户")
                        break

                # If still unknown, try to get from user cache or user API
                if sender_name == "未知用户" and sender_id:
                    if sender_id in self._user_cache:
                        sender_name = self._user_cache[sender_id].name
                    else:
                        sender_name = self._get_user_name(sender_id)

                messages.append(ChatMessage(
                    chat_id=chat_id,
                    chat_name="",
                    chat_type="",
                    sender_id=sender_id,
                    sender_name=sender_name,
                    content=self._parse_message_content(item),
                    timestamp=datetime.fromtimestamp(create_time / 1000),
                ))

            page_token = data_items.get("page_token", "")
            if not data_items.get("has_more", False) or not page_token:
                break

        messages.sort(key=lambda m: m.timestamp)
        return messages

    def _extract_text_from_interactive_card(self, data: dict) -> str:
        """
        从交互卡片中递归提取所有content字段的文本内容

        Args:
            data: 交互卡片的 JSON 数据

        Returns:
            提取的纯文本内容，用空格连接
        """
        texts = []

        def extract_content_recursive(obj: Any):
            """递归提取所有content字段"""
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key == "content":
                        if isinstance(value, str) and value.strip():
                            texts.append(value.strip())
                    else:
                        extract_content_recursive(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_content_recursive(item)

        try:
            actual_data = data
            if "json_card" in data:
                json_card_str = data.get("json_card", "")
                if json_card_str:
                    try:
                        actual_data = json.loads(json_card_str)
                    except json.JSONDecodeError:
                        pass

            extract_content_recursive(actual_data)

        except Exception:
            # 如果提取失败，返回简单的标记
            return "[交互卡片]"

        # 去重并拼接（不限制数量）
        unique_texts = list(dict.fromkeys(texts))  # 保持顺序去重
        if unique_texts:
            return "[交互卡片] " + " ".join(unique_texts)
        return "[交互卡片]"

    def _parse_message_content(self, msg_item: dict) -> str:
        """解析消息内容"""
        msg_type = msg_item.get("msg_type", "text")
        body = msg_item.get("body", {})
        content_str = body.get("content", "")
        mentions = msg_item.get("mentions", [])

        if not content_str:
            return ""

        try:
            data = json.loads(content_str)
            if not isinstance(data, dict):
                return self._replace_mention_placeholders(content_str, mentions)

            if msg_type == "text":
                text = data.get("text", content_str)
                return self._replace_mention_placeholders(text, mentions)
            elif msg_type == "post":
                text = self._parse_post_content(data)
                return self._replace_mention_placeholders(text, mentions)
            elif msg_type == "image":
                return "[图片]"
            elif msg_type == "file":
                return f"[文件: {data.get('file_name', 'unknown')}]"
            elif msg_type == "audio":
                return "[语音]"
            elif msg_type == "media":
                return "[视频]"
            elif msg_type == "share_chat":
                return f"[分享群聊: {data.get('chat_name', 'unknown')}]"
            elif msg_type == "share_user":
                return f"[分享用户: {data.get('user_name', 'unknown')}]"
            elif msg_type == "interactive":
                # 递归提取卡片文本内容
                text = self._extract_text_from_interactive_card(data)
                return self._replace_mention_placeholders(text, mentions)
            else:
                text = data.get("text", "")
                if text:
                    return self._replace_mention_placeholders(text, mentions)
                return f"[{msg_type}]"
        except json.JSONDecodeError:
            return self._replace_mention_placeholders(content_str, mentions)
        except Exception:
            return self._replace_mention_placeholders(content_str, mentions)

    def _replace_mention_placeholders(self, text: str, mentions: list) -> str:
        """
        替换 @_user_1 等占位符为实际用户名

        Args:
            text: 原始文本
            mentions: mentions 列表

        Returns:
            替换后的文本
        """
        if not text or not mentions:
            return text

        result = text

        # 构建映射表 - 支持多种 key 格式
        mention_map = {}
        for idx, mention in enumerate(mentions):
            key = mention.get("key", "")
            name = mention.get("name", "")

            if name:
                # 1. 使用原始 key
                if key:
                    mention_map[key] = name
                # 2. 使用索引作为备用 key (_user_1, _user_2 等)
                mention_map[f"_user_{idx + 1}"] = name
                # 3. 也支持不带下划线的格式
                mention_map[f"user_{idx + 1}"] = name

        # 进行替换
        for key, name in mention_map.items():
            # 替换 @_user_1, @_user_2 等格式
            placeholder = f"@{key}"
            if placeholder in result:
                result = result.replace(placeholder, f"@{name}")

        return result

    def _parse_post_content(self, data: dict) -> str:
        """解析富文本消息内容"""
        content = data.get("content", [])
        parts = []
        for paragraph in content:
            if isinstance(paragraph, list):
                for elem in paragraph:
                    if isinstance(elem, dict):
                        tag = elem.get("tag", "")
                        if tag == "text":
                            parts.append(elem.get("text", ""))
                        elif tag == "at":
                            user_name = elem.get("user_name", "")
                            parts.append(f"@{user_name}")
                        elif tag == "a":
                            text = elem.get("text", "")
                            href = elem.get("href", "")
                            if text and href:
                                parts.append(f"[{text}]({href})")
                            elif href:
                                parts.append(href)
                        elif tag == "img":
                            parts.append("[图片]")
        return "".join(parts)

    def _save_chat_cache(self, date: datetime, messages: List[ChatMessage]) -> Path:
        """保存聊天缓存"""
        cache_path = self.cache_base_dir / f"{date.strftime('%Y-%m-%d')}.md"

        lines = [f"# 飞书聊天记录 - {date.strftime('%Y-%m-%d')}", ""]

        chat_groups = {}
        for msg in messages:
            key = (msg.chat_id, msg.chat_name, msg.chat_type)
            if key not in chat_groups:
                chat_groups[key] = []
            chat_groups[key].append(msg)

        for (chat_id, chat_name, chat_type), msgs in chat_groups.items():
            if chat_type == "group":
                type_label = "群聊"
            elif chat_type == "p2p":
                type_label = "私聊"
            else:
                type_label = "会话"
            lines.append(f"## {type_label}：{chat_name} (chat_id: {chat_id})")
            for msg in msgs:
                time_str = msg.timestamp.strftime("%H:%M:%S")
                lines.append(f"- [{time_str}] {msg.sender_name}: {msg.content}")
            lines.append("")

        with open(cache_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return cache_path

    def get_recent_docs(self, days: int = 7) -> List[DocInfo]:
        """获取最近访问的文档列表（简化实现）"""
        return []

    def extract_doc_links_from_chat(self, chat_cache_path: Path) -> List[str]:
        """从聊天缓存中提取飞书文档链接"""
        if not chat_cache_path.exists():
            return []

        with open(chat_cache_path, "r", encoding="utf-8") as f:
            content = f.read()

        pattern = r"https?://[^\s<>\"']+feishu[^\s<>\"']+"
        links = re.findall(pattern, content)
        return list(dict.fromkeys(links))

    def collect_calendar_for_date(self, date: datetime, calendar_id: str = "") -> str:
        """
        采集指定日期的日程（前7天 + 当天 + 后7天）
        返回格式化的文本
        """
        if not calendar_id:
            calendars = self._get_calendar_list()
            if not calendars:
                return ""
            # 优先选择主日历 (type='primary')
            primary_cal = None
            for cal in calendars:
                if cal.get("type") == "primary":
                    primary_cal = cal
                    break
            if primary_cal:
                calendar_id = primary_cal.get("calendar_id", "")
            else:
                calendar_id = calendars[0].get("calendar_id", "")

        target_date_start = datetime(date.year, date.month, date.day)
        start_ts = int((target_date_start - timedelta(days=7)).timestamp() * 1000)
        end_ts = int((target_date_start + timedelta(days=8)).timestamp() * 1000) - 1

        try:
            events = self._get_calendar_events(calendar_id, start_ts, end_ts)
            if not events:
                return ""

            events_by_date = self._group_events_by_date(events, date)
            return self._format_calendar_events(events_by_date, date)

        except Exception as e:
            return ""

    def _get_calendar_list(self) -> List[dict]:
        """获取日历列表"""
        url = "https://open.feishu.cn/open-apis/calendar/v4/calendars"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            data = resp.json()
            if data.get("code") == 0:
                # 先尝试 calendar_list，再尝试 calendars（兼容不同版本）
                calendars = data.get("data", {}).get("calendar_list", [])
                if not calendars:
                    calendars = data.get("data", {}).get("calendars", [])
                return calendars
            return []
        except Exception:
            return []

    def _get_calendar_events(self, calendar_id: str, start_ts: int, end_ts: int) -> List[dict]:
        """获取日历事件列表"""
        url = f"https://open.feishu.cn/open-apis/calendar/v4/calendars/{calendar_id}/events"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        events = []
        page_token = ""

        while True:
            params = {
                "page_size": 50,
                "time_zone": "Asia/Shanghai",
                "start_time": str(start_ts),
                "end_time": str(end_ts),
            }
            if page_token:
                params["page_token"] = page_token

            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                data = resp.json()
            except Exception as e:
                raise Exception(f"Failed to get calendar events: {e}") from e

            if data.get("code") == 99991663:
                time.sleep(2)
                continue

            if data.get("code") != 0:
                raise Exception(f"Calendar API error: {data}")

            data_items = data.get("data", {})
            items = data_items.get("items", [])

            for item in items:
                event_start = self._parse_event_time(item.get("start_time"))
                event_end = self._parse_event_time(item.get("end_time"))
                if event_start and event_end:
                    event_start_ts = event_start.timestamp() * 1000
                    event_end_ts = event_end.timestamp() * 1000
                    if event_end_ts >= start_ts and event_start_ts <= end_ts:
                        events.append(item)

            page_token = data_items.get("page_token", "")
            if not data_items.get("has_more", False) or not page_token:
                break

        return events

    def _parse_event_time(self, time_obj: dict) -> Optional[datetime]:
        """解析事件时间"""
        if not time_obj:
            return None
        ts = time_obj.get("timestamp")
        if ts:
            return datetime.fromtimestamp(int(ts))
        return None

    def _group_events_by_date(self, events: List[dict], target_date: datetime) -> Dict[str, List[dict]]:
        """
        将事件按日期分组
        返回: {"past": [...], "today": [...], "future": [...]}
        """
        result = {"past": [], "today": [], "future": []}
        target_date_start = datetime(target_date.year, target_date.month, target_date.day)
        seven_days_ago = target_date_start - timedelta(days=7)
        seven_days_later = target_date_start + timedelta(days=7)

        for event in events:
            start_time = self._parse_event_time(event.get("start_time"))
            if not start_time:
                continue

            event_date = datetime(start_time.year, start_time.month, start_time.day)

            if seven_days_ago <= event_date < target_date_start:
                result["past"].append(event)
            elif event_date == target_date_start:
                result["today"].append(event)
            elif target_date_start < event_date <= seven_days_later:
                result["future"].append(event)

        return result

    def _format_calendar_events(self, events_by_date: Dict[str, List[dict]], target_date: datetime) -> str:
        """格式化日程事件为 LLM 输入文本"""
        lines = []

        if events_by_date["past"]:
            lines.append("--- 历史（前7天）---")
            lines.append("")
            for event in sorted(events_by_date["past"], key=lambda e: self._parse_event_time(e.get("start_time")) or datetime.max):
                lines.extend(self._format_single_event(event, show_date=True))
                lines.append("")

        if events_by_date["today"]:
            lines.append(f"--- 今天（{target_date.strftime('%Y-%m-%d')}）---")
            lines.append("")
            for event in sorted(events_by_date["today"], key=lambda e: self._parse_event_time(e.get("start_time")) or datetime.max):
                lines.extend(self._format_single_event(event, show_date=False))
                lines.append("")

        if events_by_date["future"]:
            lines.append("--- 未来（后7天）---")
            lines.append("")
            for event in sorted(events_by_date["future"], key=lambda e: self._parse_event_time(e.get("start_time")) or datetime.max):
                lines.extend(self._format_single_event(event, show_date=True))
                lines.append("")

        return "\n".join(lines)

    def _format_single_event(self, event: dict, show_date: bool = False) -> List[str]:
        """格式化单个事件"""
        lines = []
        start_time = self._parse_event_time(event.get("start_time"))
        end_time = self._parse_event_time(event.get("end_time"))
        title = event.get("summary", "").strip() or "（无标题）"

        time_str = ""
        if start_time and end_time:
            if show_date:
                time_str = f"{start_time.strftime('%Y-%m-%d')} {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
            else:
                time_str = f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
        elif start_time:
            if show_date:
                time_str = f"{start_time.strftime('%Y-%m-%d')} {start_time.strftime('%H:%M')}"
            else:
                time_str = start_time.strftime('%H:%M')

        if time_str:
            lines.append(f"## {time_str} - {title}")
        else:
            lines.append(f"## {title}")

        organizer = event.get("organizer", {})
        organizer_name = organizer.get("display_name", "") or organizer.get("email", "")
        if organizer_name:
            lines.append(f"- 组织者: {organizer_name}")

        attendees = event.get("attendees", [])
        if attendees:
            attendee_names = []
            for a in attendees:
                name = a.get("display_name", "") or a.get("email", "")
                if name:
                    attendee_names.append(name)
            if attendee_names:
                lines.append(f"- 参与者: {', '.join(attendee_names)}")

        location = event.get("location")
        if location:
            lines.append(f"- 地点: {location}")

        description = event.get("description")
        if description:
            lines.append(f"- 描述: {description}")

        if not event.get("summary", "").strip():
            lines.append("- 备注: 对应时间可能有智能纪要文档")

        return lines

    # =========================================================================
    # 时间工具函数（参考 JS 实现）
    # =========================================================================

    def _seconds_to_datetime(self, seconds: int) -> datetime:
        """Unix 秒 → 北京时间 datetime"""
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
        return dt.astimezone(BEIJING_TZ)

    def _millis_to_datetime(self, millis: int) -> datetime:
        """Unix 毫秒 → 北京时间 datetime"""
        return self._seconds_to_datetime(millis // 1000)

    def _datetime_to_seconds(self, dt: datetime) -> int:
        """datetime → Unix 秒"""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BEIJING_TZ)
        return int(dt.timestamp())

    def _datetime_to_seconds_str(self, dt: datetime) -> str:
        """datetime → Unix 秒字符串"""
        return str(self._datetime_to_seconds(dt))

    def _parse_time_range(self, relative_time: str) -> Dict[str, int]:
        """
        解析相对时间范围，返回 Unix 秒
        支持: today/yesterday/day_before_yesterday/this_week/last_week/this_month/last_month/last_{N}_{unit}
        """
        now = datetime.now(BEIJING_TZ)
        bj_now = now

        if relative_time == "today":
            start = bj_now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif relative_time == "yesterday":
            d = bj_now - timedelta(days=1)
            start = d.replace(hour=0, minute=0, second=0, microsecond=0)
            end = d.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif relative_time == "day_before_yesterday":
            d = bj_now - timedelta(days=2)
            start = d.replace(hour=0, minute=0, second=0, microsecond=0)
            end = d.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif relative_time == "this_week":
            day = bj_now.weekday()  # 0=Mon .. 6=Sun
            diff_to_mon = day
            monday = bj_now - timedelta(days=diff_to_mon)
            start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif relative_time == "last_week":
            day = bj_now.weekday()
            diff_to_mon = day
            this_monday = bj_now - timedelta(days=diff_to_mon)
            last_monday = this_monday - timedelta(days=7)
            last_sunday = this_monday - timedelta(days=1)
            start = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
            end = last_sunday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif relative_time == "this_month":
            first_day = bj_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start = first_day
            end = now
        elif relative_time == "last_month":
            first_day_this_month = bj_now.replace(day=1)
            last_day_prev_month = first_day_this_month - timedelta(days=1)
            first_day_prev_month = last_day_prev_month.replace(day=1)
            start = first_day_prev_month.replace(hour=0, minute=0, second=0, microsecond=0)
            end = last_day_prev_month.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            # last_{N}_{unit}
            import re
            match = re.match(r"^last_(\d+)_(minutes?|hours?|days?)$", relative_time)
            if not match:
                raise ValueError(f"不支持的 relative_time 格式: {relative_time}")
            n = int(match.group(1))
            unit = match.group(2).rstrip("s")  # normalize plural

            if unit == "minute":
                start = now - timedelta(minutes=n)
            elif unit == "hour":
                start = now - timedelta(hours=n)
            elif unit == "day":
                start = now - timedelta(days=n)
            else:
                raise ValueError(f"不支持的时间单位: {unit}")
            end = now

        return {
            "start": self._datetime_to_seconds(start),
            "end": self._datetime_to_seconds(end)
        }

    # =========================================================================
    # 搜索消息功能（参考 feishu_im_user_search_messages）
    # =========================================================================

    def search_messages(
        self,
        query: Optional[str] = None,
        sender_ids: Optional[List[str]] = None,
        chat_id: Optional[str] = None,
        mention_ids: Optional[List[str]] = None,
        message_type: Optional[str] = None,
        sender_type: Optional[str] = None,
        chat_type: Optional[str] = None,
        relative_time: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page_size: int = 50,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        跨会话搜索飞书消息

        Args:
            query: 搜索关键词
            sender_ids: 发送者 open_id 列表
            chat_id: 限定在某个会话内搜索
            mention_ids: 被@用户的 open_id 列表
            message_type: 消息类型过滤 (file/image/media)
            sender_type: 发送者类型 (user/bot/all)
            chat_type: 会话类型 (group/p2p)
            relative_time: 相对时间范围 (today/yesterday/this_week/last_3_days 等)
            start_time: 起始时间（与 relative_time 互斥）
            end_time: 结束时间（与 relative_time 互斥）
            page_size: 每页消息数（1-50）
            page_token: 分页标记

        Returns:
            {
                "messages": [...],
                "has_more": bool,
                "page_token": str
            }
        """
        # 步骤 1: 解析时间范围
        if relative_time and (start_time or end_time):
            raise ValueError("不能同时使用 relative_time 和 start_time/end_time")

        if relative_time:
            time_range = self._parse_time_range(relative_time)
            start_ts = str(time_range["start"])
            end_ts = str(time_range["end"])
        else:
            # 默认: 从 2001-01-01 到现在
            if start_time:
                start_ts = self._datetime_to_seconds_str(start_time)
            else:
                start_ts = "978307200"  # 2001-01-01
            if end_time:
                end_ts = self._datetime_to_seconds_str(end_time)
            else:
                end_ts = str(int(time.time()))

        # 步骤 2: 构建搜索参数
        search_data: Dict[str, Any] = {
            "query": query or "",
            "start_time": start_ts,
            "end_time": end_ts
        }

        if sender_ids:
            search_data["from_ids"] = sender_ids
        if chat_id:
            search_data["chat_ids"] = [chat_id]
        if mention_ids:
            search_data["at_chatter_ids"] = mention_ids
        if message_type:
            search_data["message_type"] = message_type
        if sender_type and sender_type != "all":
            search_data["from_type"] = sender_type
        if chat_type:
            search_data["chat_type"] = "group_chat" if chat_type == "group" else "p2p_chat"

        # 步骤 3: 搜索消息 ID (使用 v2 API)
        search_url = "https://open.feishu.cn/open-apis/search/v2/message"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        params = {
            "user_id_type": "open_id",
            "page_size": min(page_size, 50)
        }
        if page_token:
            params["page_token"] = page_token

        for _attempt in range(5):
            try:
                resp = requests.post(search_url, headers=headers, params=params, json=search_data, timeout=30)
                search_res = resp.json()
            except Exception as e:
                raise Exception(f"Search API failed: {e}") from e
            if search_res.get("code") == 99991663:  # 限流
                time.sleep(2)
                continue
            break

        if search_res.get("code") != 0:
            raise Exception(f"Search API error: {search_res}")

        message_ids = search_res.get("data", {}).get("items", [])
        has_more = search_res.get("data", {}).get("has_more", False)
        page_token = search_res.get("data", {}).get("page_token", "")

        if not message_ids:
            return {"messages": [], "has_more": has_more, "page_token": page_token}

        # 步骤 4: 批量获取消息详情
        query_str = "&".join([f"message_ids={requests.utils.quote(mid)}" for mid in message_ids])
        mget_url = f"https://open.feishu.cn/open-apis/im/v1/messages/mget?{query_str}"

        for _attempt in range(5):
            try:
                resp = requests.get(mget_url, headers=headers, params={
                    "user_id_type": "open_id",
                    "card_msg_content_type": "raw_card_content"
                }, timeout=30)
                mget_res = resp.json()
            except Exception as e:
                raise Exception(f"Batch get messages failed: {e}") from e
            if mget_res.get("code") == 99991663:  # 限流
                time.sleep(2)
                continue
            break

        items = mget_res.get("data", {}).get("items", [])

        # 步骤 5: 批量获取会话信息
        chat_ids = list({i.get("chat_id", "") for i in items if i.get("chat_id")})
        chat_map = self._fetch_chat_contexts(chat_ids)

        # 步骤 6: 格式化消息（先收集用户信息）
        all_user_ids = set()
        for item in items:
            # 收集 sender
            sender = item.get("sender", {})
            if sender.get("sender_type") == "user":
                sender_id = sender.get("id", "")
                if sender_id:
                    all_user_ids.add(sender_id)
            # 收集 mentions
            for mention in item.get("mentions", []):
                mention_id = mention.get("id", "")
                if mention_id:
                    # 从 mentions 中提取 open_id
                    if mention_id.startswith("ou_"):
                        all_user_ids.add(mention_id)
                    elif mention_id.startswith("open_id:"):
                        all_user_ids.add(mention_id.split(":", 1)[1])

        # 从 mentions 中免费获取用户名称
        mention_names = {}
        for item in items:
            for mention in item.get("mentions", []):
                m_id = mention.get("id", "")
                m_name = mention.get("name", "")
                if m_id and m_name:
                    # 提取 open_id
                    open_id = m_id
                    if m_id.startswith("open_id:"):
                        open_id = m_id.split(":", 1)[1]
                    if open_id.startswith("ou_"):
                        mention_names[open_id] = m_name

        if mention_names:
            for open_id, name in mention_names.items():
                if open_id not in self._user_cache:
                    self._user_cache[open_id] = UserInfo(name=name, updated_at=time.time())

        # 批量获取剩余用户信息
        if all_user_ids:
            self._batch_get_user_names(list(all_user_ids))

        # 步骤 7: 解析 P2P 对方用户名
        p2p_target_ids = []
        for chat_id, chat_info in chat_map.items():
            if chat_info.get("chat_mode") == "p2p":
                target_id = chat_info.get("p2p_target_id")
                if target_id:
                    p2p_target_ids.append(target_id)
        if p2p_target_ids:
            self._batch_get_user_names(p2p_target_ids)

        # 步骤 8: 格式化并补充会话信息
        messages = []
        for item in items:
            msg = self._format_search_message_item(item)
            if not msg:
                continue

            # 先从原始 item 中获取 chat_id（即使获取不到 chat 上下文也要保留）
            chat_id = item.get("chat_id")
            if chat_id:
                msg["chat_id"] = chat_id

            # 然后尝试补充 chat_name 和 chat_type
            if chat_id and chat_id in chat_map:
                chat_info = chat_map[chat_id]
                msg["chat_type"] = chat_info.get("chat_mode")

                if chat_info.get("chat_mode") == "p2p":
                    target_id = chat_info.get("p2p_target_id")
                    if target_id:
                        partner_name = self._user_cache.get(target_id, UserInfo(name="", updated_at=0)).name
                        msg["chat_name"] = partner_name
                        msg["chat_partner"] = {
                            "open_id": target_id,
                            "name": partner_name
                        }
                else:
                    msg["chat_name"] = chat_info.get("name", "")

            messages.append(msg)

        return {
            "messages": messages,
            "has_more": has_more,
            "page_token": page_token
        }

    def search_messages_all(
        self,
        days: Optional[int] = None,
        max_messages: int = 10000,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict]:
        """
        分页获取所有消息

        Args:
            days: 获取最近几天的消息（与 start_time/end_time 互斥）
            max_messages: 最多获取多少条消息
            start_time: 起始时间（与 days 互斥）
            end_time: 结束时间（与 days 互斥）

        Returns:
            消息列表
        """
        # ========== 新增：预搜索获取 mentions 预填充缓存 ==========
        try:
            # 先进行一次轻量搜索，获取 mentions
            presearch_kwargs = {
                "page_size": 50,
                "page_token": None
            }
            if days is not None:
                presearch_kwargs["relative_time"] = f"last_{days}_days"
            else:
                presearch_kwargs["start_time"] = start_time
                presearch_kwargs["end_time"] = end_time

            pre_result = self.search_messages(**presearch_kwargs)
            pre_messages = pre_result.get("messages", [])
            if pre_messages:
                self._populate_cache_from_mentions(pre_messages)
        except Exception as e:
            pass
        # =========================================================

        all_messages = []
        page_token = ""
        iterations = 0
        max_iterations = (max_messages // 100) + 2  # 安全边界

        while len(all_messages) < max_messages and iterations < max_iterations:
            iterations += 1

            try:
                # 构建搜索参数
                search_kwargs = {
                    "page_size": min(100, max_messages - len(all_messages)),
                    "page_token": page_token if page_token else None
                }

                if days is not None:
                    search_kwargs["relative_time"] = f"last_{days}_days"
                else:
                    search_kwargs["start_time"] = start_time
                    search_kwargs["end_time"] = end_time

                result = self.search_messages(**search_kwargs)

                messages = result.get("messages", [])
                if not messages:
                    break

                all_messages.extend(messages)

                has_more = result.get("has_more", False)
                page_token = result.get("page_token", "")

                if not has_more or not page_token:
                    break

            except Exception as e:
                break
        return all_messages[:max_messages]

    def _fetch_chat_contexts(self, chat_ids: List[str]) -> Dict[str, Dict]:
        """批量获取会话信息（带缓存）"""
        result = {}
        if not chat_ids:
            return result

        # 先从缓存取
        uncached_ids = []
        for chat_id in chat_ids:
            if chat_id in self._chat_cache:
                result[chat_id] = self._chat_cache[chat_id]
            else:
                uncached_ids.append(chat_id)

        if not uncached_ids:
            return result  # 全部命中缓存，直接返回

        # 只查询未缓存的会话
        url = "https://open.feishu.cn/open-apis/im/v1/chats/batch_query"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            resp = requests.post(url, headers=headers, json={
                "chat_ids": uncached_ids
            }, params={"user_id_type": "open_id"}, timeout=30)
            data = resp.json()

            if data.get("code") != 0:
                return result

            for chat in data.get("data", {}).get("items", []):
                chat_id = chat.get("chat_id")
                if chat_id:
                    chat_info = {
                        "name": chat.get("name", ""),
                        "chat_mode": chat.get("chat_mode", ""),
                        "p2p_target_id": chat.get("p2p_target_id")
                    }
                    result[chat_id] = chat_info
                    self._chat_cache[chat_id] = chat_info  # 写入缓存
        except Exception as e:
            pass

        return result

    def _format_search_message_item(self, item: Dict) -> Optional[Dict]:
        """格式化单条搜索消息"""
        message_id = item.get("message_id", "")
        msg_type = item.get("msg_type", "unknown")

        # 解析消息内容
        content = ""
        try:
            raw_content = item.get("body", {}).get("content", "")
            if raw_content:
                content = self._parse_message_content(item)
        except Exception as e:
            content = item.get("body", {}).get("content", "")

        # 构建 sender
        sender = item.get("sender", {})
        sender_id = sender.get("id", "")
        sender_type = sender.get("sender_type", "unknown")
        sender_name = None

        # 先从当前消息的 mentions 中查找
        if sender_id:
            mentions_list = item.get("mentions", [])
            for mention in mentions_list:
                mention_id = mention.get("id", "")
                # 匹配：直接匹配、或者 mention_id 包含 sender_id
                if mention_id == sender_id or (sender_id and sender_id in mention_id):
                    mention_name = mention.get("name", "")
                    if mention_name:
                        sender_name = mention_name
                        break

        # 如果还没找到，尝试从 user_cache 获取
        if sender_name is None and sender_id and sender_type == "user":
            # 清理 sender_id（去掉前缀）
            clean_sender_id = sender_id
            if sender_id.startswith("open_id:"):
                clean_sender_id = sender_id.split(":", 1)[1]

            if clean_sender_id in self._user_cache:
                sender_name = self._user_cache[clean_sender_id].name
            else:
                # 尝试 API 获取
                sender_name = self._get_user_name(clean_sender_id)

        # 如果还是没找到，标记为未知用户
        if sender_name is None:
            sender_name = "未知用户"

        sender_dict = {
            "id": sender_id,
            "sender_type": sender_type,
            "name": sender_name
        }

        # 构建 mentions
        mentions = None
        if item.get("mentions"):
            mentions = []
            for m in item.get("mentions", []):
                m_id = m.get("id", "")
                # 提取 open_id
                open_id = m_id
                if m_id.startswith("open_id:"):
                    open_id = m_id.split(":", 1)[1]
                mentions.append({
                    "key": m.get("key", ""),
                    "id": open_id,
                    "name": m.get("name", "")
                })

        # 转换时间
        create_time = ""
        if item.get("create_time"):
            try:
                dt = self._millis_to_datetime(int(item.get("create_time")))
                create_time = dt.isoformat()
            except (ValueError, TypeError):
                pass

        formatted = {
            "message_id": message_id,
            "msg_type": msg_type,
            "content": content,
            "sender": sender_dict,
            "create_time": create_time,
            "deleted": item.get("deleted", False),
            "updated": item.get("updated", False)
        }

        # 可选字段
        if item.get("thread_id"):
            formatted["thread_id"] = item.get("thread_id")
        elif item.get("parent_id"):
            formatted["reply_to"] = item.get("parent_id")

        if mentions:
            formatted["mentions"] = mentions

        return formatted

    def get_recent_docs_from_drive(
        self,
        date: Optional[datetime] = None,
        days: int = 1
    ) -> List[DocInfo]:
        """
        从飞书 Drive 获取最近打开和与我共享的文档

        Args:
            date: 目标日期（如果为None则使用今天）
            days: 获取最近几天的文档

        Returns:
            DocInfo 列表
        """
        if date is None:
            date = datetime.now()

        docs = []

        # 获取最近打开的文档
        recent_opened = self._get_recently_opened_docs(days)
        docs.extend(recent_opened)

        # 获取与我共享的文档
        shared_with_me = self._get_shared_with_me_docs(date, days)
        docs.extend(shared_with_me)

        # 去重（基于 URL）
        seen_urls = set()
        unique_docs = []
        for doc in docs:
            if doc.doc_url not in seen_urls:
                seen_urls.add(doc.doc_url)
                unique_docs.append(doc)

        return unique_docs

    def _get_recently_opened_docs(self, days: int = 1) -> List[DocInfo]:
        """获取最近打开的文档（简化实现，使用 feishu-data-collector skill）"""
        try:
            # 使用 feishu-data-collector skill 获取
            import subprocess
            from pathlib import Path

            cmd = [
                "claude",
                "--skill", "feishu-data-collector",
                "--arg", f"action=recent_docs",
                "--arg", f"days={days}",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(Path(__file__).parent.parent)
            )

            if result.returncode != 0:
                return []

            # 解析输出（简化处理）
            output = result.stdout
            docs = []
            # TODO: 根据 skill 实际输出格式解析
            return docs

        except Exception as e:
            return []

    def _get_shared_with_me_docs(self, date: datetime, days: int = 1) -> List[DocInfo]:
        """获取与我共享的文档（简化实现）"""
        # 从聊天记录中提取的文档链接已经在其他地方处理
        # 这里可以添加更多获取共享文档的逻辑
        return []

    def search_minutes_assistant_messages(
        self,
        days: int = 2
    ) -> List[Dict]:
        """
        搜索"智能纪要助手"机器人发的消息

        Args:
            days: 搜索最近几天的消息

        Returns:
            消息列表，包含文档链接
        """
        try:
            result = self.search_messages(
                relative_time=f"last_{days}_days",
                sender_type="bot",
                page_size=100
            )

            messages = result.get("messages", [])

            # 过滤出包含文档链接的消息
            minutes_messages = []
            for msg in messages:
                sender = msg.get("sender", {})
                sender_name = sender.get("name", "")
                content = msg.get("content", "")

                # 检查是否是智能纪要助手：
                # 1. 通过 sender name 匹配（旧方式）
                # 2. 通过消息内容中的 vc_assistant_notice 匹配（新方式）
                # 3. 通过消息内容中的"智能纪要"匹配（新方式）
                is_minutes = (
                    "智能纪要" in sender_name
                    or "minutes" in sender_name.lower()
                    or "vc_assistant_notice" in content
                    or "智能纪要" in content
                )

                if is_minutes:
                    # 提取文档链接
                    doc_links = self._extract_doc_links_from_content(content)
                    if doc_links:
                        msg["extracted_doc_links"] = doc_links
                        minutes_messages.append(msg)

            return minutes_messages

        except Exception as e:
            return []

    def _extract_doc_links_from_content(self, content: str) -> List[str]:
        """从消息内容中提取飞书文档链接"""
        if not content:
            return []

        pattern = r"https?://[^\s<>\"']+feishu[^\s<>\"']+"
        links = re.findall(pattern, content)
        return list(dict.fromkeys(links))  # 去重

    def extract_doc_links_from_text(self, content: str) -> List[str]:
        """从文本中提取飞书文档链接（公开方法）"""
        return self._extract_doc_links_from_content(content)

    def search_messages_enhanced(
        self,
        start_time: datetime,
        end_time: datetime,
        max_messages: int = 10000,
        interval_minutes: int = 30,
        max_concurrent: int = 10
    ) -> List[Dict]:
        """
        增强的消息获取方法：
        - 分开不同 chat_type
        - 按照时间间隔切片
        - 并发获取更多消息

        Args:
            start_time: 起始时间
            end_time: 结束时间
            max_messages: 最多获取多少条消息
            interval_minutes: 每个时间间隔的分钟数
            max_concurrent: 最大并发数

        Returns:
            消息列表
        """
        # ========== 预搜索获取 mentions 预填充缓存 ==========
        try:
            # 先进行一次轻量搜索，获取 mentions
            presearch_kwargs = {
                "page_size": 50,
                "page_token": None,
                "start_time": start_time,
                "end_time": end_time
            }
            pre_result = self.search_messages(**presearch_kwargs)
            pre_messages = pre_result.get("messages", [])
            if pre_messages:
                self._populate_cache_from_mentions(pre_messages)
        except Exception as e:
            pass
        # =========================================================

        all_messages = []
        seen_message_ids = set()

        # 生成时间间隔
        intervals = self._generate_time_intervals(start_time, end_time, interval_minutes)

        # 按 chat_type 分别获取
        chat_types = ["group", "p2p"]
        for chat_type in chat_types:
            if len(all_messages) >= max_messages:
                break

            # 并发获取每个时间间隔的消息
            messages = self._fetch_messages_with_intervals(
                intervals,
                chat_type=chat_type,
                max_messages=max_messages - len(all_messages),
                max_concurrent=max_concurrent,
                seen_message_ids=seen_message_ids
            )

            all_messages.extend(messages)
        return all_messages[:max_messages]

    def _generate_time_intervals(
        self,
        start_time: datetime,
        end_time: datetime,
        interval_minutes: int = 30
    ) -> List[Tuple[datetime, datetime]]:
        """生成时间间隔列表，凌晨2点到9点自动合并为60分钟间隔"""
        intervals = []
        current = start_time

        while current < end_time:
            hour = current.hour
            # 凌晨2点到9点消息少，用60分钟大间隔
            if 2 <= hour < 9:
                delta = timedelta(minutes=60)
            else:
                delta = timedelta(minutes=interval_minutes)
            interval_end = min(current + delta, end_time)
            intervals.append((current, interval_end))
            current = interval_end

        return intervals

    def _fetch_messages_with_intervals(
        self,
        intervals: List[Tuple[datetime, datetime]],
        chat_type: Optional[str],
        max_messages: int,
        max_concurrent: int,
        seen_message_ids: set
    ) -> List[Dict]:
        """并发获取多个时间间隔的消息"""
        all_messages = []
        lock = concurrent.futures.ThreadPoolExecutor(max_workers=1)  # 用于线程安全的添加

        def fetch_interval(interval: Tuple[datetime, datetime]) -> List[Dict]:
            """获取单个时间间隔的消息（带分页）"""
            interval_start, interval_end = interval
            messages = []
            page_token = ""
            max_iterations = 20  # 安全边界，防止无限循环
            iterations = 0

            while iterations < max_iterations:
                iterations += 1
                try:
                    result = self.search_messages(
                        start_time=interval_start,
                        end_time=interval_end,
                        chat_type=chat_type,
                        page_size=50,
                        page_token=page_token if page_token else None
                    )

                    for msg in result.get("messages", []):
                        msg_id = msg.get("message_id")
                        if msg_id and msg_id not in seen_message_ids:
                            seen_message_ids.add(msg_id)
                            messages.append(msg)

                    has_more = result.get("has_more", False)
                    page_token = result.get("page_token", "")
                    if not has_more or not page_token:
                        break

                except Exception as e:
                    break

            return messages

        # 并发获取
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            future_to_interval = {
                executor.submit(fetch_interval, interval): interval
                for interval in intervals
            }

            for future in concurrent.futures.as_completed(future_to_interval):
                if len(all_messages) >= max_messages:
                    # 取消剩余任务
                    for f in future_to_interval:
                        f.cancel()
                    break

                try:
                    messages = future.result()
                    if messages:
                        all_messages.extend(messages)
                except Exception as e:
                    pass

        return all_messages[:max_messages]

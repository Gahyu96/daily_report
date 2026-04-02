"""
飞书聊天 LLM 过滤模块
"""
import json
import tempfile
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


class LLMCallError(Exception):
    """LLM 调用失败"""
    pass


@dataclass
class ChatCategory:
    """聊天分类"""
    ALERT_GROUP = "alert_group"  # 告警群
    INVALID_CHAT = "invalid_chat"  # 无效闲聊
    VALID_GROUP = "valid_group"  # 有效群聊
    VALID_DIRECT = "valid_direct"  # 有效私聊
    UNKNOWN = "unknown"  # 未知分类


class ChatFilter:
    # 告警群关键词
    ALERT_KEYWORDS = [
        "告警", "报警", "监控", "通知群", "执行器", "错误", "异常",
        "超时", "失败", "推送", "expired", "error", "alert", "monitor"
    ]

    # 无效闲聊群关键词（注意：不要包含"通知"，避免误伤告警通知群）
    INVALID_KEYWORDS = [
        "收让饭", "贪玩之家", "吃饭", "订餐", "外卖", "餐厅",
        "投票", "考勤", "放假", "活动", "节日", "生日",
        "福利", "红包", "团购", "拼单", "打车", "班车"
    ]

    # 无效推送消息关键词
    PUSH_KEYWORDS = [
        "飞书春季新品", "飞书CLI", "直播预告", "活动通知",
        "新品见面会", "产品面对面", "共学通知", "新版本更新"
    ]

    # 用户标识（用于判断"与我相关"）
    USER_NAMES = ["梁嘉裕", "梁哥"]

    FILTER_PROMPT = """你是一个工作内容过滤助手。请从以下飞书聊天记录中，提取所有与工作相关的内容，过滤掉纯闲聊。

【工作内容定义】
- 任务安排、进度汇报、工作讨论
- 项目相关的沟通、问题解决
- 文档协作、代码 review
- 会议安排、会议纪要
- 任何与工作职责相关的对话

【闲聊定义】
- 纯问候、打招呼
- 生活琐事、娱乐八卦
- 与工作无关的闲聊

【输入】
{chat_content}

【输出要求】
- 只输出与工作相关的内容，保持原有的时间、人物、对话结构
- 如果某段对话部分相关部分不相关，只保留相关部分
- 如果没有任何工作相关内容，输出 "无工作相关内容"
- 不要添加任何额外的解释或说明
- 保持 Markdown 格式（群聊/私聊分组）

【重要】
- 严格判断，不要把闲聊误判为工作内容
- 但也不要漏过任何与工作相关的信息
- 对于模糊的内容，保守处理（不确定的就保留）
"""

    def __init__(self, arkplan_settings: str, token_limit: int = 15000):
        self.arkplan_settings = Path(arkplan_settings)
        self.token_limit = token_limit

    def classify_and_filter_chats(self, chat_content: str) -> Tuple[str, Dict[str, int]]:
        """
        分类并过滤聊天记录

        Returns:
            (过滤后的内容, 分类统计字典)
        """
        if not chat_content or not chat_content.strip():
            return "", {}

        # 先按会话拆分
        sessions = self._split_into_sessions(chat_content)

        filtered_parts = []
        stats = {
            ChatCategory.ALERT_GROUP: 0,
            ChatCategory.INVALID_CHAT: 0,
            ChatCategory.VALID_GROUP: 0,
            ChatCategory.VALID_DIRECT: 0,
            ChatCategory.UNKNOWN: 0
        }

        for session_header, session_content in sessions:
            category = self._classify_session(session_header, session_content)
            stats[category] += 1

            if category == ChatCategory.INVALID_CHAT:
                continue  # 直接跳过无效闲聊

            if category == ChatCategory.ALERT_GROUP:
                # 告警群：提取关键告警信息
                alert_summary = self._summarize_alerts(session_header, session_content)
                if alert_summary:
                    filtered_parts.append(alert_summary)
                continue

            # 有效内容：标记与我相关的消息
            marked_content = self._mark_relevant_messages(session_header, session_content)
            filtered_parts.append(marked_content)

        return "\n\n".join(filtered_parts), stats

    def _mark_relevant_messages(self, session_header: str, session_content: str) -> str:
        """
        标记群聊中与我相关的消息
        - 梁嘉裕发的消息前加 👤
        - @梁嘉裕 的消息前加 📌
        - 与梁嘉裕直接相关的对话上下文保留
        """
        lines = session_content.strip().split("\n")
        if not lines:
            return session_header

        marked_lines = []
        # 记录哪些消息是与我相关的
        relevant_line_indices = set()

        # 第一轮：识别与我相关的行
        for i, line in enumerate(lines):
            if self._is_user_message(line):
                relevant_line_indices.add(i)
                # 前一条和后一条也保留（上下文）
                if i > 0:
                    relevant_line_indices.add(i - 1)
                if i < len(lines) - 1:
                    relevant_line_indices.add(i + 1)
            elif self._is_mention_user(line):
                relevant_line_indices.add(i)

        # 第二轮：标记并输出
        for i, line in enumerate(lines):
            if i in relevant_line_indices:
                if self._is_user_message(line):
                    marked_lines.append(f"👤 {line}")
                elif self._is_mention_user(line):
                    marked_lines.append(f"📌 {line}")
                else:
                    marked_lines.append(f"   {line}")
            else:
                # 不相关的消息，降低权重（前面加空格，或者用更轻量的标记）
                marked_lines.append(f"   {line}")

        return f"{session_header}\n" + "\n".join(marked_lines)

    def _is_user_message(self, line: str) -> bool:
        """判断是否是用户（梁嘉裕）发的消息"""
        for name in self.USER_NAMES:
            if f"] {name}:" in line or f"]{name}:" in line:
                return True
        return False

    def _is_mention_user(self, line: str) -> bool:
        """判断是否@了用户（梁嘉裕）"""
        for name in self.USER_NAMES:
            if f"@{name}" in line:
                return True
        return False

    def _classify_session(self, session_header: str, session_content: str) -> str:
        """分类单个会话"""
        # 判断是群聊还是私聊
        is_group = "群聊：" in session_header
        chat_name = session_header.replace("## 群聊：", "").replace("## 私聊：", "").strip()

        # 私聊默认是有效内容，除非明确是推送
        if not is_group:
            # 检查内容是否是无效推送
            if self._is_push_message(session_content):
                return ChatCategory.INVALID_CHAT
            # 私聊默认为有效
            return ChatCategory.VALID_DIRECT

        # 群聊分类逻辑
        # 检查是否是无效闲聊（完全匹配关键词）
        for keyword in self.INVALID_KEYWORDS:
            if keyword == chat_name:  # 完全匹配，避免误伤
                return ChatCategory.INVALID_CHAT

        # 检查是否是告警群
        for keyword in self.ALERT_KEYWORDS:
            if keyword in chat_name:
                return ChatCategory.ALERT_GROUP

        # 群聊默认有效
        return ChatCategory.VALID_GROUP

    def _is_push_message(self, content: str) -> bool:
        """判断是否是无效推送消息"""
        # 推送消息通常有以下特征：
        # 1. 包含多个推送关键词
        # 2. 内容较短，主要是通知
        # 3. 包含"直播预告"、"新品"等明确推送词

        # 检查是否包含明确的推送关键词组合
        push_signals = 0
        if "飞书春季新品" in content or "新品见面会" in content:
            push_signals += 2
        if "直播预告" in content:
            push_signals += 2
        if "共学通知" in content:
            push_signals += 2
        if "活动通知" in content and "征集" in content:
            push_signals += 2

        # 只有强信号才判定为推送
        return push_signals >= 2

    def _summarize_alerts(self, session_header: str, session_content: str) -> str:
        """提取告警群的关键信息"""
        lines = session_content.strip().split("\n")
        if not lines:
            return ""

        # 简单提取：保留所有非纯表情、非图片的消息
        alert_lines = []
        for line in lines:
            if line.strip() and not line.strip().endswith("[图片]") and not line.strip().endswith("[sticker]"):
                alert_lines.append(line)

        if alert_lines:
            return f"{session_header}\n" + "\n".join(alert_lines)
        return ""

    def _split_into_sessions(self, content: str) -> List[Tuple[str, str]]:
        """将内容拆分为多个会话"""
        sessions = []
        current_header = None
        current_content = []

        lines = content.split("\n")
        for line in lines:
            if line.startswith("## 群聊：") or line.startswith("## 私聊："):
                if current_header:
                    sessions.append((current_header, "\n".join(current_content)))
                current_header = line
                current_content = []
            else:
                if current_header:
                    current_content.append(line)

        if current_header:
            sessions.append((current_header, "\n".join(current_content)))

        return sessions

    def filter_chat_content(self, chat_content: str) -> str:
        """过滤聊天内容（使用 LLM）"""
        if not chat_content:
            return ""

        chunks = self._split_into_chunks(chat_content)
        results = []

        for chunk in chunks:
            try:
                filtered = self._call_llm_filter(chunk)
                if filtered and filtered != "无工作相关内容":
                    results.append(filtered)
            except LLMCallError as e:
                print(f"Warning: LLM filter failed, using original chunk: {e}")
                results.append(chunk)

        if not results:
            return "无工作相关内容"

        return "\n\n".join(results)

    def _split_into_chunks(self, content: str) -> List[str]:
        """按会话分片"""
        chunks = []
        current_chunk = []
        current_size = 0

        lines = content.split("\n")

        for line in lines:
            # 估算 token 数（简单估算）
            line_size = len(line)  # 简化：中文字符 = 1 token

            if line.startswith("## "):
                # 新会话开始
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_size = line_size
            else:
                if current_size + line_size > self.token_limit and current_chunk:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = [line]
                    current_size = line_size
                else:
                    current_chunk.append(line)
                    current_size += line_size

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks

    def _call_llm_filter(self, chunk: str) -> str:
        """调用 LLM 过滤"""
        prompt = self.FILTER_PROMPT.format(chat_content=chunk)

        try:
            # 构建请求数据
            request_data = {
                "model": "doubao-seed-2-0-pro-260215",
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            }

            # 构建curl命令
            cmd = [
                "curl",
                "https://ark.cn-beijing.volces.com/api/v3/responses",
                "-H", "Authorization: Bearer 3a948797-497c-4a2c-b9d2-7b3d7771b788",
                "-H", "Content-Type: application/json",
                "-d", json.dumps(request_data, ensure_ascii=False)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                raise LLMCallError(f"LLM call failed with code {result.returncode}: {result.stderr}")

            # 解析响应
            try:
                response_data = json.loads(result.stdout)
                llm_result = ""
                # 火山引擎响应格式
                if isinstance(response_data, dict):
                    if "output" in response_data and isinstance(response_data["output"], list):
                        # 遍历output数组找到message类型的内容
                        for item in response_data["output"]:
                            if item.get("type") == "message" and isinstance(item.get("content"), list):
                                for content_item in item["content"]:
                                    if content_item.get("type") == "output_text":
                                        llm_result = content_item.get("text", "")
                                        break
                            if llm_result:
                                break
                return llm_result.strip()
            except Exception as e:
                raise LLMCallError(f"Failed to parse LLM response: {e}, raw response: {result.stdout[:500]}") from e

        except subprocess.TimeoutExpired as e:
            raise LLMCallError(f"LLM call timed out: {e}") from e

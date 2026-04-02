"""
Claude 会话采集器
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


class ClaudeCollector:
    """Claude 会话采集器"""

    def __init__(self, history_path: str, projects_path: str):
        self.history_path = Path(os.path.expanduser(history_path))
        self.projects_path = Path(os.path.expanduser(projects_path))

    def collect_for_date(self, date: datetime) -> str:
        """
        采集指定日期的会话

        Args:
            date: 日期（只取年月日部分）

        Returns:
            会话文本内容
        """
        date_start = datetime(date.year, date.month, date.day, 0, 0, 0)
        date_end = datetime(date.year, date.month, date.day, 23, 59, 59)

        texts = []

        # 从 history.jsonl 采集
        if self.history_path.exists():
            texts.extend(self._parse_history(date_start, date_end))

        # 从 projects 目录采集
        if self.projects_path.exists():
            texts.extend(self._parse_projects(date_start, date_end))

        return "\n\n".join(texts) if texts else ""

    def _parse_history(self, start: datetime, end: datetime) -> List[str]:
        """解析 history.jsonl"""
        texts = []
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        ts = self._get_timestamp(data)
                        if ts and start <= ts <= end:
                            text = self._entry_to_text(data, include_timestamp=True)
                            if text:
                                texts.append(text)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Warning: Failed to read history: {e}")
        return texts

    def _parse_projects(self, start: datetime, end: datetime) -> List[str]:
        """解析 projects 目录"""
        import os
        from datetime import datetime

        texts = []
        try:
            for jsonl_path in self.projects_path.rglob("*.jsonl"):
                if "memory" in jsonl_path.parts:
                    continue

                # 快速过滤：如果文件修改时间早于起始时间，跳过（不可能包含目标日期的内容）
                mtime = datetime.fromtimestamp(os.path.getmtime(jsonl_path))
                if mtime < start:
                    continue

                try:
                    session_texts = self._parse_session_file(jsonl_path, start, end)
                    texts.extend(session_texts)
                except Exception as e:
                    print(f"Warning: Failed to parse {jsonl_path}: {e}")
        except Exception as e:
            print(f"Warning: Failed to read projects: {e}")
        return texts

    def _parse_session_file(self, jsonl_path: Path, start: datetime, end: datetime) -> List[str]:
        """解析单个会话文件"""
        texts = []
        session_id = jsonl_path.stem

        try:
            # 尝试 utf-8，失败用 latin-1
            try:
                f = open(jsonl_path, "r", encoding="utf-8")
            except UnicodeDecodeError:
                f = open(jsonl_path, "r", encoding="latin-1")

            with f:
                session_has_content = False
                session_texts = []

                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        ts = self._get_timestamp(data)
                        if ts and start <= ts <= end:
                            text = self._entry_to_text(data, include_timestamp=True)
                            if text:
                                session_texts.append(text)
                                session_has_content = True
                    except json.JSONDecodeError:
                        continue

                if session_has_content:
                    texts.append(f"--- 会话: {session_id} ---\n" + "\n".join(session_texts))

        except Exception as e:
            print(f"Warning: Failed to read {jsonl_path}: {e}")

        return texts

    def _get_time_range_from_content(self, content: str) -> Optional[str]:
        """从内容中提取时间范围"""
        import re
        time_pattern = r'\[(\d{2}:\d{2}:\d{2})\]'
        times = re.findall(time_pattern, content)
        if times:
            return f"{times[0]} ~ {times[-1]}"
        return None

    def _get_timestamp(self, data: Dict[str, Any]) -> Optional[datetime]:
        """从数据中获取时间戳"""
        ts_val = data.get("timestamp")
        if ts_val:
            if isinstance(ts_val, (int, float)):
                if ts_val > 1e12:
                    return datetime.fromtimestamp(ts_val / 1000.0)
                else:
                    return datetime.fromtimestamp(ts_val)
            elif isinstance(ts_val, str):
                # 先尝试纯数字字符串（history.jsonl 中时间戳以字符串形式存储）
                try:
                    numeric = float(ts_val)
                    if numeric > 1e12:
                        return datetime.fromtimestamp(numeric / 1000.0)
                    else:
                        return datetime.fromtimestamp(numeric)
                except (ValueError, TypeError):
                    pass
                # 再尝试 ISO 格式字符串，如 "2026-03-26T06:20:00.449Z"
                try:
                    if ts_val.endswith('Z'):
                        dt = datetime.fromisoformat(ts_val.replace('Z', '+00:00'))
                        return dt.replace(tzinfo=None)
                    else:
                        dt = datetime.fromisoformat(ts_val)
                        if dt.tzinfo:
                            return dt.replace(tzinfo=None)
                        return dt
                except (ValueError, TypeError):
                    pass
        return None

    def _entry_to_text(self, data: Dict[str, Any], include_timestamp: bool = True) -> str:
        """将一条记录转换为文本"""
        # 支持多种消息格式
        msg_type = data.get("type")

        # 检查是否有 message 对象（新格式）
        has_message = "message" in data and isinstance(data.get("message"), dict)

        # 确定角色和内容
        role = None
        content = ""

        if has_message:
            message_obj = data.get("message", {})
            role = message_obj.get("role")
            content = message_obj.get("content", "")
        else:
            # 旧格式
            role = data.get("role", msg_type)
            content = data.get("content") or data.get("display") or ""

        # 如果没有明确的 role，从 type 推断
        if not role:
            if msg_type == "user":
                role = "user"
            elif msg_type == "assistant":
                role = "assistant"
            elif msg_type == "system":
                role = "system"

        # history.jsonl 的命令历史格式：只有 display 字段，无 role/type
        if not role and data.get("display"):
            role = "user"
            if not content:
                content = data["display"]

        # 只处理有效的角色类型
        if role not in ["user", "assistant", "system"]:
            return ""

        # 如果没有内容，跳过
        if not content:
            return ""

        parts = []

        # 时间戳
        if include_timestamp:
            ts = self._get_timestamp(data)
            if ts:
                time_str = ts.strftime("%Y-%m-%d %H:%M:%S")
                parts.append(f"[{time_str}]")

        # 角色
        if role == "assistant":
            parts.append("AI:")
        elif role == "system":
            parts.append("System:")
        else:
            parts.append("User:")

        if content:
            parts.append(str(content))

        return " ".join(parts) if len(parts) > 1 else ""

    def collect_structured(self, date: datetime) -> Dict[str, str]:
        """
        返回结构化数据而不是合并文本

        Returns: {
            "claude_history": "历史会话内容",
            "claude_projects": "项目会话内容"
        }
        """
        date_start = datetime(date.year, date.month, date.day, 0, 0, 0)
        date_end = datetime(date.year, date.month, date.day, 23, 59, 59)

        result = {}

        # 采集 history
        if self.history_path.exists():
            texts = self._parse_history(date_start, date_end)
            result["claude_history"] = "\n\n".join(texts) if texts else ""

        # 采集 projects
        if self.projects_path.exists():
            texts = self._parse_projects(date_start, date_end)
            content = "\n\n".join(texts) if texts else ""
            result["claude_projects"] = self._truncate_long_content(content)

        return result

    def collect_history_for_date(self, date: datetime) -> str:
        """单独采集 history"""
        date_start = datetime(date.year, date.month, date.day, 0, 0, 0)
        date_end = datetime(date.year, date.month, date.day, 23, 59, 59)
        texts = self._parse_history(date_start, date_end)
        return "\n\n".join(texts) if texts else ""

    def collect_projects_for_date(self, date: datetime) -> str:
        """单独采集 projects"""
        date_start = datetime(date.year, date.month, date.day, 0, 0, 0)
        date_end = datetime(date.year, date.month, date.day, 23, 59, 59)
        texts = self._parse_projects(date_start, date_end)
        return "\n\n".join(texts) if texts else ""

    def _truncate_long_content(self, content: str, max_chars: int = 50000) -> str:
        """
        超长内容取最后部分
        保留开头说明 + 最后 N 字符
        """
        if len(content) <= max_chars:
            return content
        keep_chars = max_chars - 100  # 留空间给说明
        return (
            f"[内容过长，已截断，保留最后 {keep_chars} 字符]\n\n"
            f"...\n\n"
            f"{content[-keep_chars:]}"
        )

# 飞书集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 集成飞书聊天记录和文档采集功能，同时添加未完成任务继承机制

**Architecture:** 模块化扩展现有 daily_report 项目，新增 feishu/ 和 inheritance/ 模块，通过清晰接口与主流程整合

**Tech Stack:** Python 3, PyYAML, 飞书 Open API, feishu-docx-export skill

---

## 文件结构映射

| 文件 | 操作 | 职责 |
|------|------|------|
| `feishu/__init__.py` | Create | 包初始化 |
| `feishu/__main__.py` | Create | 模块入口 (python -m feishu) |
| `feishu/auth.py` | Create | 飞书 OAuth 认证和 token 管理 |
| `feishu/collector.py` | Create | 飞书聊天和文档列表采集 |
| `feishu/filter.py` | Create | LLM 闲聊过滤 |
| `feishu/exporter.py` | Create | 文档导出和智能总结 |
| `inheritance/__init__.py` | Create | 包初始化 |
| `inheritance/manager.py` | Create | 未完成任务继承管理 |
| `config.yaml` | Modify | 添加飞书配置 |
| `.gitignore` | Modify | 添加飞书缓存 |
| `daily_report.py` | Modify | 整合飞书数据源 |
| `generator.py` | Modify | 更新 LLM 提示词 |
| `requirements.txt` | Modify | 添加 requests 依赖 |

---

### Task 1: 项目基础结构和配置

**Files:**
- Create: `feishu/__init__.py`
- Create: `inheritance/__init__.py`
- Modify: `config.yaml`
- Modify: `.gitignore`

- [ ] **Step 1: 创建 feishu/__init__.py**

```python
"""
飞书集成模块
"""
from .auth import FeishuAuthenticator
from .collector import FeishuCollector, ChatMessage, DocInfo
from .filter import ChatFilter
from .exporter import FeishuDocExporter

__all__ = [
    "FeishuAuthenticator",
    "FeishuCollector",
    "ChatMessage",
    "DocInfo",
    "ChatFilter",
    "FeishuDocExporter",
]
```

- [ ] **Step 2: 创建 inheritance/__init__.py**

```python
"""
任务继承模块
"""
from .manager import TaskInheritanceManager, InheritedTask

__all__ = [
    "TaskInheritanceManager",
    "InheritedTask",
]
```

- [ ] **Step 3: 更新 config.yaml**

读取现有 config.yaml，添加飞书配置：

```yaml
# 现有配置保持不变
claude:
  history_path: "~/.claude/history.jsonl"
  projects_path: "~/.claude/projects"

llm:
  arkplan_settings: "~/.claude/arkplan.json"

report:
  base_dir: "reports"

# 新增：飞书配置
feishu:
  enabled: false  # 默认不启用
  app_id: "your_app_id_here"
  app_secret: "your_app_secret_here"
  env_dir: "~/.feishu_env"
  chat_cache_dir: "reports/feishu_chat_cache"
  temp_dir: "/tmp/feishu_docs"
  llm_token_limit: 15000
  recent_docs_days: 7
  doc_summary_threshold: 3500
  redirect_uri: "http://localhost:8080/callback"
```

- [ ] **Step 4: 更新 .gitignore**

如果没有 .gitignore 则创建，添加：

```gitignore
# 飞书缓存
reports/feishu_chat_cache/
```

- [ ] **Step 5: Commit**

```bash
git add feishu/__init__.py inheritance/__init__.py config.yaml
git add .gitignore || true
git commit -m "feat: add feishu integration base structure and config"
```

---

### Task 2: 实现任务继承模块

**Files:**
- Create: `inheritance/manager.py`

- [ ] **Step 1: 创建 inheritance/manager.py**

```python
"""
任务继承管理模块
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional


@dataclass
class InheritedTask:
    task_text: str
    source_date: str
    source_type: str


class TaskInheritanceManager:
    def __init__(self, reports_base_dir: str = "reports"):
        self.reports_base_dir = Path(reports_base_dir)
        self.daily_dir = self.reports_base_dir / "daily"
        self.weekly_dir = self.reports_base_dir / "weekly"
        self.monthly_dir = self.reports_base_dir / "monthly"

    def get_incomplete_tasks_from_daily(self, date: datetime) -> List[InheritedTask]:
        """从日报获取未完成任务（date 是要生成报告的日期，取前一天）"""
        yesterday = date - timedelta(days=1)
        filename = f"daily_report_{yesterday.strftime('%Y-%m-%d')}.md"
        filepath = self.daily_dir / filename
        return self._get_incomplete_tasks_from_file(
            filepath, yesterday.strftime("%Y-%m-%d"), "daily"
        )

    def get_incomplete_tasks_from_weekly(self, year: int, week: int) -> List[InheritedTask]:
        """从周报获取未完成任务"""
        # 计算上一周
        prev_week = week - 1
        prev_year = year
        if prev_week < 1:
            prev_week = 52
            prev_year -= 1
        filename = f"weekly_report_{prev_year}-W{prev_week:02d}.md"
        filepath = self.weekly_dir / filename
        return self._get_incomplete_tasks_from_file(
            filepath, f"{prev_year}-W{prev_week:02d}", "weekly"
        )

    def get_incomplete_tasks_from_monthly(self, year: int, month: int) -> List[InheritedTask]:
        """从月报获取未完成任务"""
        # 计算上一月
        prev_month = month - 1
        prev_year = year
        if prev_month < 1:
            prev_month = 12
            prev_year -= 1
        filename = f"monthly_report_{prev_year}-{prev_month:02d}.md"
        filepath = self.monthly_dir / filename
        return self._get_incomplete_tasks_from_file(
            filepath, f"{prev_year}-{prev_month:02d}", "monthly"
        )

    def _get_incomplete_tasks_from_file(
        self, filepath: Path, source_date: str, source_type: str
    ) -> List[InheritedTask]:
        """从报告文件读取未完成任务"""
        if not filepath.exists():
            return []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return self._extract_incomplete_tasks(content, source_date, source_type)
        except Exception as e:
            print(f"Warning: Failed to read {filepath}: {e}")
            return []

    def _extract_incomplete_tasks(
        self, report_content: str, source_date: str, source_type: str
    ) -> List[InheritedTask]:
        """从报告内容中提取未完成任务"""
        tasks = []
        # 匹配: "- [ ] 任务内容"
        pattern = r"^\s*-\s*\[\s+\]\s*(.+)$"
        for line in report_content.split("\n"):
            match = re.match(pattern, line)
            if match:
                task_text = match.group(1).strip()
                if task_text:
                    tasks.append(InheritedTask(
                        task_text=task_text,
                        source_date=source_date,
                        source_type=source_type
                    ))
        return tasks

    def _format_tasks_for_prompt(self, tasks: List[InheritedTask]) -> str:
        """格式化任务列表给 LLM 提示词"""
        if not tasks:
            return ""

        if tasks[0].source_type == "daily":
            title = "【昨日未完成任务】"
            desc = "以下是前一天未完成的任务，请在今日日报中继承并更新状态："
        elif tasks[0].source_type == "weekly":
            title = "【上周未完成任务】"
            desc = "以下是上周未完成的任务，请在本周周报中继承并更新状态："
        else:
            title = "【上月未完成任务】"
            desc = "以下是上月未完成的任务，请在本月月报中继承并更新状态："

        lines = [title, desc]
        for task in tasks:
            lines.append(f"- [ ] {task.task_text}")
        return "\n".join(lines)
```

- [ ] **Step 2: Commit**

```bash
git add inheritance/manager.py
git commit -m "feat: add task inheritance module"
```

---

### Task 3: 实现飞书认证模块

**Files:**
- Create: `feishu/auth.py`
- Create: `feishu/__main__.py`

- [ ] **Step 1: 创建 feishu/auth.py**

```python
"""
飞书 OAuth 认证模块
"""
import json
import os
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import requests


# 自定义异常
class TokenExpiredError(Exception):
    """Access token 过期"""
    pass


class RefreshTokenExpiredError(Exception):
    """Refresh token 过期"""
    pass


class APIError(Exception):
    """飞书 API 错误"""
    def __init__(self, code: int, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(f"API Error {code}: {msg}")


class NetworkError(Exception):
    """网络请求错误"""
    pass


class FeishuAuthenticator:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        env_dir: str = "~/.feishu_env",
        redirect_uri: str = "http://localhost:8080/callback"
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.env_dir = Path(os.path.expanduser(env_dir))
        self.redirect_uri = redirect_uri
        self.token_cache_path = self.env_dir / "token_cache.json"
        self._ensure_env_dir()

    def _ensure_env_dir(self) -> None:
        """确保环境目录存在并设置正确权限"""
        self.env_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.env_dir, 0o700)
        except Exception:
            pass

    def get_authorization_url(self) -> str:
        """获取授权 URL"""
        base_url = "https://open.feishu.cn/open-apis/authen/v1/authorize"
        params = {
            "app_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "im:message drive:drive drive:file",
        }
        return f"{base_url}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """用授权码换取 token"""
        url = "https://open.feishu.cn/open-apis/authen/v1/access_token"
        body = {
            "grant_type": "authorization_code",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "code": code,
        }
        try:
            resp = requests.post(url, json=body, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise NetworkError(f"Network request failed: {e}") from e

        if data.get("code") != 0:
            raise APIError(data.get("code", -1), data.get("msg", "Unknown error"))

        token_data = data["data"]
        now = int(time.time())
        token_data["expires_at"] = now + token_data["expires_in"]
        token_data["refresh_expires_at"] = now + token_data["refresh_expires_in"]

        self._save_token_cache(token_data)
        return token_data

    def get_access_token(self) -> str:
        """获取有效的 access_token（自动刷新）"""
        token_data = self._load_token_cache()
        if not token_data:
            raise TokenExpiredError("No token found, please authenticate first")

        now = int(time.time())
        if now >= token_data["expires_at"]:
            # Token 过期，尝试刷新
            token_data = self.refresh_access_token()

        return token_data["access_token"]

    def refresh_access_token(self) -> Dict[str, Any]:
        """刷新 access_token"""
        token_data = self._load_token_cache()
        if not token_data:
            raise TokenExpiredError("No token found, please authenticate first")

        now = int(time.time())
        if now >= token_data["refresh_expires_at"]:
            raise RefreshTokenExpiredError("Refresh token expired, please re-authenticate")

        url = "https://open.feishu.cn/open-apis/authen/v1/refresh_access_token"
        body = {
            "grant_type": "refresh_token",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "refresh_token": token_data["refresh_token"],
        }
        try:
            resp = requests.post(url, json=body, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise NetworkError(f"Network request failed: {e}") from e

        if data.get("code") != 0:
            raise APIError(data.get("code", -1), data.get("msg", "Unknown error"))

        new_token_data = data["data"]
        now = int(time.time())
        new_token_data["expires_at"] = now + new_token_data["expires_in"]
        new_token_data["refresh_expires_at"] = now + new_token_data["refresh_expires_in"]

        self._save_token_cache(new_token_data)
        return new_token_data

    def _save_token_cache(self, token_data: Dict[str, Any]) -> None:
        """保存 token 缓存"""
        with open(self.token_cache_path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, ensure_ascii=False, indent=2)
        try:
            os.chmod(self.token_cache_path, 0o600)
        except Exception:
            pass

    def _load_token_cache(self) -> Optional[Dict[str, Any]]:
        """加载 token 缓存"""
        if not self.token_cache_path.exists():
            return None
        try:
            with open(self.token_cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load token cache: {e}")
            return None
```

- [ ] **Step 2: 创建 feishu/__main__.py**

```python
"""
飞书模块入口，支持 python -m feishu 命令
"""
import argparse
import sys
from pathlib import Path

# 添加父目录到 path 以便导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from feishu.auth import FeishuAuthenticator, RefreshTokenExpiredError
from daily_report import load_config


def main():
    parser = argparse.ArgumentParser(description="飞书认证管理")
    parser.add_argument("command", choices=["auth", "refresh"], help="命令: auth-首次授权, refresh-刷新token")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    args = parser.parse_args()

    config = load_config(args.config)
    feishu_config = config.get("feishu", {})

    if not feishu_config:
        print("错误: 配置文件中未找到 feishu 配置")
        sys.exit(1)

    auth = FeishuAuthenticator(
        feishu_config["app_id"],
        feishu_config["app_secret"],
        feishu_config.get("env_dir", "~/.feishu_env"),
        feishu_config.get("redirect_uri", "http://localhost:8080/callback")
    )

    if args.command == "auth":
        # 首次授权流程
        url = auth.get_authorization_url()
        print(f"请访问以下 URL 进行授权:\n{url}")
        code = input("请输入授权码: ")
        token_data = auth.exchange_code_for_token(code)
        print(f"授权成功! Token 已保存")
        print(f"Access token 过期时间: {datetime.fromtimestamp(token_data['expires_at'])}")
    elif args.command == "refresh":
        # 刷新 token
        try:
            token_data = auth.refresh_access_token()
            print(f"Token 刷新成功!")
            print(f"新过期时间: {datetime.fromtimestamp(token_data['expires_at'])}")
        except RefreshTokenExpiredError:
            print("错误: refresh_token 已过期，请重新运行 'python -m feishu auth' 进行授权")
            sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 更新 requirements.txt**

添加 requests 依赖（如果没有的话）：

```
PyYAML>=6.0
requests>=2.31.0
```

- [ ] **Step 4: Commit**

```bash
git add feishu/auth.py feishu/__main__.py requirements.txt
git commit -m "feat: add feishu auth module"
```

---

### Task 4: 实现飞书采集模块

**Files:**
- Create: `feishu/collector.py`

- [ ] **Step 1: 创建 feishu/collector.py**

```python
"""
飞书聊天和文档采集模块
"""
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
import requests


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
    def __init__(self, access_token: str, cache_base_dir: str = "reports/feishu_chat_cache"):
        self.access_token = access_token
        self.cache_base_dir = Path(cache_base_dir)
        self.cache_base_dir.mkdir(parents=True, exist_ok=True)

    def collect_chat_for_date(self, date: datetime, force: bool = False) -> Path:
        """采集指定日期的聊天记录"""
        cache_path = self.cache_base_dir / f"{date.strftime('%Y-%m-%d')}.md"

        if not force and cache_path.exists():
            return cache_path

        # 计算时间范围（毫秒时间戳）
        start_ts = int(datetime(date.year, date.month, date.day, 0, 0, 0).timestamp() * 1000)
        end_ts = int(datetime(date.year, date.month, date.day, 23, 59, 59).timestamp() * 1000)

        # 获取所有会话
        chats = self._get_chats_list()

        # 采集每个会话的消息
        all_messages = []
        for chat in chats:
            try:
                messages = self._get_chat_messages(chat["chat_id"], start_ts, end_ts)
                for msg in messages:
                    msg.chat_name = chat.get("name", "未知会话")
                    msg.chat_type = chat.get("chat_type", "unknown")
                all_messages.extend(messages)
            except Exception as e:
                print(f"Warning: Failed to collect chat {chat.get('chat_id')}: {e}")

        # 保存缓存
        return self._save_chat_cache(date, all_messages)

    def _get_chats_list(self) -> List[dict]:
        """获取会话列表"""
        url = "https://open.feishu.cn/open-apis/im/v1/chats"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        chats = []
        page_token = ""

        while True:
            params = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token

            try:
                resp = self._api_request("GET", url, headers=headers, params=params)
            except RateLimitError:
                time.sleep(2)
                continue
            except Exception as e:
                raise ChatListError(f"Failed to get chat list: {e}") from e

            data = resp.get("data", {})
            items = data.get("items", [])
            chats.extend(items)

            page_token = data.get("page_token", "")
            if not data.get("has_more", False) or not page_token:
                break

        return chats

    def _get_chat_messages(self, chat_id: str, start_time: int, end_time: int) -> List[ChatMessage]:
        """获取会话消息"""
        url = f"https://open.feishu.cn/open-apis/im/v1/messages"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        messages = []
        page_token = ""

        while True:
            params = {
                "container_id_type": "chat",
                "container_id": chat_id,
                "sort_type": "ByCreateTimeDesc",
                "page_size": 100,
            }
            if page_token:
                params["page_token"] = page_token

            try:
                resp = self._api_request("GET", url, headers=headers, params=params)
            except RateLimitError:
                time.sleep(2)
                continue
            except Exception as e:
                raise MessageListError(f"Failed to get messages: {e}") from e

            data = resp.get("data", {})
            items = data.get("items", [])

            for item in items:
                create_time = int(item.get("create_time", 0))
                if create_time < start_time:
                    continue
                if create_time > end_time:
                    continue

                sender = item.get("sender", {})
                messages.append(ChatMessage(
                    chat_id=chat_id,
                    chat_name="",
                    chat_type="",
                    sender_id=sender.get("id", ""),
                    sender_name=sender.get("name", "未知用户"),
                    content=self._parse_message_content(item),
                    timestamp=datetime.fromtimestamp(create_time / 1000),
                ))

            page_token = data.get("page_token", "")
            if not data.get("has_more", False) or not page_token:
                break

        # 按时间正序排列
        messages.sort(key=lambda m: m.timestamp)
        return messages

    def _parse_message_content(self, msg_item: dict) -> str:
        """解析消息内容"""
        body = msg_item.get("body", {})
        content = body.get("content", "")
        if content:
            try:
                import json
                data = json.loads(content)
                if isinstance(data, dict):
                    return data.get("elements", [{}])[0].get("text", content)
            except Exception:
                pass
        return content or ""

    def _save_chat_cache(self, date: datetime, messages: List[ChatMessage]) -> Path:
        """保存聊天缓存"""
        cache_path = self.cache_base_dir / f"{date.strftime('%Y-%m-%d')}.md"

        lines = [f"# 飞书聊天记录 - {date.strftime('%Y-%m-%d')}", ""]

        # 按会话分组
        chat_groups = {}
        for msg in messages:
            key = (msg.chat_id, msg.chat_name, msg.chat_type)
            if key not in chat_groups:
                chat_groups[key] = []
            chat_groups[key].append(msg)

        for (chat_id, chat_name, chat_type), msgs in chat_groups.items():
            type_label = "群聊" if chat_type == "group" else "私聊"
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
        # 【设计说明】简化原因：
        # 1. 飞书 API 获取最近访问文档需要调用 drive/v1/files 接口并按访问时间筛选
        # 2. 实际使用中，聊天记录中的文档链接已足够覆盖大部分工作相关文档
        # 3. 此简化不影响核心功能（从聊天中提取文档链接）
        # 4. 后续可根据需要扩展此方法
        return []

    def extract_doc_links_from_chat(self, chat_cache_path: Path) -> List[str]:
        """从聊天缓存中提取飞书文档链接"""
        if not chat_cache_path.exists():
            return []

        with open(chat_cache_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 匹配飞书文档链接
        pattern = r"https?://[^\s]*feishu\.[^\s]*/(docx|sheet|bitable|wiki)/[^\s]+"
        links = re.findall(pattern, content)
        # 上面的正则可能需要调整，简化为:
        pattern = r"https?://[^\s<>\"']+feishu[^\s<>\"']+"
        links = re.findall(pattern, content)
        # 去重
        return list(dict.fromkeys(links))

    def _api_request(self, method: str, url: str, **kwargs) -> dict:
        """API 请求封装，带重试和限流处理"""
        retry_count = 0
        max_retries = 3
        delays = [1, 2, 4]

        while retry_count <= max_retries:
            try:
                resp = requests.request(method, url, timeout=30, **kwargs)
                data = resp.json()

                if data.get("code") == 99991663:  # 限流码
                    if retry_count < max_retries:
                        delay = delays[min(retry_count, len(delays) - 1)]
                        time.sleep(delay)
                        retry_count += 1
                        continue
                    raise RateLimitError("API rate limit exceeded")

                return data

            except requests.RequestException as e:
                if retry_count < max_retries:
                    delay = delays[min(retry_count, len(delays) - 1)]
                    time.sleep(delay)
                    retry_count += 1
                    continue
                raise
```

- [ ] **Step 2: Commit**

```bash
git add feishu/collector.py
git commit -m "feat: add feishu collector module"
```

---

### Task 5: 实现飞书聊天过滤模块

**Files:**
- Create: `feishu/filter.py`

- [ ] **Step 1: 创建 feishu/filter.py**

```python
"""
飞书聊天 LLM 过滤模块
"""
import tempfile
import subprocess
from pathlib import Path
from typing import List


class LLMCallError(Exception):
    """LLM 调用失败"""
    pass


class ChatFilter:
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

    def filter_chat(self, chat_cache_path: Path) -> str:
        """过滤聊天记录"""
        if not chat_cache_path.exists():
            return ""

        with open(chat_cache_path, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = self._split_into_chunks(content)
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

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
            f.write(prompt)
            temp_path = f.name

        try:
            cmd = [
                "happy",
                "--settings", str(self.arkplan_settings),
                "-p", temp_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                raise LLMCallError(f"happy failed with code {result.returncode}: {result.stderr}")

            return result.stdout.strip()

        except subprocess.TimeoutExpired as e:
            raise LLMCallError(f"LLM call timed out: {e}") from e
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass
```

- [ ] **Step 2: Commit**

```bash
git add feishu/filter.py
git commit -m "feat: add feishu chat filter module"
```

---

### Task 6: 实现飞书文档导出模块

**Files:**
- Create: `feishu/exporter.py`

- [ ] **Step 1: 创建 feishu/exporter.py**

```python
"""
飞书文档导出与智能总结模块
"""
import tempfile
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Optional, List


class DocExportError(Exception):
    """文档导出失败"""
    pass


class DocSummaryError(Exception):
    """文档总结失败"""
    pass


class FeishuDocExporter:
    DOC_SUMMARY_PROMPT = """请对以下飞书文档内容生成一个简洁的摘要，突出与工作相关的关键信息。

【要求】
- 摘要长度控制在 300-500 字
- 保留关键结论、任务、决策、时间节点
- 如果是会议纪要，保留参会人、议题、决议
- 如果是项目文档，保留项目状态、关键里程碑、待办事项
- 不要遗漏重要的工作信息

【文档内容】
{doc_content}

【输出格式】
直接输出摘要，不要添加额外说明。
"""

    def __init__(
        self,
        temp_dir: str = "/tmp/feishu_docs",
        arkplan_settings: str = "~/.claude/arkplan.json",
        summary_threshold: int = 3500
    ):
        self.temp_dir = Path(temp_dir)
        self.arkplan_settings = Path(arkplan_settings)
        self.summary_threshold = summary_threshold
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def export_doc(self, doc_url: str) -> Optional[str]:
        """导出单个文档"""
        export_path = self._call_feishu_export_skill(doc_url)
        if not export_path:
            return None

        content = self._read_exported_doc(export_path)
        if not content:
            return None

        return self._summarize_doc_if_needed(content, doc_url)

    def export_docs(self, doc_urls: List[str]) -> Dict[str, str]:
        """批量导出文档"""
        results = {}
        for url in doc_urls:
            try:
                content = self.export_doc(url)
                if content:
                    results[url] = content
            except Exception as e:
                print(f"Warning: Failed to export doc {url}: {e}")
        return results

    def cleanup(self) -> None:
        """清理临时目录"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _call_feishu_export_skill(self, doc_url: str) -> Optional[Path]:
        """调用 feishu-docx-export skill"""
        try:
            cmd = [
                "happy",
                "--settings", str(self.arkplan_settings),
                "--skill", "feishu-docx-export",
                "--arg", f"doc_url={doc_url}",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                raise DocExportError(f"Skill failed with code {result.returncode}: {result.stderr}")

            # 尝试解析输出 - 根据 skill 的实际输出格式调整
            output = result.stdout.strip()

            # 简化：假设 skill 输出 Markdown 内容
            if output and len(output) > 10:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".md", dir=self.temp_dir, encoding="utf-8", delete=False) as f:
                    f.write(output)
                    return Path(f.name)

            return None

        except subprocess.TimeoutExpired as e:
            raise DocExportError(f"Skill timed out: {e}") from e

    def _read_exported_doc(self, export_path: Path) -> Optional[str]:
        """读取导出的文档"""
        if not export_path.exists():
            return None
        try:
            with open(export_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"Warning: Failed to read exported doc: {e}")
            return None

    def _summarize_doc_if_needed(self, content: str, doc_url: str) -> str:
        """混合方案：短文档直接返回，长文档先总结"""
        if len(content) <= self.summary_threshold:
            return content

        try:
            summary = self._call_doc_summary(content)
            return f"[摘要] {summary}"
        except DocSummaryError as e:
            print(f"Warning: Failed to summarize doc, using truncated content: {e}")
            return content[:self.summary_threshold] + "\n\n[内容过长已截断]"

    def _call_doc_summary(self, content: str) -> str:
        """调用 LLM 生成文档摘要"""
        prompt = self.DOC_SUMMARY_PROMPT.format(doc_content=content[:10000])  # 限制输入长度

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
            f.write(prompt)
            temp_path = f.name

        try:
            cmd = [
                "happy",
                "--settings", str(self.arkplan_settings),
                "-p", temp_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                raise DocSummaryError(f"LLM failed with code {result.returncode}: {result.stderr}")

            return result.stdout.strip()

        except subprocess.TimeoutExpired as e:
            raise DocSummaryError(f"Summary timed out: {e}") from e
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass
```

- [ ] **Step 2: Commit**

```bash
git add feishu/exporter.py
git commit -m "feat: add feishu doc exporter module"
```

---

### Task 7: 整合到主流程 - daily_report.py

**Files:**
- Modify: `daily_report.py`

- [ ] **Step 1: 读取现有 daily_report.py**

读取文件，了解现有结构。

- [ ] **Step 2: 修改 daily_report.py，添加导入和新函数**

在文件顶部添加：

```python
# 新增导入
from feishu import FeishuAuthenticator, FeishuCollector, ChatFilter, FeishuDocExporter
from feishu.auth import RefreshTokenExpiredError
from inheritance import TaskInheritanceManager
```

在 `load_config` 函数后添加：

```python
def validate_feishu_config(config: dict) -> bool:
    """验证飞书配置是否完整"""
    feishu_config = config.get("feishu", {})
    if not feishu_config.get("enabled", False):
        return True
    required_keys = ["app_id", "app_secret"]
    for key in required_keys:
        if not feishu_config.get(key):
            print(f"Warning: feishu.{key} 未配置，飞书集成将不可用")
            return False
    return True


def collect_all_sources(date: datetime, config: dict, force: bool = False) -> str:
    """收集所有数据源"""
    parts = []

    # 1. Claude 会话（现有）
    claude_collector = ClaudeCollector(
        config["claude"]["history_path"],
        config["claude"]["projects_path"],
    )
    claude_content = claude_collector.collect_for_date(date)
    if claude_content:
        parts.append("=== Claude 会话记录 ===\n" + claude_content)

    # 2. 飞书集成（新增）
    if config.get("feishu", {}).get("enabled", False) and validate_feishu_config(config):
        feishu_content = collect_feishu_sources(date, config, force)
        if feishu_content:
            parts.append(feishu_content)

    # 3. 继承任务（新增）
    inheritance_mgr = TaskInheritanceManager(config["report"]["base_dir"])
    yesterday = date - timedelta(days=1)
    inherited_tasks = inheritance_mgr.get_incomplete_tasks_from_daily(yesterday)
    if inherited_tasks:
        tasks_text = inheritance_mgr._format_tasks_for_prompt(inherited_tasks)
        parts.append(tasks_text)

    return "\n\n".join(parts)


def collect_feishu_sources(date: datetime, config: dict, force: bool = False) -> str:
    """收集飞书数据源"""
    parts = []
    feishu_config = config.get("feishu", {})

    # 认证
    auth = FeishuAuthenticator(
        feishu_config["app_id"],
        feishu_config["app_secret"],
        feishu_config.get("env_dir", "~/.feishu_env"),
        feishu_config.get("redirect_uri", "http://localhost:8080/callback")
    )
    try:
        access_token = auth.get_access_token()
    except RefreshTokenExpiredError:
        print("飞书 refresh_token 已过期，请重新运行 'python -m feishu auth' 授权")
        return ""
    except Exception as e:
        print(f"飞书认证失败: {e}")
        return ""

    # 采集聊天记录
    collector = FeishuCollector(access_token, feishu_config.get("chat_cache_dir", "reports/feishu_chat_cache"))
    chat_cache_path = collector.collect_chat_for_date(date, force=force)

    # LLM 过滤闲聊
    chat_filter = ChatFilter(
        config["llm"]["arkplan_settings"],
        feishu_config.get("llm_token_limit", 15000)
    )
    filtered_chat = chat_filter.filter_chat(chat_cache_path)
    if filtered_chat and filtered_chat != "无工作相关内容":
        parts.append("=== 飞书聊天（已过滤）===\n" + filtered_chat)

    # 导出文档
    doc_links = collector.extract_doc_links_from_chat(chat_cache_path)
    recent_docs = collector.get_recent_docs(days=feishu_config.get("recent_docs_days", 7))
    all_doc_urls = doc_links + [d.doc_url for d in recent_docs]

    # 去重策略：基于 URL 字符串完全匹配去重
    unique_doc_urls = list(dict.fromkeys(all_doc_urls))

    if unique_doc_urls:
        exporter = FeishuDocExporter(
            feishu_config.get("temp_dir", "/tmp/feishu_docs"),
            config["llm"]["arkplan_settings"],
            feishu_config.get("doc_summary_threshold", 3500)
        )
        try:
            doc_contents = exporter.export_docs(unique_doc_urls)
        finally:
            exporter.cleanup()

        if doc_contents:
            parts.append("=== 飞书文档 ===\n")
            for url, content in doc_contents.items():
                parts.append(f"--- {url} ---\n{content}")

    return "\n\n".join(parts)
```

- [ ] **Step 3: 修改 main() 函数，使用新的 collect_all_sources**

找到生成日报的部分，修改：

```python
# 原代码：
# conversation_text = collector.collect_for_date(date)

# 新代码：
conversation_text = collect_all_sources(date, config, args.force)
```

- [ ] **Step 4: Commit**

```bash
git add daily_report.py
git commit -m "feat: integrate feishu sources into main flow"
```

---

### Task 8: 更新 generator.py 提示词

**Files:**
- Modify: `generator.py`

- [ ] **Step 1: 读取现有 generator.py**

读取文件，找到 `_build_daily_prompt`、`_build_weekly_prompt`、`_build_monthly_prompt` 方法。

- [ ] **Step 2: 修改 _build_daily_prompt 方法**

在提示词开头添加：

```python
DAILY_PROMPT_PREFIX = """【重要：继承任务说明】
如果输入中包含「昨日未完成任务」部分，请：
1. 将这些任务作为今天日报的「四、下一步计划」的基础
2. 对于今天会话中提到已经完成的继承任务，移到「二、关键进展」中，并标记为已完成
3. 对于今天会话中提到有新进展但未完成的继承任务，保留在「下一步计划」中，但更新任务描述
4. 对于没有提到的继承任务，继续保留在「下一步计划」中

【重要：飞书聊天说明】
输入中可能包含「飞书聊天（已过滤）」部分，这是从飞书聊天中提取的工作相关内容。请：
1. 将其与 Claude 会话记录合并分析
2. 同样区分「自主工作」和「下属支持」
3. 从中提取关键进展、遇到的困难等

【重要：飞书文档说明】
输入中可能包含「飞书文档」部分，这是从飞书文档中导出的内容（可能包含 [摘要] 标记）。请：
1. 参考文档内容理解工作背景
2. 如果文档是今天创建或编辑的，可以在关键进展中提及
3. 不要直接大段复制文档内容，而是总结与今日工作相关的部分

---

"""
```

然后修改 `_build_daily_prompt` 方法，将此前缀添加到原有提示词之前。

- [ ] **Step 3: 修改 _build_weekly_prompt 方法**

在提示词开头添加周报版本的前缀（"昨日未完成任务" 改为 "上周未完成任务"）：

```python
WEEKLY_PROMPT_PREFIX = """【重要：继承任务说明】
如果输入中包含「上周未完成任务」部分，请：
1. 将这些任务作为本周报的「四、下一步计划」的基础
2. 对于本周会话中提到已经完成的继承任务，移到「二、关键进展」中，并标记为已完成
3. 对于本周会话中提到有新进展但未完成的继承任务，保留在「下一步计划」中，但更新任务描述
4. 对于没有提到的继承任务，继续保留在「下一步计划」中

【重要：飞书聊天说明】
输入中可能包含「飞书聊天（已过滤）」部分，这是从飞书聊天中提取的工作相关内容。请：
1. 将其与 Claude 会话记录合并分析
2. 同样区分「自主工作」和「下属支持」
3. 从中提取关键进展、遇到的困难等

【重要：飞书文档说明】
输入中可能包含「飞书文档」部分，这是从飞书文档中导出的内容（可能包含 [摘要] 标记）。请：
1. 参考文档内容理解工作背景
2. 如果文档是本周创建或编辑的，可以在关键进展中提及
3. 不要直接大段复制文档内容，而是总结与本周工作相关的部分

---

"""
```

- [ ] **Step 4: 修改 _build_monthly_prompt 方法**

在提示词开头添加月报版本的前缀（"昨日未完成任务" 改为 "上月未完成任务"）：

```python
MONTHLY_PROMPT_PREFIX = """【重要：继承任务说明】
如果输入中包含「上月未完成任务」部分，请：
1. 将这些任务作为本月报的「四、下一步计划」的基础
2. 对于本月会话中提到已经完成的继承任务，移到「二、关键进展」中，并标记为已完成
3. 对于本月会话中提到有新进展但未完成的继承任务，保留在「下一步计划」中，但更新任务描述
4. 对于没有提到的继承任务，继续保留在「下一步计划」中

【重要：飞书聊天说明】
输入中可能包含「飞书聊天（已过滤）」部分，这是从飞书聊天中提取的工作相关内容。请：
1. 将其与 Claude 会话记录合并分析
2. 同样区分「自主工作」和「下属支持」
3. 从中提取关键进展、遇到的困难等

【重要：飞书文档说明】
输入中可能包含「飞书文档」部分，这是从飞书文档中导出的内容（可能包含 [摘要] 标记）。请：
1. 参考文档内容理解工作背景
2. 如果文档是本月创建或编辑的，可以在关键进展中提及
3. 不要直接大段复制文档内容，而是总结与本月工作相关的部分

---

"""
```

- [ ] **Step 5: Commit**

```bash
git add generator.py
git commit -m "feat: update generator prompts for feishu integration"
```

---

### Task 9: 最终测试和文档

**Files:**
- N/A

- [ ] **Step 1: 运行现有代码验证**

```bash
python daily_report.py --help
```

Expected: 显示帮助信息，没有错误

- [ ] **Step 2: 验证模块导入**

```bash
python -c "from feishu import FeishuAuthenticator; from inheritance import TaskInheritanceManager; print('OK')"
```

Expected: 输出 "OK"

- [ ] **Step 3: Commit（如果有修改）**

如有需要，commit 最后的修改。

---

## 计划完成

Plan complete and saved to `docs/superpowers/plans/2026-03-24-feishu-integration-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

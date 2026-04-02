# 飞书日程集成实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有日报系统中添加飞书日程采集功能，采集前7天+当天+后7天的日程，整合到日报上下文中。

**Architecture:** 在 `feishu/collector.py` 中添加日程采集方法，在 `daily_report.py` 中调用，保持现有架构不变。

**Tech Stack:** Python, requests, 飞书 OpenAPI

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `feishu/collector.py` | 修改 | 添加 `collect_calendar_for_date()` 等方法 |
| `daily_report.py` | 修改 | 在 `collect_feishu_sources()` 中调用日程采集 |

---

## 任务列表

### Task 1: 在 FeishuCollector 中添加日程 API 调用方法

**Files:**
- Modify: `feishu/collector.py`

- [ ] **Step 1: 添加 `_get_calendar_events()` 方法**

在 `FeishuCollector` 类中 `_api_request()` 方法之前添加：

```python
    def _get_calendar_events(self, calendar_id: str, start_ts: int, end_ts: int) -> List[dict]:
        """获取日历事件列表"""
        url = f"https://open.feishu.cn/open-apis/calendar/v4/calendars/{calendar_id}/events"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        events = []
        page_token = ""

        while True:
            params = {
                "page_size": 100,
                "time_zone": "Asia/Shanghai",
            }
            if page_token:
                params["page_token"] = page_token

            try:
                resp = self._api_request("GET", url, headers=headers, params=params)
            except RateLimitError:
                time.sleep(2)
                continue
            except Exception as e:
                raise Exception(f"Failed to get calendar events: {e}") from e

            data = resp.get("data", {})
            items = data.get("items", [])

            # 过滤时间范围内的事件
            for item in items:
                event_start = self._parse_event_time(item.get("start_time"))
                event_end = self._parse_event_time(item.get("end_time"))
                if event_start and event_end:
                    if event_end.timestamp() * 1000 >= start_ts and event_start.timestamp() * 1000 <= end_ts:
                        events.append(item)

            page_token = data.get("page_token", "")
            if not data.get("has_more", False) or not page_token:
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
```

- [ ] **Step 2: 添加辅助方法 `_group_events_by_date()`**

在 `_parse_event_time()` 之后添加：

```python
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
```

- [ ] **Step 3: 添加 `_format_calendar_events()` 方法**

在 `_group_events_by_date()` 之后添加：

```python
    def _format_calendar_events(self, events_by_date: Dict[str, List[dict]], target_date: datetime) -> str:
        """格式化日程事件为 LLM 输入文本"""
        lines = []

        # 历史事件
        if events_by_date["past"]:
            lines.append("--- 历史（前7天）---")
            lines.append("")
            for event in sorted(events_by_date["past"], key=lambda e: self._parse_event_time(e.get("start_time")) or datetime.max):
                lines.extend(self._format_single_event(event, show_date=True))
                lines.append("")

        # 今天的事件
        if events_by_date["today"]:
            lines.append(f"--- 今天（{target_date.strftime('%Y-%m-%d')}）---")
            lines.append("")
            for event in sorted(events_by_date["today"], key=lambda e: self._parse_event_time(e.get("start_time")) or datetime.max):
                lines.extend(self._format_single_event(event, show_date=False))
                lines.append("")

        # 未来事件
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

        # 组织者
        organizer = event.get("organizer", {})
        organizer_name = organizer.get("display_name", "") or organizer.get("email", "")
        if organizer_name:
            lines.append(f"- 组织者: {organizer_name}")

        # 参与者
        attendees = event.get("attendees", [])
        if attendees:
            attendee_names = []
            for a in attendees:
                name = a.get("display_name", "") or a.get("email", "")
                if name:
                    attendee_names.append(name)
            if attendee_names:
                lines.append(f"- 参与者: {', '.join(attendee_names)}")

        # 地点
        location = event.get("location")
        if location:
            lines.append(f"- 地点: {location}")

        # 描述
        description = event.get("description")
        if description:
            lines.append(f"- 描述: {description}")

        # 如果没有标题，添加备注
        if not event.get("summary", "").strip():
            lines.append("- 备注: 对应时间可能有智能纪要文档")

        return lines
```

- [ ] **Step 4: 添加主入口方法 `collect_calendar_for_date()`**

在 `extract_doc_links_from_chat()` 方法之后添加：

```python
    def collect_calendar_for_date(self, date: datetime, calendar_id: str = "") -> str:
        """
        采集指定日期的日程（前7天 + 当天 + 后7天）
        返回格式化的文本
        """
        if not calendar_id:
            # 默认使用主日历
            calendar_id = "feishu.cn_PRnEkMf3VmhBRb9pSdlWsh@group.calendar.feishu.cn"

        # 计算时间范围
        target_date_start = datetime(date.year, date.month, date.day)
        start_ts = int((target_date_start - timedelta(days=7)).timestamp() * 1000)
        end_ts = int((target_date_start + timedelta(days=8)).timestamp() * 1000) - 1

        try:
            # 获取事件
            events = self._get_calendar_events(calendar_id, start_ts, end_ts)
            if not events:
                return ""

            # 按日期分组
            events_by_date = self._group_events_by_date(events, date)

            # 格式化
            return self._format_calendar_events(events_by_date, date)

        except Exception as e:
            print(f"Warning: Failed to collect calendar events: {e}")
            return ""
```

- [ ] **Step 5: 验证导入**

确认文件顶部已有的导入：
- `from datetime import datetime, timedelta` - 应该已存在
- `from typing import List, Optional, Dict` - 可能需要添加 Dict

在 `from typing import List, Optional` 后添加 `, Dict`：

```python
from typing import List, Optional, Dict
```

---

### Task 2: 修改 daily_report.py 调用日程采集

**Files:**
- Modify: `daily_report.py`

- [ ] **Step 1: 在 `collect_feishu_sources()` 中添加日程采集**

在 `collect_feishu_sources()` 函数中，聊天采集之后、文档采集之前添加：

```python
    # 3. 采集日程
    try:
        calendar_content = collector.collect_calendar_for_date(date)
        if calendar_content:
            parts.append("=== 飞书日程 ===\n" + calendar_content)
    except Exception as e:
        print(f"Warning: Failed to collect calendar: {e}")
```

完整的插入位置（在 line 119-120 之间）：

```python
    if filtered_chat and filtered_chat != "无工作相关内容":
        parts.append("=== 飞书聊天（已过滤）===\n" + filtered_chat)

    # 3. 采集日程
    try:
        calendar_content = collector.collect_calendar_for_date(date)
        if calendar_content:
            parts.append("=== 飞书日程 ===\n" + calendar_content)
    except Exception as e:
        print(f"Warning: Failed to collect calendar: {e}")

    # 导出文档
    doc_links = collector.extract_doc_links_from_chat(chat_cache_path)
```

---

### Task 3: 测试验证

**Files:**
- Test: 运行日报生成脚本

- [ ] **Step 1: 检查语法错误**

```bash
cd /Users/liangjiayu/projects/daily_report
python -m py_compile feishu/collector.py
python -m py_compile daily_report.py
```

Expected: 无输出（表示无语法错误）

- [ ] **Step 2: 运行昨天的日报生成（实际测试）**

```bash
python daily_report.py --yesterday --force --verbose
```

Expected: 看到 "=== 飞书日程 ===" 部分输出，日报成功生成

- [ ] **Step 3: 提交代码**

```bash
git add feishu/collector.py daily_report.py
git commit -m "feat: add feishu calendar integration

- Add calendar event collection (7 days past + today + 7 days future)
- Format calendar events for LLM context
- Handle untitled meetings with note about smart minutes

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## 总结

完成以上任务后，系统将能够：
1. 从飞书日历采集前7天+当天+后7天的日程
2. 按历史/今天/未来分组展示
3. 正确处理无标题会议并添加智能纪要备注
4. 将日程信息整合到日报生成上下文中

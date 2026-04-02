---
name: Feishu Calendar Integration Design
description: Add Feishu calendar events collection to daily report system
type: spec
---

# 飞书日程集成设计文档

## 概述
在现有日报系统中添加飞书日程（日历事件）采集功能，作为日报上下文数据源。

## 目标
- 从飞书日历 API 采集指定日期的日程事件
- 将日程信息整合到日报生成的上下文中
- 保持现有架构不变，最小化改动

## 背景
- 主日历 ID: `feishu.cn_PRnEkMf3VmhBRb9pSdlWsh@group.calendar.feishu.cn`
- 日程 API: `GET /calendar/v4/calendars/{calendar_id}/events`
- 本阶段只做日程采集，暂不涉及会议历史和会议总结文档匹配

## 设计详情

### 1. 数据结构
在 `feishu/collector.py` 中添加日程相关数据结构（可选，直接用 dict）：

```python
@dataclass
class CalendarEvent:
    event_id: str
    title: str
    start_time: datetime
    end_time: datetime
    organizer: str
    attendees: List[str]
    location: Optional[str] = None
    description: Optional[str] = None
    status: str = "confirmed"  # confirmed, tentative, cancelled
```

### 2. FeishuCollector 新增方法

| 方法 | 功能 |
|------|------|
| `collect_calendar_for_date(date: datetime) -> str` | 采集日程（前7天 + 当天 + 后7天），返回格式化文本 |
| `_get_calendar_events(calendar_id: str, start_ts: int, end_ts: int) -> List[dict]` | 调用飞书日历 API 获取原始事件 |
| `_group_events_by_date(events: List[dict]) -> Dict[str, List[dict]]` | 按日期分组事件 |
| `_format_calendar_events(events_by_date: Dict[str, List[dict]]) -> str` | 格式化为 LLM 输入文本 |

### 3. API 调用详情

**端点**: `https://open.feishu.cn/open-apis/calendar/v4/calendars/{calendar_id}/events`

**参数**:
- `page_size`: 100
- `anchor_time`: 当天开始时间戳（秒）
- `time_zone`: "Asia/Shanghai"

**时间范围**:
- 开始: 目标日期前 7 天 00:00:00
- 结束: 目标日期后 7 天 23:59:59
- 目的: 前7天指导总结，后7天指导计划

### 4. 数据流变更

在 `daily_report.py` 的 `collect_feishu_sources()` 中新增：

```python
# 3. 采集日程
calendar_content = collector.collect_calendar_for_date(date)
if calendar_content:
    parts.append("=== 飞书日程 ===\n" + calendar_content)
```

插入位置：在聊天采集之后，文档采集之前。

### 5. 日程格式化输出示例

```
=== 飞书日程 ===

--- 历史（前7天）---

## 2026-03-20 10:00 - 11:00 - 产品周会
- 组织者: 张三
- 参与者: 张三, 李四, 王五
- 地点: 会议室 A
- 描述: 讨论本周产品进度

--- 今天（2026-03-25）---

## 10:00 - 11:00 - （无标题）
- 组织者: 张三
- 参与者: 技术团队
- 备注: 对应时间可能有智能纪要文档

## 14:00 - 15:30 - 技术评审
- 组织者: 李四
- 参与者: 技术团队
- 描述: 新架构方案评审

--- 未来（后7天）---

## 2026-03-28 10:00 - 11:00 - 月度规划会
- 组织者: 王五
- 参与者: 全体成员
```

## 配置变更

无需新增配置项，复用现有飞书配置。

## 风险与注意事项

1. **日历权限：确保 token 有日历读权限
2. **API 限流：复用现有 `_api_request` 的限流处理**
3. **空数据：当天无日程时返回空字符串
4. **时区：统一使用 Asia/Shanghai

## 后续优化（第二阶段）

- 飞书会议历史记录采集
- 智能纪要文档匹配（通过标题关键词"智能纪要" + 时间匹配）
- 会议与纪要关联

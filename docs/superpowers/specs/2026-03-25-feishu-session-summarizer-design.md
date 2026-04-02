# 飞书会话总结功能设计

**日期**: 2026-03-25
**目标**: 基于飞书消息生成智能会话总结，整合到日报

---

## 1. 概述

### 1.1 背景
现有日报工具已集成飞书聊天记录和日程采集。需要增强功能：
- 获取更多消息（最近2天，最多10000条）
- 完善用户信息显示（使用 contact/v3/user/basic_batch API）
- 按主题聚合会话并生成总结
- 整合到日报生成流程

### 1.2 目标
- 独立的会话总结工具（参数控制时间和条数）
- 日报集成（自动获取最近2天消息并总结）
- 完善的用户缓存机制
- 按主题聚合的智能总结

---

## 2. 架构设计

### 2.1 组件架构
```
daily_report/
├── feishu/
│   ├── collector.py       [增强] 用户缓存 + 批量获取用户 + 批量搜索消息
│   ├── summarizer.py      [新增] FeishuSummarizer 类
│   └── __main__.py        [增强] summarize 命令
└── daily_report.py         [增强] 集成会话总结
```

### 2.2 数据流程
```
1. 获取消息
   └─ FeishuCollector.search_messages_all(days=2, max=10000)
      └─ 分页调用 search/v2/message

2. 完善用户信息
   └─ FeishuCollector._ensure_users_basic(user_ids)
      └─ 调用 contact/v3/users/basic_batch
      └─ 更新 _user_cache（带时间戳）

3. 按会话分组
   └─ FeishuSummarizer.fetch_sessions()
      └─ 返回 List[ChatSession]

4. 按主题聚合 + LLM 总结
   └─ FeishuSummarizer.group_by_topic()
      └─ 返回 List[TopicSummary]

5. 格式化为日报
   └─ FeishuSummarizer.format_for_daily_report()
      ├─ 独立章节文本
      └─ 提取字典（key_progress/action_items 等）
```

---

## 3. 详细设计

### 3.1 增强 FeishuCollector (feishu/collector.py)

#### 3.1.1 用户缓存机制增强

**现有结构修改：**
```python
# 修改前
self._user_cache: Dict[str, str] = {}

# 修改后
@dataclass
class UserInfo:
    name: str
    updated_at: float  # timestamp

self._user_cache: Dict[str, UserInfo] = {}
self._user_cache_path: Optional[Path] = None  # 可选持久化
```

**新增方法：**

| 方法 | 功能 |
|------|------|
| `_ensure_users_basic(user_ids: List[str])` | 批量获取用户基本信息 |
| `_load_user_cache()` | 从磁盘加载缓存（可选） |
| `_save_user_cache()` | 保存缓存到磁盘（可选） |

#### 3.1.2 contact/v3/user/basic_batch API

**API 端点：**
```
POST https://open.feishu.cn/open-apis/contact/v3/users/basic_batch
```

**请求体：**
```json
{
  "user_ids": ["ou_xxx", "ou_yyy"],
  "user_id_type": "open_id"
}
```

**响应处理：**
```python
for user_item in data.get("data", {}).get("items", []):
    user = user_item.get("user", {})
    open_id = user.get("open_id", "")
    name = user.get("name", "")
    if open_id and name:
        self._user_cache[open_id] = UserInfo(
            name=name,
            updated_at=time.time()
        )
```

#### 3.1.3 批量获取消息

**新增方法签名：**
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
```

**实现逻辑：**
1. 计算时间范围（最近 `days` 天）
2. 循环调用 `search_messages()` 带 `page_token`
3. 累加消息直到达到 `max_messages` 或 `has_more=False`

---

### 3.2 新增 FeishuSummarizer (feishu/summarizer.py)

#### 3.2.1 数据类

```python
from dataclasses import dataclass
from typing import List, Optional, Dict

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
```

#### 3.2.2 FeishuSummarizer 类

```python
class FeishuSummarizer:
    def __init__(self, collector: FeishuCollector, llm_config: Dict):
        self.collector = collector
        self.llm_config = llm_config

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
        # 1. 调用 collector.search_messages_all()
        # 2. 按 chat_id 分组
        # 3. 构建 ChatSession 对象
        # 4. 对于私聊，设置 p2p_partner

    def group_by_topic(self, sessions: List[ChatSession]) -> List[TopicSummary]:
        """
        按主题聚合并调用 LLM 生成总结

        Returns:
            TopicSummary 列表
        """
        # 1. 提取所有消息内容，构建提示词
        # 2. 调用 LLM 进行主题聚类和总结
        # 3. 解析返回结果，构建 TopicSummary 对象

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
        # 1. 生成独立章节：完整的主题总结
        # 2. 提取关键信息到字典
```

---

### 3.3 命令行增强 (feishu/__main__.py)

#### 3.3.1 新增 summarize 命令

**参数：**
- `--days N`: 获取最近 N 天（默认 2）
- `--limit N`: 最多 N 条消息（默认 10000）
- `--output FILE`: 输出到文件（可选）

**实现：**
```python
def summarize_sessions(config, days=2, limit=10000, output=None):
    """独立会话总结命令"""
    # 1. 初始化 collector 和 summarizer
    # 2. 获取会话并总结
    # 3. 格式化输出
    # 4. 输出到终端或文件
```

---

### 3.4 日报集成 (daily_report.py)

#### 3.4.1 修改 collect_feishu_sources()

```python
def collect_feishu_sources(date: datetime, config: dict, force: bool = False) -> str:
    # ... 现有代码 ...

    # 新增：获取并总结最近 2 天的会话
    from feishu.summarizer import FeishuSummarizer
    summarizer = FeishuSummarizer(collector, config.get("llm", {}))
    sessions = summarizer.fetch_sessions(days=2, max_messages=10000)
    topics = summarizer.group_by_topic(sessions)
    summary_section, extracted = summarizer.format_for_daily_report(topics)

    parts.append("=== 飞书会话总结 ===\n" + summary_section)

    # 将 extracted 保存到临时变量，供后续生成器使用
    # ...

    return "\n\n".join(parts)
```

#### 3.4.2 修改 generator.py 支持提取信息整合

在生成日报时，使用 `extracted` 字典：
- `extracted["key_progress"]` → 添加到"二、关键进展"
- `extracted["action_items"]` → 添加到"四、下一步计划"
- `extracted["problems"]` → 添加到"三、遇到的困难"

---

## 4. API 参考

### 4.1 search/v2/message
- **路径**: `POST https://open.feishu.cn/open-apis/search/v2/message`
- **用途**: 搜索消息
- **文档**: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/search-v2/message/create

### 4.2 contact/v3/user/basic_batch
- **路径**: `POST https://open.feishu.cn/open-apis/contact/v3/users/basic_batch`
- **用途**: 批量获取用户基本信息
- **文档**: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/user/basic_batch

---

## 5. 使用方式

### 5.1 独立使用
```bash
# 总结最近 2 天，最多 10000 条消息
python -m feishu summarize

# 自定义参数
python -m feishu summarize --days 7 --limit 5000 --output summary.md
```

### 5.2 日报集成
```bash
# 生成日报时自动包含飞书会话总结
python daily_report.py --date 2026-03-25
```

---

## 6. 风险和注意事项

1. **API 限流**: 批量获取用户和消息时注意限流，添加重试逻辑
2. **用户隐私**: 缓存用户信息时注意安全，可选持久化加密
3. **LLM 成本**: 主题聚合可能消耗较多 token，考虑设置消息长度限制
4. **分页处理**: search/v2/message 分页要正确处理 page_token

---

## 7. 后续优化方向

1. 用户缓存持久化（可选加密）
2. 支持按人聚合视图
3. 会话摘要的多语言支持
4. 消息去重和智能筛选
5. 支持导出多种格式（JSON/HTML/PDF）

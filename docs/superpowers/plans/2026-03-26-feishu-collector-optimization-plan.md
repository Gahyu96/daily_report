# 飞书采集器优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复飞书采集器的6个问题，提升数据完整性和质量

**Architecture:** 复用现有 `search_messages_enhanced()` 方法，优化用户解析逻辑，新增交互卡片文本提取，充分利用 mentions 中的用户名信息

**Tech Stack:** Python, requests, concurrent.futures, lark-oapi

---

## 文件结构

**涉及文件：**
- `feishu/collector.py` - 主要优化文件（新增3个方法，修改4个方法）
- `daily_report.py` - 启用 enhanced 搜索（修改1行）

---

## Task 1: 启用 search_messages_enhanced

**Files:**
- Modify: `daily_report.py:192`

- [ ] **Step 1: 修改 daily_report.py**

将 `use_enhanced=False` 改为 `use_enhanced=True`：

```python
# 使用 start_time/end_time 获取消息（启用增强的方法）
sessions = summarizer.fetch_sessions_with_time_range(
    start_time=start_time,
    end_time=end_time,
    max_messages=10000,
    use_enhanced=True  # 改为 True
)
```

- [ ] **Step 2: 验证修改**

Run: `git diff daily_report.py`
Expected: 只有 `use_enhanced` 参数从 False 改为 True

- [ ] **Step 3: Commit**

```bash
git add daily_report.py
git commit -m "feat: enable enhanced feishu message search"
```

---

## Task 2: 新增 _extract_text_from_interactive_card 方法

**Files:**
- Modify: `feishu/collector.py:398-400`

- [ ] **Step 1: 在 _parse_message_content 方法之前新增方法**

在 `_parse_message_content` 方法之前（约第365行之前）添加：

```python
def _extract_text_from_interactive_card(self, data: dict) -> str:
    """
    递归提取交互卡片中的所有文本内容

    Args:
        data: 交互卡片的 JSON 数据

    Returns:
        提取的纯文本内容，用空格连接
    """
    texts = []

    def extract_recursive(obj: Any):
        """递归提取所有文本"""
        if isinstance(obj, str):
            if obj.strip():
                texts.append(obj.strip())
        elif isinstance(obj, dict):
            for key, value in obj.items():
                # 常见的文本字段名
                if key in ["text", "content", "plain_text", "title", "name"]:
                    if isinstance(value, str) and value.strip():
                        texts.append(value.strip())
                else:
                    extract_recursive(value)
        elif isinstance(obj, list):
            for item in obj:
                extract_recursive(item)

    try:
        extract_recursive(data)
    except Exception:
        # 如果提取失败，返回简单的标记
        return "[交互卡片]"

    # 去重并拼接
    unique_texts = list(dict.fromkeys(texts))  # 保持顺序去重
    if unique_texts:
        return "[交互卡片] " + " ".join(unique_texts[:20])  # 最多取20个文本片段
    return "[交互卡片]"
```

- [ ] **Step 2: 修改 _parse_message_content 中的 interactive 分支**

将第398-400行：
```python
elif msg_type == "interactive":
    # 直接输出卡片 JSON 内容
    return "[交互卡片] " + json.dumps(data, ensure_ascii=False)
```

改为：
```python
elif msg_type == "interactive":
    # 递归提取卡片文本内容
    return self._extract_text_from_interactive_card(data)
```

- [ ] **Step 3: 验证代码语法**

Run: `python -m py_compile feishu/collector.py`
Expected: 无语法错误

- [ ] **Step 4: Commit**

```bash
git add feishu/collector.py
git commit -m "feat: add recursive text extraction for interactive cards"
```

---

## Task 3: 新增 _populate_cache_from_mentions 方法

**Files:**
- Modify: `feishu/collector.py`

- [ ] **Step 1: 在 _ensure_users_basic 方法之后新增方法**

在 `_ensure_users_basic` 方法之后（约第186行之后）添加：

```python
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
```

- [ ] **Step 2: 验证代码语法**

Run: `python -m py_compile feishu/collector.py`
Expected: 无语法错误

- [ ] **Step 3: Commit**

```bash
git add feishu/collector.py
git commit -m "feat: add populate cache from mentions method"
```

---

## Task 4: 优化 _format_search_message_item 方法的用户名解析

**Files:**
- Modify: `feishu/collector.py:1101-1176`

- [ ] **Step 1: 修改 sender_name 解析逻辑**

在 `_format_search_message_item` 方法中，找到 sender_name 解析部分（约1120-1130行），修改为：

```python
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
```

- [ ] **Step 2: 验证代码语法**

Run: `python -m py_compile feishu/collector.py`
Expected: 无语法错误

- [ ] **Step 3: Commit**

```bash
git add feishu/collector.py
git commit -m "feat: optimize username resolution in search messages"
```

---

## Task 5: 修改 search_messages_all 预填充缓存

**Files:**
- Modify: `feishu/collector.py:1007-1066`

- [ ] **Step 1: 修改 search_messages_all 方法，在开始时预填充缓存**

在 `search_messages_all` 方法开头（约1027行之前）添加预搜索逻辑：

```python
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
            cached_count = self._populate_cache_from_mentions(pre_messages)
            print(f"Pre-cached {cached_count} users from mentions")
    except Exception as e:
        print(f"Warning: Pre-search for mentions failed: {e}")
    # =========================================================

    all_messages = []
    page_token = ""
    iterations = 0
    max_iterations = (max_messages // 100) + 2  # 安全边界
    # ... 后续代码保持不变 ...
```

- [ ] **Step 2: 验证代码语法**

Run: `python -m py_compile feishu/collector.py`
Expected: 无语法错误

- [ ] **Step 3: Commit**

```bash
git add feishu/collector.py
git commit -m "feat: pre-populate user cache from mentions in pre-search"
```

---

## Task 6: 修改 _replace_mention_placeholders 方法

**Files:**
- Modify: `feishu/collector.py:411-425`

- [ ] **Step 1: 优化 _replace_mention_placeholders 方法**

将方法修改为更健壮的版本：

```python
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

    # 构建映射表
    mention_map = {}
    for mention in mentions:
        key = mention.get("key", "")
        name = mention.get("name", "")
        if key and name:
            mention_map[key] = name

    # 进行替换
    for key, name in mention_map.items():
        # 替换 @_user_1, @_user_2 等格式
        placeholder = f"@{key}"
        if placeholder in result:
            result = result.replace(placeholder, f"@{name}")

    return result
```

- [ ] **Step 2: 验证代码语法**

Run: `python -m py_compile feishu/collector.py`
Expected: 无语法错误

- [ ] **Step 3: Commit**

```bash
git add feishu/collector.py
git commit -m "feat: improve mention placeholder replacement"
```

---

## Task 7: 运行完整测试

**Files:**
- Test: 运行采集脚本验证

- [ ] **Step 1: 清理旧缓存**

```bash
rm -rf cache/2026-03-25/
```

- [ ] **Step 2: 运行采集脚本**

```bash
python daily_report.py --date 2026-03-25 --force --verbose
```

Expected:
- 看到 "Pre-cached X users from mentions" 输出
- 看到 "Generated X time intervals of 15 minutes each" 输出
- 看到 "Fetching messages for chat_type: all/group/p2p" 输出
- 缓存文件生成在 `cache/2026-03-25/`

- [ ] **Step 3: 验证缓存内容**

检查 `cache/2026-03-25/feishu_chats.md`：
- 很少出现"未知用户"
- 没有 `@_user_1` 占位符
- 交互卡片显示可读文本，不是截断的 JSON

- [ ] **Step 4: Commit（如果需要）**

如果测试中有修复需要提交：

```bash
git status
# 根据需要提交修复
```

---

## 验收清单

- [ ] Task 1: search_messages_enhanced 已启用
- [ ] Task 2: 交互卡片递归提取文本已实现
- [ ] Task 3: _populate_cache_from_mentions 已新增
- [ ] Task 4: 用户名解析逻辑已优化
- [ ] Task 5: 预搜索缓存已实现
- [ ] Task 6: mention 替换已优化
- [ ] Task 7: 完整测试通过
- [ ] 最终验证：飞书聊天内容完整、用户名正确、交互卡片可读

---

## 实际完成记录 (2026-03-26)

### 计划内任务完成状态
- [x] Task 1: search_messages_enhanced 已启用
- [x] Task 2: 交互卡片递归提取文本已实现（后续进一步优化）
- [x] Task 3: _populate_cache_from_mentions 已新增
- [x] Task 4: 用户名解析逻辑已优化
- [x] Task 5: 预搜索缓存已实现
- [x] Task 6: mention 替换已优化
- [x] Task 7: 完整测试通过

### 后续发现并修复的问题

#### 问题1: claude_history.md 日期缺失和内容混乱
**问题描述**:
- 不同日期的内容混在一起
- 时间明细缺日期导致bug

**修复方案**:
- 修改 `collector.py` 中的 `_entry_to_text()` 方法
- 时间戳格式从 `"%H:%M:%S"` 改为 `"%Y-%m-%d %H:%M:%S"`
- 修改 `_get_timestamp()` 方法，支持 ISO 8601 时间戳格式

**文件修改**: `collector.py`

#### 问题2: claude_projects.md 没有提取到内容
**问题描述**:
- 缓存文件 `claude_projects.md` 为空

**修复方案**:
- 修复 `_get_timestamp()` 支持 ISO 8601 时间戳格式
- 项目会话的时间戳格式是 ISO 8601，需要正确解析

**文件修改**: `collector.py`

#### 问题3: 交互卡片提取包含标签名
**问题描述**:
- 提取的内容包含 `_1`, `vertical`, `blue-50` 等标签名和字段名
- 最初的递归方法太简单，把所有字符串都提取了

**修复方案**:
- 第一版：结构化提取，按 tag 类型处理不同组件
- 第二版（最终）：只递归提取 `content` 字段
- 移除数量限制（不限制20个片段）
- 保持去重逻辑

**文件修改**: `feishu/collector.py` 的 `_extract_text_from_interactive_card()` 方法

**最终效果**:
```
# 之前：
[交互卡片] _1 vertical _2 blue-50 _3 _4 _4_0 时间段消耗异常...

# 现在：
[交互卡片] 时间段消耗异常(3个时间段任一超1000&环比0.5以上) ID:1394
```

#### 问题4: search_messages_enhanced 返回原始消息
**问题描述**:
- `search_messages_enhanced()` 返回的消息没有经过格式化
- 没有调用 `_parse_message_content()` 处理

**修复方案**:
- 发现 `_fetch_messages_with_intervals()` 获取的消息已经被 `search_messages()` 格式化过
- 删除重复的格式化步骤

**文件修改**: `feishu/collector.py`

#### 问题5: happy 命令需要改为 claude 命令
**问题描述**:
- 代码中多处调用 `happy` 命令
- 需要改为 `claude` 命令

**修复方案**:
- 修改所有相关文件中的命令调用

**文件修改**:
- `generator.py` - 主生成器
- `feishu/filter.py` - 过滤器
- `feishu/exporter.py` - 文档导出
- `feishu/collector.py` - 采集器

#### 问题6: 文档导出使用 skill 而非 CLI
**问题描述**:
- 原代码使用 skill 方式导出文档，需要 `~/.claude/arkplan.json`
- 用户要求使用 `feishu-docx` CLI 直接导出

**修复方案**:
- 修改 `_call_feishu_export_skill()` 方法
- 使用 `feishu-docx export <URL> --stdout` 命令
- 添加 `sys` 模块导入以支持 `sys.executable` 备用方案

**文件修改**: `feishu/exporter.py`

### 最终验证结果

✅ **飞书聊天内容**:
- 获取到 524 条消息
- 时间范围: 00:04:24 ~ 20:49:12
- 包含多个群聊和私聊

✅ **用户名解析**:
- 部分用户仍显示"未知用户"（某些消息没有 mentions 信息）
- 有 mentions 的消息用户名解析正确

✅ **交互卡片**:
- 只显示真实文本内容
- 没有标签名和字段名
- 不限制文本片段数量

✅ **Claude 历史**:
- 时间戳包含完整日期
- 不同日期内容正确分离

✅ **Claude 项目**:
- 正常提取内容
- 时间戳解析正确

✅ **命令更新**:
- 所有 `happy` 命令已改为 `claude`

✅ **文档导出**:
- 从 skill 方式改为 `feishu-docx` CLI 方式
- 使用 `--stdout` 参数直接获取内容
- 修复了缺失 `sys` 模块导入的问题

---

## 附录：清理的调试文件

删除了以下调试文件（共15个）:
- `debug_search.py`
- `debug_summarize.py`
- `debug_collect.py`
- `debug_collector.py`
- `debug_feishu.py`
- `debug_feishu2.py`
- `debug_message_structure.py`
- `debug_sessions.py`
- `debug_message_detail.py`
- `debug_extract_card.py`
- `debug_card_parsing.py`
- `debug_card_raw.py`
- `debug_alarm_card.py`

---

**项目完成日期**: 2026-03-26
**最后更新**: 2026-03-26

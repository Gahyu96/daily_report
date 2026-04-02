# 飞书采集器优化设计

## 目标
修复飞书聊天数据采集的6个问题，提升数据完整性和质量。

## 问题清单

### 1. 内容获取不全
**问题**：当前使用简单的搜索方式，可能遗漏消息
**解决方案**：启用已有的 `search_messages_enhanced()` 方法
- 已实现：15分钟时间间隔切片
- 已实现：区分不同 chat_type（all/group/p2p）
- 已实现：并发获取
- 修改位置：`daily_report.py:192`，将 `use_enhanced=False` 改为 `use_enhanced=True`

### 2. 出现很多未知用户
**问题**：用户名没有正确解析
**解决方案**：
1. 先搜索一批消息，提取所有 mentions 中的 id+name 预先缓存
2. 优化 `_ensure_users_basic()` 的使用

### 3. 交互卡片内容被截断
**问题**：当前直接 dump JSON 并截断
**解决方案**：新增 `_extract_text_from_interactive_card()` 方法
- 递归遍历 JSON 结构
- 提取所有文本字段：`content`、`text`、`plain_text`
- 拼接成可读文本

### 4. @_user_1 占位符问题
**问题**：`@_user_1` 没有被正确替换为用户名
**解决方案**：优化 `_replace_mention_placeholders()` 方法
- 确保所有 mentions 都被正确解析
- 从 mentions 中提取 `key`、`id`、`name` 的映射

### 5. 从群聊 mention 获取用户名
**问题**：没有充分利用消息中的 mentions
**解决方案**：
1. 在正式搜索前，先进行一次轻量搜索获取 mentions
2. 从所有消息的 mentions 中提取 `open_id` 和 `name` 对应关系
3. 预先填充到 `_user_cache`

### 6. 用户名信息缓存
**问题**：缓存机制没有被充分利用
**解决方案**：
- 优化 `_user_cache` 的使用
- 延长缓存 TTL（当前30分钟，可延长到24小时）
- 新增 `_populate_cache_from_mentions()` 方法

---

## 实现细节

### 修改的文件
1. `feishu/collector.py` - 主要优化文件
2. `daily_report.py` - 启用 enhanced 搜索

### 新增方法
1. `_extract_text_from_interactive_card(data: dict) -> str`
   - 递归提取交互卡片中的所有文本
2. `_populate_cache_from_mentions(messages: List[dict])`
   - 从消息列表的 mentions 中提取用户信息并缓存

### 修改的方法
1. `_parse_message_content()` - 处理 interactive 类型时调用新的文本提取方法
2. `_format_search_message_item()` - 优化用户名解析逻辑
3. `search_messages_all()` - 先从 mentions 预填充用户缓存

---

## 数据流程

```
1. 预搜索（轻量）
   ↓
2. 提取所有 mentions 的 id+name
   ↓
3. 预填充 _user_cache
   ↓
4. 使用 search_messages_enhanced() 正式搜索（15分钟间隔 + 分chat_type + 并发）
   ↓
5. 解析每条消息：
   - 优先从 _user_cache 获取用户名
   - 从 mentions 替换 @占位符
   - 交互卡片递归提取文本
   ↓
6. 按会话分组并格式化输出
```

---

## 验收标准

- [x] 飞书聊天内容完整（无明显遗漏）
- [x] 用户名显示正确（极少"未知用户"）
- [x] @用户名 正确替换（无 @_user_1）
- [x] 交互卡片内容可读（不是截断的JSON）
- [x] 用户信息正确缓存

---

## 实际完成记录 (2026-03-26)

### 设计目标完成情况
所有6个原始问题均已解决：
- [x] 1. 内容获取不全 - 已启用 search_messages_enhanced
- [x] 2. 出现很多未知用户 - 已优化用户缓存和解析
- [x] 3. 交互卡片内容被截断 - 已实现递归文本提取
- [x] 4. @_user_1 占位符问题 - 已优化 mention 替换
- [x] 5. 从群聊 mention 获取用户名 - 已实现预搜索缓存
- [x] 6. 用户名信息缓存 - 已优化缓存使用

### 后续发现并解决的问题

#### 7. claude_history.md 日期缺失和内容混乱
**发现时间**: 2026-03-26
**问题描述**:
- 不同日期的会话内容混在一起
- 时间戳只显示时间（"%H:%M:%S"），缺少日期
- 导致日期过滤逻辑失效

**解决方案**:
- 修改 `collector.py` 中的 `_entry_to_text()` 方法
- 时间戳格式改为 `"%Y-%m-%d %H:%M:%S"`（包含完整日期）
- 修改 `_get_timestamp()` 方法，增强对各种时间戳格式的支持

**验收结果**: ✅ 已修复，日期过滤正常工作

#### 8. claude_projects.md 没有提取到内容
**发现时间**: 2026-03-26
**问题描述**:
- 项目会话缓存文件为空
- 项目会话的时间戳格式是 ISO 8601（如 "2026-03-25T10:30:00Z"）
- 原 `_get_timestamp()` 方法不支持这种格式

**解决方案**:
- 增强 `_get_timestamp()` 方法，支持 ISO 8601 格式
- 使用 `dateutil.parser.isoparse()` 解析 ISO 8601 时间戳

**验收结果**: ✅ 已修复，项目会话内容正常提取

#### 9. 交互卡片提取包含标签名
**发现时间**: 2026-03-26
**问题描述**:
- 第一版递归提取把所有字符串都提取了
- 包含 `_1`, `vertical`, `blue-50`, `pixels` 等标签名和字段名
- 内容杂乱，难以阅读

**解决方案迭代**:
1. **第一版**: 递归提取所有字符串（问题太多）
2. **第二版**: 结构化提取，按 tag 类型处理（仍有标签名混入）
3. **第三版（最终）**: 只递归提取 `content` 字段，不限制数量

**最终方案**:
```python
def extract_content_recursive(obj: Any):
    """只递归提取content字段"""
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
```

**验收结果**: ✅ 已优化，只显示真实文本内容

#### 10. search_messages_enhanced 返回原始消息
**发现时间**: 2026-03-26
**问题描述**:
- `search_messages_enhanced()` 调用 `_fetch_messages_with_intervals()`
- `_fetch_messages_with_intervals()` 内部调用 `search_messages()`
- `search_messages()` 已经对消息进行了格式化（调用 `_format_search_message_item()`）
- 但 `search_messages_enhanced()` 又尝试格式化一次，导致混乱

**解决方案**:
- 删除 `search_messages_enhanced()` 中重复的格式化步骤
- 直接使用 `search_messages()` 返回的已格式化消息

**验收结果**: ✅ 已修复，消息格式正确

#### 11. happy 命令需要改为 claude 命令
**发现时间**: 2026-03-26
**问题描述**:
- 代码中多处调用 `happy` 命令行工具
- 需要统一改为 `claude` 命令

**修改的文件**:
1. `generator.py` - 主日报生成器
2. `feishu/filter.py` - 会话过滤器
3. `feishu/exporter.py` - 文档导出器
4. `feishu/collector.py` - 数据采集器

**修改内容**:
- 所有 `subprocess.run(["happy", ...])` 改为 `subprocess.run(["claude", ...])`
- 所有错误信息中的 "happy" 改为 "claude"
- 所有日志输出中的 "Calling happy..." 改为 "Calling claude..."

**验收结果**: ✅ 已完成，所有命令已更新

#### 12. 文档导出使用 CLI 而非 skill
**发现时间**: 2026-03-26
**问题描述**:
- 原代码使用 skill 方式导出文档，需要 `~/.claude/arkplan.json`
- 用户要求使用 `feishu-docx` CLI 直接导出

**解决方案**:
- 修改 `_call_feishu_export_skill()` 方法
- 使用 `feishu-docx export <URL> --stdout` 命令
- 添加 `sys` 模块导入以支持备用方案
- 保持缓存机制不变

**修改的文件**:
1. `feishu/exporter.py` - 添加 `sys` 导入，修改 `_call_feishu_export_skill()`

**验收结果**: ✅ 已完成，文档导出改为 CLI 方式

### 最终验收结果

✅ **所有问题已解决**:
1. 飞书聊天内容完整 - 获取到 524 条消息
2. 用户名显示 - 有 mentions 的消息解析正确
3. @用户名替换 - 占位符已正确替换
4. 交互卡片 - 只显示真实文本，无标签名
5. 用户缓存 - 预搜索缓存机制正常工作
6. claude_history - 日期正确，内容分离
7. claude_projects - 内容正常提取
8. 命令行工具 - 已全部改为 claude
9. 文档导出 - 使用 feishu-docx CLI 而非 skill

---

**设计文档完成日期**: 2026-03-24
**实际完成日期**: 2026-03-26
**最后更新**: 2026-03-26

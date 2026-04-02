# 日报系统优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化日报系统，实现按内容类型分类总结、分来源缓存、移除原始内容附录、JSON内容不截断

**Architecture:** 渐进式改造现有代码，新增缓存层，改造收集器返回结构化数据，重写Generator提示词

**Tech Stack:** Python 3, YAML, subprocess (happy LLM)

---

## File Structure

| File | Operation | Purpose |
|------|-----------|---------|
| `cache_manager.py` | Create | 缓存管理模块 |
| `collector.py` | Modify | 新增结构化采集方法 |
| `feishu/collector.py` | Modify | 增强智能纪要识别 |
| `generator.py` | Modify | 新提示词 + 新输出结构 |
| `daily_report.py` | Modify | 集成缓存 + 新流程 |

---

## Task 1: Create CacheManager

**Files:**
- Create: `cache_manager.py`

- [ ] **Step 1: Write the CacheManager class**

```python
"""
缓存管理模块
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


class CacheManager:
    def __init__(self, base_dir: str = "cache"):
        self.base_dir = Path(base_dir)

    def get_cache_dir(self, date: datetime) -> Path:
        """获取指定日期的缓存目录"""
        date_str = date.strftime("%Y-%m-%d")
        cache_dir = self.base_dir / date_str
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def get_cache_path(self, date: datetime, source: str) -> Path:
        """获取指定来源的缓存文件路径"""
        cache_dir = self.get_cache_dir(date)
        return cache_dir / f"{source}.md"

    def has_cache(self, date: datetime, source: str) -> bool:
        """检查缓存是否存在"""
        return self.get_cache_path(date, source).exists()

    def read_cache(self, date: datetime, source: str) -> Optional[str]:
        """读取缓存"""
        cache_path = self.get_cache_path(date, source)
        if not cache_path.exists():
            return None
        with open(cache_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 跳过元数据部分，返回内容
        if "=== 内容 ===" in content:
            return content.split("=== 内容 ===", 1)[1].strip()
        return content

    def write_cache(self, date: datetime, source: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """写入缓存"""
        cache_path = self.get_cache_path(date, source)
        lines = ["=== 元数据 ==="]
        lines.append(f"采集时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"来源: {source}")
        if metadata:
            for k, v in metadata.items():
                lines.append(f"{k}: {v}")
        lines.append("")
        lines.append("=== 内容 ===")
        lines.append(content)

        with open(cache_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def clear_cache(self, date: datetime, source: Optional[str] = None):
        """清除缓存"""
        if source:
            cache_path = self.get_cache_path(date, source)
            cache_path.unlink(missing_ok=True)
        else:
            cache_dir = self.get_cache_dir(date)
            if cache_dir.exists():
                for f in cache_dir.glob("*.md"):
                    f.unlink()
```

- [ ] **Step 2: Verify the file is created**

Run: `ls -la cache_manager.py`
Expected: File exists

- [ ] **Step 3: Commit**

```bash
git add cache_manager.py
git commit -m "feat: add CacheManager for source-separated caching

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 2: Enhance ClaudeCollector

**Files:**
- Modify: `collector.py`

- [ ] **Step 1: Add new methods to ClaudeCollector**

Add these methods at the end of the `ClaudeCollector` class, before the file ends:

```python
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
```

Also add Dict to imports at top:
```python
from typing import List, Dict, Any, Optional, Tuple
```

- [ ] **Step 2: Verify changes**

Run: `python -c "from collector import ClaudeCollector; print('Import OK')"`
Expected: Import OK

- [ ] **Step 3: Commit**

```bash
git add collector.py
git commit -m "feat: add structured collection methods to ClaudeCollector

- collect_structured() returns dict with separate sources
- collect_history_for_date() and collect_projects_for_date() for individual source collection
- _truncate_long_content() for handling very long project sessions

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 3: Update ReportGenerator Prompt

**Files:**
- Modify: `generator.py`

- [ ] **Step 1: Update DAILY_PROMPT_PREFIX**

Replace the `DAILY_PROMPT_PREFIX` (lines 16-44) with:

```python
    # 日报提示词前缀
    DAILY_PROMPT_PREFIX = """【重要：继承任务说明】
如果输入中包含「昨日未完成任务」部分，请：
1. 将这些任务作为今天日报的「四、明日计划」的基础
2. 对于今天会话中提到已经完成的继承任务，移到「二、核心工作内容」中，并标记为已完成
3. 对于今天会话中提到有新进展但未完成的继承任务，保留在「明日计划」中，但更新任务描述
4. 对于没有提到的继承任务，继续保留在「明日计划」中

【重要：飞书聊天说明】
输入中可能包含「飞书会话」部分，这是从飞书聊天中提取的工作相关内容。请：
1. 将其与 Claude 会话记录合并分析
2. 同样区分工作类型
3. 从中提取关键进展、遇到的困难等
4. 飞书聊天记录是重要来源

【重要：飞书文档说明】
输入中可能包含「飞书文档」部分，这是从飞书文档中导出的内容（可能包含 [摘要] 标记）。请：
1. 参考文档内容理解工作背景
2. 如果文档是今天创建或编辑的，可以在关键进展中提及
3. 特别注意标题包含"智能纪要"、"会议纪要"的文档，这些作为会议内容的重要来源
4. 不要直接大段复制文档内容，而是总结与今日工作相关的部分

【重要：来源标注说明】
所有工作内容要点都需要标注来源，格式："| 来源: [来源名称]"
来源名称示例：
- Claude 历史会话
- Claude 项目会话 xxx（会话ID）
- 飞书会话 xxx（群名或对方名）
- 飞书智能纪要 xxx.docx
- 飞书文档 xxx.docx

【重要：内容分类说明】
请将所有工作内容分为以下 4 类：
1. 会议：所有会议相关内容，包括飞书智能纪要、会议讨论等
2. 自主工作：自己主导的设计、开发、决策等
3. 团队管理：团队协作、任务分配、人员管理等
4. 提供支持：帮助他人、review 代码、指导下属等

【重要：不要附录原始内容】
不要在日报最后添加"附录：原始工作记录"或类似章节，所有内容都必须经过总结。

---

"""
```

- [ ] **Step 2: Update _build_daily_prompt() method**

Replace `_build_daily_prompt()` (lines 251-321) with:

```python
    def _build_daily_prompt(self, text: str, date: datetime) -> str:
        """构建日报提示词"""
        return self.DAILY_PROMPT_PREFIX + f"""请根据以下工作会话记录，生成**{date.strftime('%Y-%m-%d')}**的日报。

【重要：日期要求】
- 日报标题必须是：# 日报 - {date.strftime('%Y-%m-%d')}
- 所有内容都必须是关于 {date.strftime('%Y-%m-%d')} 这一天的
- 不要包含其他日期的内容

【重要：数据来源说明】
以下是所有重要的数据来源，请综合分析：
- Claude 历史会话：用户的需求和对话
- Claude 项目会话：AI-agent 执行的结果
- 飞书会话：工作聊天记录（重要来源）
- 飞书文档：包括智能纪要（会议内容重要来源）

工作记录：
{text}

【重要分析要求】
1. 任务状态精细判断（核心！）：
   仔细分析所有会话内容，将任务分为三类：
   a. 【已完成】：
      - 明确说"完成了"、"已解决"、"搞定了"、"做好了"等
      - 有明确的完成结果或输出
      - 会话中没有后续疑问或未解决问题
   b. 【明确计划执行】：
      - 明确说"我明天做"、"接下来要做"、"计划做"等
      - 有明确的执行意向和时间节点
      - 不是随口一提，是认真规划的
   c. 【可能计划执行】：
      - 提到了某个想法或可能性，但不确定是否真的要做
      - 例如"可以考虑"、"或许能"、"要不要试试"等
      - 没有明确的执行承诺

2. 下一步计划分类输出：
   - 只有"明确计划执行"的任务才放入「四、明日计划」
   - "可能计划执行"的任务放入「六、其他备注」，作为观察记录
   - "已完成"的任务绝对不要出现在「明日计划」

3. 下一步计划要具体：
   - 每个任务要有明确的时间节点（如：明日、本周内、3天内等）
   - 如果会话中提到了时间节点，直接使用；没有则合理推测

4. 内容呈现格式：
   - 短内容用要点列表（- 开头）
   - 长内容用段落总结
   - 每个要点或段落后面都要标注来源

请直接输出 Markdown 格式的日报，不要用 JSON 包裹！格式如下：

# 日报 - YYYY-MM-DD

## 一、今日概览
[100-300 字整体总结，区分各类型工作的占比]

## 二、核心工作内容

### 🎯 会议
- [要点摘要] | 来源: [飞书智能纪要 xxx.docx]
- [要点摘要] | 来源: [飞书会话 xxx 群]
- [较长内容用段落总结，关键点标注来源]

### 💻 自主工作
- [要点摘要] | 来源: [Claude 历史会话]
- [要点摘要] | 来源: [Claude 项目会话 xxx]

### 👥 团队管理
- [要点摘要] | 来源: ...

### 🤝 提供支持
- [要点摘要] | 来源: ...

## 三、问题与风险
- [困难 1]
- [困难 2]

## 四、明日计划
- [ ] 任务内容 - 时间节点
- [ ] 任务内容 - 时间节点

## 五、需要支持
- 谁: 需要什么支持

## 六、其他备注
其他备注，包含【可能计划执行】的任务列表

---

## 附录：数据源索引
- Claude 历史会话: N 条消息
- Claude 项目会话: N 个会话
- 飞书会话: N 个
- 飞书文档: N 个（含智能纪要 M 个）
"""
```

- [ ] **Step 3: Update _generate_fallback_report()**

Replace `_generate_fallback_report()` (lines 166-188) with:

```python
    def _generate_fallback_report(self, content: str, date: datetime) -> str:
        """生成fallback日报，直接包含收集到的内容"""
        # 简单统计数据源
        claude_history_count = content.count("=== Claude 历史会话 ===")
        claude_projects_count = content.count("=== Claude 项目会话 ===")
        feishu_chats_count = content.count("=== 飞书会话 ===")
        feishu_docs_count = content.count("=== 飞书文档 ===")

        return f"""# 日报 - {date.strftime('%Y-%m-%d')}

## 一、今日总结
今日有工作记录，详见下方内容。

## 二、核心工作内容

### 💻 自主工作
- 有工作记录，请查看详细内容 | 来源: 综合

## 三、遇到的困难

## 四、明日计划

## 五、需要支持

## 六、其他备注

---

## 附录：数据源索引
- Claude 历史会话: {claude_history_count} 部分
- Claude 项目会话: {claude_projects_count} 部分
- 飞书会话: {feishu_chats_count} 部分
- 飞书文档: {feishu_docs_count} 部分
"""
```

- [ ] **Step 4: Verify changes**

Run: `python -c "from generator import ReportGenerator; print('Import OK')"`
Expected: Import OK

- [ ] **Step 5: Commit**

```bash
git add generator.py
git commit -m "feat: update ReportGenerator with new prompt and structure

- Remove raw content appendix requirement
- Add 4-category content classification (meeting/independent/team/support)
- Add source annotation requirements
- Update fallback report format
- Emphasize Feishu chats as important source

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 4: Integrate Cache into daily_report.py

**Files:**
- Modify: `daily_report.py`

- [ ] **Step 1: Add imports**

At the top, add:

```python
from cache_manager import CacheManager
```

- [ ] **Step 2: Add build_combined_text function**

Add before `get_dates_to_process()`:

```python
def build_combined_text(structured_data: Dict[str, str]) -> str:
    """
    构建传给 LLM 的聚合文本，保留来源标识
    """
    parts = []
    if structured_data.get("claude_history"):
        parts.append("=== Claude 历史会话 ===\n" + structured_data["claude_history"])
    if structured_data.get("claude_projects"):
        parts.append("=== Claude 项目会话 ===\n" + structured_data["claude_projects"])
    if structured_data.get("feishu_chats"):
        parts.append("=== 飞书会话 ===\n" + structured_data["feishu_chats"])
    if structured_data.get("feishu_docs"):
        parts.append("=== 飞书文档 ===\n" + structured_data["feishu_docs"])
    if structured_data.get("inherited_tasks"):
        parts.append(structured_data["inherited_tasks"])
    return "\n\n".join(parts)
```

- [ ] **Step 3: Modify collect_all_sources function**

Replace `collect_all_sources()` (lines 55-82) with:

```python
def collect_all_sources(
    date: datetime,
    config: dict,
    force: bool = False
) -> Tuple[str, Dict[str, str]]:
    """
    收集所有数据源

    Returns: (聚合文本, 结构化数据字典)
    """
    cache_mgr = CacheManager()
    structured_data = {}
    parts = []

    # 1. Claude 历史会话
    claude_collector = ClaudeCollector(
        config["claude"]["history_path"],
        config["claude"]["projects_path"],
    )

    source = "claude_history"
    if force or not cache_mgr.has_cache(date, source):
        content = claude_collector.collect_history_for_date(date)
        session_count = content.count("\n--- 会话:") if content else 0
        metadata = {"条数": str(session_count)}
        cache_mgr.write_cache(date, source, content, metadata)
    else:
        content = cache_mgr.read_cache(date, source) or ""
    structured_data[source] = content
    if content:
        parts.append("=== Claude 历史会话 ===\n" + content)

    # 2. Claude 项目会话
    source = "claude_projects"
    if force or not cache_mgr.has_cache(date, source):
        content = claude_collector.collect_projects_for_date(date)
        content = claude_collector._truncate_long_content(content)
        session_count = content.count("\n--- 会话:") if content else 0
        metadata = {"条数": str(session_count)}
        cache_mgr.write_cache(date, source, content, metadata)
    else:
        content = cache_mgr.read_cache(date, source) or ""
    structured_data[source] = content
    if content:
        parts.append("=== Claude 项目会话 ===\n" + content)

    # 3. 飞书集成
    if config.get("feishu", {}).get("enabled", False) and validate_feishu_config(config):
        feishu_result = collect_feishu_sources(date, config, force)
        if feishu_result:
            parts.append(feishu_result)
            # 简单拆分 feishu 内容（实际应结构化返回）
            if "=== 飞书会话总结 ===" in feishu_result:
                structured_data["feishu_chats"] = feishu_result
            if "=== 飞书文档 ===" in feishu_result:
                structured_data["feishu_docs"] = feishu_result

    # 4. 继承任务
    inheritance_mgr = TaskInheritanceManager(config["report"]["base_dir"])
    yesterday = date - timedelta(days=1)
    inherited_tasks = inheritance_mgr.get_incomplete_tasks_from_daily(yesterday)
    if inherited_tasks:
        tasks_text = inheritance_mgr._format_tasks_for_prompt(inherited_tasks)
        parts.append(tasks_text)
        structured_data["inherited_tasks"] = tasks_text

    combined_text = "\n\n".join(parts)
    return combined_text, structured_data
```

- [ ] **Step 4: Update main() to use new collect_all_sources**

In `main()`, find lines 331-337:

```python
        # 采集所有数据源
        conversation_text = collect_all_sources(date, config, args.force)
        if args.verbose:
            print(f"  Collected {len(conversation_text)} chars of content")

        # 生成日报
        output_path = generator.generate_daily(date, conversation_text)
```

Replace with:

```python
        # 采集所有数据源
        conversation_text, structured_data = collect_all_sources(date, config, args.force)
        if args.verbose:
            print(f"  Collected {len(conversation_text)} chars of content")
            print(f"  Sources: {list(structured_data.keys())}")

        # 生成日报
        output_path = generator.generate_daily(date, conversation_text)
```

Also add Tuple to imports:

```python
from typing import Dict, Any, List, Optional, Tuple
```

- [ ] **Step 5: Verify changes**

Run: `python daily_report.py --help`
Expected: Help text displayed without errors

- [ ] **Step 6: Commit**

```bash
git add daily_report.py
git commit -m "feat: integrate CacheManager into main workflow

- Add CacheManager import and integration
- Modify collect_all_sources() to use cache and return structured data
- Add build_combined_text() helper
- Update main() to handle new return format

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 5: Test End-to-End Flow

**Files:**
- All (for testing)

- [ ] **Step 1: Run a test generation**

First, let's verify the code can import everything:

```bash
python -c "
from cache_manager import CacheManager
from collector import ClaudeCollector
from generator import ReportGenerator
from datetime import datetime
print('All imports OK')
"
```
Expected: All imports OK

- [ ] **Step 2: Test CacheManager basic operations**

```bash
python -c "
from cache_manager import CacheManager
from datetime import datetime
import tempfile
import shutil

cache_dir = tempfile.mkdtemp()
try:
    cm = CacheManager(cache_dir)
    date = datetime.now()

    # Write cache
    cm.write_cache(date, 'test_source', 'test content', {'key': 'value'})
    print('Write OK')

    # Check cache exists
    assert cm.has_cache(date, 'test_source')
    print('Has cache OK')

    # Read cache
    content = cm.read_cache(date, 'test_source')
    assert content == 'test content'
    print('Read OK')

    print('CacheManager test passed!')
finally:
    shutil.rmtree(cache_dir)
"
```
Expected: CacheManager test passed!

- [ ] **Step 3: Try generating a report (dry run)**

```bash
python daily_report.py --date 2026-03-25 --verbose --force
```
Expected: No Python errors, may fail at happy LLM call but that's expected

- [ ] **Step 4: Final verification**

Check git status and make sure everything is committed:

```bash
git status
git diff HEAD~5 --stat
```

---

## Summary

The plan is complete! The implementation will:

1. Add `CacheManager` for source-separated caching
2. Enhance `ClaudeCollector` with structured collection methods
3. Update `ReportGenerator` with new prompt and output structure
4. Integrate caching into `daily_report.py` main workflow
5. Test the end-to-end flow

All tasks follow bite-sized, test-as-you-go pattern with frequent commits.

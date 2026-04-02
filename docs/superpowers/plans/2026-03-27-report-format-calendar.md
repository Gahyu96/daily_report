# 日报格式优化 + 日历集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复飞书日历数据未注入 LLM 的 bug，并将日报/周报/月报的输出格式升级为按上下午分组、子弹点展开、末尾集中标注来源的风格，周报/月报新增亮点卡片，月报改为真实 LLM 生成。

**Architecture:** 两个文件改动：`daily_report.py` 修复 `build_combined_text` 把日历数据加入拼接；`generator.py` 重写三个报告的提示词，并将月报的 `_call_llm_for_monthly` 从 JSON mock 改为真实 LLM 调用。测试放在 `tests/` 目录，用 pytest。

**Tech Stack:** Python 3, pytest, subprocess (claude CLI), 现有 `generator.py` / `daily_report.py` 结构

---

## File Map

| 文件 | 操作 | 说明 |
|------|------|------|
| `daily_report.py` | Modify line 57-72 | `build_combined_text` 加入 `feishu_calendar` |
| `generator.py` | Modify | `DAILY_PROMPT_PREFIX`、`_build_daily_prompt`、`WEEKLY_PROMPT_PREFIX`、`_build_weekly_prompt`、`MONTHLY_PROMPT_PREFIX`、`_build_monthly_prompt`（新增）、`_call_llm_for_monthly`、`_parse_monthly_result` |
| `tests/test_build_combined_text.py` | Create | 测试日历数据注入 |
| `tests/test_generator_prompts.py` | Create | 测试三种报告的提示词格式 |
| `tests/test_monthly_llm.py` | Create | 测试月报 LLM 生成路径 |

---

## Task 1: 修复 `build_combined_text` 注入日历数据

**Files:**
- Modify: `daily_report.py:57-72`
- Create: `tests/test_build_combined_text.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_build_combined_text.py`：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from daily_report import build_combined_text


def test_feishu_calendar_included():
    data = {
        "feishu_calendar": "## 2026-03-27\n- 10:00 调研会",
    }
    result = build_combined_text(data)
    assert "=== 飞书日程 ===" in result
    assert "调研会" in result


def test_feishu_calendar_excluded_when_empty():
    data = {"feishu_calendar": ""}
    result = build_combined_text(data)
    assert "飞书日程" not in result


def test_feishu_calendar_excluded_when_missing():
    data = {"claude_history": "some content"}
    result = build_combined_text(data)
    assert "飞书日程" not in result


def test_all_sources_order():
    """日历应该在飞书文档之后出现"""
    data = {
        "feishu_docs": "doc content",
        "feishu_calendar": "calendar content",
    }
    result = build_combined_text(data)
    doc_pos = result.find("飞书文档")
    cal_pos = result.find("飞书日程")
    assert doc_pos < cal_pos
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/liangjiayu/projects/daily_report
python -m pytest tests/test_build_combined_text.py -v
```

期望：`FAILED` - `assert "=== 飞书日程 ===" in result`

- [ ] **Step 3: 修改 `build_combined_text`**

打开 `daily_report.py`，在 `build_combined_text` 函数的 `if structured_data.get("feishu_docs"):` 块之后加入：

```python
    if structured_data.get("feishu_calendar"):
        parts.append("=== 飞书日程 ===\n" + structured_data["feishu_calendar"])
```

完整函数改后如下（第57-72行区域）：

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
    if structured_data.get("feishu_calendar"):
        parts.append("=== 飞书日程 ===\n" + structured_data["feishu_calendar"])
    if structured_data.get("inherited_tasks"):
        parts.append(structured_data["inherited_tasks"])
    return "\n\n".join(parts)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_build_combined_text.py -v
```

期望：4 个 PASSED

- [ ] **Step 5: Commit**

```bash
git add daily_report.py tests/test_build_combined_text.py
git commit -m "fix: inject feishu_calendar into build_combined_text"
```

---

## Task 2: 更新 `DAILY_PROMPT_PREFIX` 加入日历说明

**Files:**
- Modify: `generator.py:17-59`（`DAILY_PROMPT_PREFIX` 常量）
- Create: `tests/test_generator_prompts.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_generator_prompts.py`：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from generator import ReportGenerator


def make_gen():
    return ReportGenerator("~/.claude/arkplan.json", "/tmp/test_reports")


def test_daily_prefix_has_calendar_instructions():
    gen = make_gen()
    assert "飞书日程" in gen.DAILY_PROMPT_PREFIX
    assert "上午" in gen.DAILY_PROMPT_PREFIX or "上下午" in gen.DAILY_PROMPT_PREFIX


def test_weekly_prompt_has_highlight_card():
    from datetime import datetime
    gen = make_gen()
    prompt = gen._build_weekly_prompt("some daily content", 2026, 13)
    assert "⭐ 本周亮点" in prompt


def test_monthly_prompt_has_highlight_card():
    gen = make_gen()
    prompt = gen._build_monthly_prompt("some daily content", 2026, 3)
    assert "⭐ 本月亮点" in prompt
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_generator_prompts.py::test_daily_prefix_has_calendar_instructions -v
```

期望：FAILED

- [ ] **Step 3: 修改 `DAILY_PROMPT_PREFIX`**

在 `generator.py` 中，找到 `DAILY_PROMPT_PREFIX` 的 `---\n\n"""` 结束行之前，加入新的说明块：

```python
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

【重要：飞书日程说明】
输入中可能包含「飞书日程」部分，这是当天的日历事件数据。请：
1. 用日程的开始时间判断事件属于上午（12点前）还是下午/晚上（12点后）
2. 将会议类日程与飞书聊天/纪要对照，补充完整的会议信息（日程是会议的骨架，聊天纪要是肉）
3. 日程时间是上下午分组的主要依据；没有日程时，根据消息时间戳推断

【重要：来源标注说明】
所有工作内容要点都需要在每个工作类型章节末尾集中标注来源，格式：
> 📎 来源: [来源名称1] · [来源名称2]
来源名称示例：
- Claude 历史会话
- Claude 项目会话 xxx（会话ID）
- 飞书会话 xxx（群名或对方名）
- 飞书智能纪要 xxx.docx
- 飞书文档 xxx.docx
- 飞书日程

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

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_generator_prompts.py::test_daily_prefix_has_calendar_instructions -v
```

期望：PASSED

- [ ] **Step 5: Commit**

```bash
git add generator.py tests/test_generator_prompts.py
git commit -m "feat: add feishu calendar instructions to DAILY_PROMPT_PREFIX"
```

---

## Task 3: 重写 `_build_daily_prompt` — 上下午分组格式

**Files:**
- Modify: `generator.py:287-381`（`_build_daily_prompt` 方法）

- [ ] **Step 1: 写失败测试**

在 `tests/test_generator_prompts.py` 追加：

```python
def test_daily_prompt_has_am_pm_sections():
    from datetime import datetime
    gen = make_gen()
    prompt = gen._build_daily_prompt("some content", datetime(2026, 3, 27))
    assert "🌅 上午" in prompt
    assert "🌆 下午" in prompt

def test_daily_prompt_has_sub_bullet_format():
    from datetime import datetime
    gen = make_gen()
    prompt = gen._build_daily_prompt("some content", datetime(2026, 3, 27))
    # 子弹点格式
    assert "  - " in prompt

def test_daily_prompt_has_grouped_source_format():
    from datetime import datetime
    gen = make_gen()
    prompt = gen._build_daily_prompt("some content", datetime(2026, 3, 27))
    assert "> 📎 来源:" in prompt
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_generator_prompts.py::test_daily_prompt_has_am_pm_sections -v
```

期望：FAILED

- [ ] **Step 3: 重写 `_build_daily_prompt`**

将 `generator.py` 中 `_build_daily_prompt` 方法替换为：

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
- 飞书日程：当天日历事件，用于确定上下午时间分组

工作记录：
{text}

【重要分析要求】
1. 任务状态精细判断（核心！）：
   仔细分析所有会话内容，将任务分为三类：
   a. 【已完成】：明确说"完成了"、"已解决"、"搞定了"等，有明确的完成结果
   b. 【明确计划执行】：明确说"我明天做"、"接下来要做"、"计划做"等，有执行意向
   c. 【可能计划执行】：提到某想法但不确定是否真的要做，如"可以考虑"、"或许能"等

2. 下一步计划分类输出：
   - 只有"明确计划执行"的任务才放入「四、明日计划」
   - "可能计划执行"的任务放入「六、其他备注」
   - "已完成"的任务绝对不要出现在「明日计划」

3. 上下午时间分组规则：
   - 优先用飞书日程的开始时间判断（12点前=上午，12点后=下午，18点后=晚上）
   - 没有日程的内容，根据飞书消息/Claude会话的时间戳判断
   - 如果某时间段完全没有工作内容，不显示该时间段章节
   - 时间段标题括号内填写该时间段实际的起止时间，如"🌅 上午（09:30-11:45）"

4. 内容呈现格式（严格遵循）：
   - 每个事项用 `- 事项标题` 开头
   - 该事项的 2-3 个关键细节用 `  - 子点` 格式（2个空格缩进）
   - 每个工作类型章节（如 **🎯 会议**）的所有来源集中在末尾一行标注：
     `> 📎 来源: 来源1 · 来源2`
   - 如果某工作类型在某时间段没有内容，不显示该类型

请直接输出 Markdown 格式的日报，不要用 JSON 包裹！格式如下：

# 日报 - {date.strftime('%Y-%m-%d')}

## 一、今日概览
[100-300 字整体总结，说明上下午各自的工作重心和整体成果]

## 二、核心工作内容

### 🌅 上午（HH:MM-12:00）

**🎯 会议**
- 事项标题
  - 关键细节 1
  - 关键细节 2

> 📎 来源: 飞书智能纪要 xxx.docx · 飞书会话 xxx群

**💻 自主工作**
- 事项标题
  - 关键细节

> 📎 来源: Claude 项目会话

### 🌆 下午（13:00-HH:MM）

**👥 团队管理**
- 事项标题
  - 关键细节

> 📎 来源: 飞书会话 xxx群 · 私聊 xxx

**🤝 提供支持**
- 事项标题
  - 关键细节

> 📎 来源: 飞书会话 xxx群

### 🌙 晚上（18:00以后）（如有内容才显示此章节）
[同上格式]

## 三、问题与风险
- 问题描述（简要说明影响和当前状态）

## 四、明日计划
- [ ] 任务内容 - 时间节点

## 五、需要支持
- 谁: 需要什么支持

## 六、其他备注
【可能计划执行】的任务列表（如无则省略）

---

## 附录：数据源索引
- Claude 历史会话: N 条消息
- Claude 项目会话: N 个会话
- 飞书会话: N 个（M个群聊 + K个私聊）
- 飞书文档: N 个（含智能纪要 M 个）
- 飞书日程: N 个事件
"""
```

- [ ] **Step 4: 运行所有日报相关测试**

```bash
python -m pytest tests/test_generator_prompts.py -k "daily" -v
```

期望：3 个 PASSED（`test_daily_prefix_has_calendar_instructions`、`test_daily_prompt_has_am_pm_sections`、`test_daily_prompt_has_sub_bullet_format`、`test_daily_prompt_has_grouped_source_format`）

- [ ] **Step 5: Commit**

```bash
git add generator.py tests/test_generator_prompts.py
git commit -m "feat: rewrite daily report prompt with AM/PM grouping and sub-bullets"
```

---

## Task 4: 重写 `_build_weekly_prompt` — 亮点卡片 + 优化格式

**Files:**
- Modify: `generator.py:405-451`（`_build_weekly_prompt` 方法）
- Modify: `generator.py:62-89`（`WEEKLY_PROMPT_PREFIX`，加来源标注说明）

- [ ] **Step 1: 运行测试确认失败**

```bash
python -m pytest tests/test_generator_prompts.py::test_weekly_prompt_has_highlight_card -v
```

期望：FAILED（`_build_weekly_prompt` 尚未有 `⭐ 本周亮点`）

- [ ] **Step 2: 更新 `WEEKLY_PROMPT_PREFIX`**

将 `generator.py` 中的 `WEEKLY_PROMPT_PREFIX` 替换为：

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

【重要：来源标注说明】
每个工作类型章节末尾集中标注来源：
> 📎 来源: [来源名称1] · [来源名称2]

---

"""
```

- [ ] **Step 3: 重写 `_build_weekly_prompt`**

将 `generator.py` 中 `_build_weekly_prompt` 方法替换为：

```python
    def _build_weekly_prompt(self, text: str, year: int, week: int) -> str:
        """构建周报提示词"""
        return self.WEEKLY_PROMPT_PREFIX + f"""请根据以下日报内容，生成**{year}年第{week}周**的周报。

【重要：内容格式要求】
- 每个事项用 `- 事项标题` 开头
- 该事项的 2-3 个关键细节用 `  - 子点` 格式（2个空格缩进）
- 每个工作类型章节末尾集中标注来源：`> 📎 来源: 来源1 · 来源2`
- 没有内容的工作类型章节不显示

请直接输出 Markdown 格式的周报，不要用 JSON 包裹！格式如下：

# 周报 - {year}年第{week}周

## ⭐ 本周亮点
> 本周最重要的 2-3 项成果，每条一句话

1. **成果标题** - 简要说明影响或结果
2. **成果标题** - 简要说明影响或结果

## 一、本周概览
[200-400 字整体总结，说明工作重心、整体成果和工作分布]

## 二、核心工作内容

### 🎯 会议
- 事项标题
  - 关键细节 1
  - 关键细节 2

> 📎 来源: 飞书智能纪要 xxx.docx

### 💻 自主工作
- 事项标题
  - 关键细节

> 📎 来源: Claude 项目会话

### 👥 团队管理
- 事项标题
  - 关键细节

> 📎 来源: 飞书会话 xxx群

### 🤝 提供支持
- 事项标题

> 📎 来源: 飞书会话 xxx

## 三、问题与风险
- 问题描述

## 四、下周计划
- [ ] 任务内容 - 时间节点

## 五、需要协调
- 协调事项

---

## 附录：日报来源
- YYYY-MM-DD（星期几）

以下是各天的日报内容：
{text}
"""
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_generator_prompts.py::test_weekly_prompt_has_highlight_card -v
```

期望：PASSED

- [ ] **Step 5: Commit**

```bash
git add generator.py
git commit -m "feat: rewrite weekly report prompt with highlight cards and sub-bullets"
```

---

## Task 5: 修复月报 LLM 生成 + 新增 `_build_monthly_prompt`

**Files:**
- Modify: `generator.py:92-119`（`MONTHLY_PROMPT_PREFIX`）
- Modify: `generator.py:672-683`（`_call_llm_for_monthly`）
- Modify: `generator.py:725-756`（`_parse_monthly_result`）
- Create new method: `generator.py`（`_build_monthly_prompt`，插入在 `_call_llm_for_monthly` 之前）
- Create: `tests/test_monthly_llm.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_monthly_llm.py`：

```python
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).parent.parent))

from generator import ReportGenerator


def make_gen(tmp_path=None):
    base = str(tmp_path) if tmp_path else "/tmp/test_monthly_reports"
    return ReportGenerator("~/.claude/arkplan.json", base)


def test_build_monthly_prompt_exists():
    """_build_monthly_prompt 方法存在且返回正确格式"""
    gen = make_gen()
    prompt = gen._build_monthly_prompt("some daily content", 2026, 3)
    assert "⭐ 本月亮点" in prompt
    assert "2026年3月" in prompt
    assert "下月重点" in prompt


def test_call_llm_for_monthly_calls_subprocess():
    """_call_llm_for_monthly 调用 subprocess 而非返回 JSON mock"""
    gen = make_gen()
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "# 月报 - 2026年3月\n\n## ⭐ 本月亮点\n1. 成果"

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        result = gen._call_llm_for_monthly("some content", 2026, 3)

    mock_run.assert_called_once()
    assert "月报" in result
    # 确认不是 JSON mock
    import json
    try:
        json.loads(result)
        assert False, "Should not be JSON"
    except (json.JSONDecodeError, ValueError):
        pass


def test_parse_monthly_result_handles_markdown():
    """_parse_monthly_result 能处理 Markdown 格式（非 JSON）"""
    gen = make_gen()
    markdown_input = """# 月报 - 2026年3月

## ⭐ 本月亮点
1. **完成日报系统升级** - 提升日报质量

## 一、本月概览
本月主要工作包括...

## 四、下月重点
- [ ] 完成xxx功能
"""
    result = gen._parse_monthly_result(markdown_input, 2026, 3)
    assert "# 月报 - 2026年3月" in result
    assert "⭐ 本月亮点" in result


def test_parse_monthly_result_normalizes_header():
    """标题被规范化为正确日期"""
    gen = make_gen()
    wrong_header = "# 月报 - 2026年99月\n\n## ⭐ 本月亮点"
    result = gen._parse_monthly_result(wrong_header, 2026, 3)
    assert "# 月报 - 2026年3月" in result
    assert "99月" not in result
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_monthly_llm.py -v
```

期望：全部 FAILED（`_build_monthly_prompt` 不存在，`_call_llm_for_monthly` 返回 JSON）

- [ ] **Step 3: 更新 `MONTHLY_PROMPT_PREFIX`**

将 `generator.py` 中 `MONTHLY_PROMPT_PREFIX` 替换为：

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
2. 从中提取关键进展、遇到的困难等

【重要：来源标注说明】
每个工作类型章节末尾集中标注来源：
> 📎 来源: [来源名称1] · [来源名称2]

---

"""
```

- [ ] **Step 4: 新增 `_build_monthly_prompt` 方法**

在 `generator.py` 中，在 `_call_llm_for_monthly` 方法之前插入：

```python
    def _build_monthly_prompt(self, text: str, year: int, month: int) -> str:
        """构建月报提示词"""
        return self.MONTHLY_PROMPT_PREFIX + f"""请根据以下日报内容，生成**{year}年{month}月**的月报。

【重要：内容格式要求】
- 每个事项用 `- 事项标题` 开头
- 该事项的 2-3 个关键细节用 `  - 子点` 格式（2个空格缩进）
- 每个工作类型章节末尾集中标注来源：`> 📎 来源: 来源1 · 来源2`

请直接输出 Markdown 格式的月报，不要用 JSON 包裹！格式如下：

# 月报 - {year}年{month}月

## ⭐ 本月亮点
> 本月最重要的 3-5 项成果，每条一句话

1. **成果标题** - 简要说明影响或结果
2. **成果标题** - 简要说明影响或结果
3. **成果标题** - 简要说明影响或结果

## 一、本月概览
[300-500 字整体总结，说明工作重心、整体成果和工作分布]

## 二、核心工作内容

### 🎯 会议
- 事项标题
  - 关键细节

> 📎 来源: ...

### 💻 自主工作
- 事项标题
  - 关键细节

> 📎 来源: ...

### 👥 团队管理
- 事项标题

> 📎 来源: ...

### 🤝 提供支持
- 事项标题

> 📎 来源: ...

## 三、问题与风险
- 问题描述

## 四、下月重点
- [ ] 重点任务 - 时间节点

## 五、需要协调
- 协调事项

---

## 附录：周报来源
- YYYY年第W周

以下是各天的日报内容：
{text}
"""
```

- [ ] **Step 5: 重写 `_call_llm_for_monthly`**

将 `generator.py` 中 `_call_llm_for_monthly` 方法替换为：

```python
    def _call_llm_for_monthly(self, text: str, year: int, month: int) -> str:
        """调用 LLM 生成月报"""
        prompt = self._build_monthly_prompt(text, year, month)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
            f.write(prompt)
            temp_path = f.name

        try:
            cmd = [
                "claude",
                "--settings", str(self.arkplan_settings),
                "--model", "doubao-seed-2-0-code-plan",
                "--print",
                "--no-session-persistence",
                "--tools", "",
            ]

            print(f"Calling claude for monthly report...")
            with open(temp_path, "r", encoding="utf-8") as f:
                prompt_content = f.read()

            result = subprocess.run(
                cmd,
                input=prompt_content,
                capture_output=True,
                text=True,
                timeout=600,
            )

            if result.returncode != 0:
                print(f"Warning: claude failed, using mock result")
                return self._get_mock_monthly_result(year, month)

            print(f"Claude response received ({len(result.stdout)} chars)")
            return result.stdout

        except Exception as e:
            print(f"Warning: Failed to call claude: {e}, using mock result")
            return self._get_mock_monthly_result(year, month)
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except:
                pass
```

- [ ] **Step 6: 新增 `_get_mock_monthly_result` 方法**

在 `_call_llm_for_monthly` 之后添加：

```python
    def _get_mock_monthly_result(self, year: int, month: int) -> str:
        """获取 mock 月报结果"""
        return f"""# 月报 - {year}年{month}月

## ⭐ 本月亮点
1. **工作记录完整** - 本月工作已记录

## 一、本月概览
本月工作记录已收集。

## 二、核心工作内容

### 💻 自主工作
- 有工作记录

> 📎 来源: 综合

## 三、问题与风险

## 四、下月重点
- [ ] 跟进各项工作

## 五、需要协调
"""
```

- [ ] **Step 7: 重写 `_parse_monthly_result`**

将 `generator.py` 中 `_parse_monthly_result` 方法替换为：

```python
    def _parse_monthly_result(self, result: str, year: int, month: int) -> str:
        """解析月报结果（Markdown 格式）"""
        correct_header = f"# 月报 - {year}年{month}月"

        if "# 月报" in result:
            lines = result.split("\n")
            cleaned_lines = []
            in_report = False
            for line in lines:
                if line.strip().startswith("# 月报"):
                    in_report = True
                    cleaned_lines.append(correct_header)
                elif in_report:
                    cleaned_lines.append(line)
            if cleaned_lines:
                return "\n".join(cleaned_lines)

        print(f"Warning: Could not find monthly report header, using raw text")
        return f"""{correct_header}

## 一、本月概览
{result[:800]}

## 二、核心工作内容

## 三、问题与风险

## 四、下月重点

## 五、需要协调
"""
```

- [ ] **Step 8: 运行所有月报测试，确认通过**

```bash
python -m pytest tests/test_monthly_llm.py -v
```

期望：4 个 PASSED

- [ ] **Step 9: 运行所有测试，确认无回归**

```bash
python -m pytest tests/ -v
```

期望：全部 PASSED

- [ ] **Step 10: Commit**

```bash
git add generator.py tests/test_monthly_llm.py
git commit -m "feat: implement monthly report LLM generation with highlight cards"
```

---

## Task 6: 集成验证

**Files:**
- 无新文件，验证端到端流程

- [ ] **Step 1: 运行完整测试套件**

```bash
cd /Users/liangjiayu/projects/daily_report
python -m pytest tests/ -v
```

期望：全部 PASSED

- [ ] **Step 2: 手动验证日报提示词包含日历数据**

```bash
python -c "
import sys
sys.path.insert(0, '.')
from generator import ReportGenerator
from datetime import datetime

gen = ReportGenerator('~/.claude/arkplan.json', 'reports')
text = '=== 飞书日程 ===\n## 2026-03-27\n- 10:00-11:30 AI效率调研会\n- 14:00-15:00 产品评审'
prompt = gen._build_daily_prompt(text, datetime(2026, 3, 27))
print('飞书日程 in prefix:', '飞书日程' in gen.DAILY_PROMPT_PREFIX)
print('🌅 上午 in prompt:', '🌅 上午' in prompt)
print('> 📎 来源: in prompt:', '> 📎 来源:' in prompt)
print('⭐ in weekly:', '⭐ 本周亮点' in gen._build_weekly_prompt('test', 2026, 13))
print('⭐ in monthly:', '⭐ 本月亮点' in gen._build_monthly_prompt('test', 2026, 3))
"
```

期望输出：
```
飞书日程 in prefix: True
🌅 上午 in prompt: True
> 📎 来源: in prompt: True
⭐ in weekly: True
⭐ in monthly: True
```

- [ ] **Step 3: 最终 commit（如有遗漏文件）**

```bash
git status
# 确认所有文件已提交
```

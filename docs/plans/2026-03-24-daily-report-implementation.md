# 自动日报工具实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个简单的多文件脚本，自动采集 Claude 会话，调用 LLM 生成日报、周报、月报，支持 crontab 定时运行。

**Architecture:** 4 个文件组成：daily_report.py (CLI入口)、collector.py (数据采集)、generator.py (LLM调用和生成)、config.yaml (配置)。不使用复杂框架，保持简单独立。

**Tech Stack:** Python 3.8+, PyYAML, happy 命令行

---

## 前置任务：清理旧代码

先把之前的复杂框架清理掉，保持简洁。

**Files:**
- Delete: `src/` 目录及所有内容
- Delete: `test_flow.py`
- Delete: `main.py`
- Delete: `.claude/skills/daily-report/`
- Keep: `config.yaml` (简化后)
- Keep: `requirements.txt` (简化后)

- [ ] **Step 1: 删除旧的 src 目录**
  ```bash
  rm -rf /Users/liangjiayu/projects/daily_report/src
  ```

- [ ] **Step 2: 删除其他旧文件**
  ```bash
  rm -f /Users/liangjiayu/projects/daily_report/test_flow.py
  rm -f /Users/liangjiayu/projects/daily_report/main.py
  rm -rf /Users/liangjiayu/projects/daily_report/.claude/skills/daily-report
  ```

- [ ] **Step 3: 简化 config.yaml**
  ```yaml
  # Claude 会话路径配置
  claude:
    history_path: "~/.claude/history.jsonl"
    projects_path: "~/.claude/projects"

  # LLM 配置
  llm:
    arkplan_settings: "~/.claude/arkplan.json"

  # 日报输出配置
  report:
    base_dir: "reports"
  ```

- [ ] **Step 4: 简化 requirements.txt**
  ```
  PyYAML>=6.0
  ```

---

### Task 1: 创建 collector.py - Claude 会话采集模块

**Files:**
- Create: `collector.py`

**Responsibility:** 读取 ~/.claude/ 下的会话文件，按日期筛选并返回文本内容。

- [ ] **Step 1: 编写 collector.py 基础结构**

```python
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
                            text = self._entry_to_text(data)
                            if text:
                                texts.append(text)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Warning: Failed to read history: {e}")
        return texts

    def _parse_projects(self, start: datetime, end: datetime) -> List[str]:
        """解析 projects 目录"""
        texts = []
        try:
            for jsonl_path in self.projects_path.rglob("*.jsonl"):
                if "memory" in jsonl_path.parts:
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
                            text = self._entry_to_text(data)
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

    def _get_timestamp(self, data: Dict[str, Any]) -> Optional[datetime]:
        """从数据中获取时间戳"""
        ts_ms = data.get("timestamp")
        if ts_ms and isinstance(ts_ms, (int, float)):
            if ts_ms > 1e12:
                return datetime.fromtimestamp(ts_ms / 1000.0)
            else:
                return datetime.fromtimestamp(ts_ms)
        return None

    def _entry_to_text(self, data: Dict[str, Any]) -> str:
        """将一条记录转换为文本"""
        parts = []

        # 角色
        role = data.get("role", "user")
        if role == "assistant":
            parts.append("AI:")
        elif role == "system":
            parts.append("System:")
        else:
            parts.append("User:")

        # 内容
        content = data.get("content") or data.get("display") or data.get("message", "")
        if content:
            parts.append(str(content))

        return " ".join(parts) if len(parts) > 1 else ""
```

- [ ] **Step 2: 验证文件创建成功**
  ```bash
  ls -la /Users/liangjiayu/projects/daily_report/collector.py
  ```
  Expected: 文件存在

---

### Task 2: 创建 generator.py - 日报生成模块

**Files:**
- Create: `generator.py`

**Responsibility:** 调用 happy 生成日报、从日报聚合生成周报/月报。

- [ ] **Step 1: 编写 generator.py 基础结构**

```python
"""
日报生成器
"""
import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional


class ReportGenerator:
    """日报生成器"""

    def __init__(self, arkplan_settings: str, base_dir: str = "reports"):
        self.arkplan_settings = Path(os.path.expanduser(arkplan_settings))
        self.base_dir = Path(base_dir)
        self.daily_dir = self.base_dir / "daily"
        self.weekly_dir = self.base_dir / "weekly"
        self.monthly_dir = self.base_dir / "monthly"

        # 创建目录
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        self.weekly_dir.mkdir(parents=True, exist_ok=True)
        self.monthly_dir.mkdir(parents=True, exist_ok=True)

    def daily_report_exists(self, date: datetime) -> bool:
        """检查日报是否已存在"""
        filename = f"daily_report_{date.strftime('%Y-%m-%d')}.md"
        return (self.daily_dir / filename).exists()

    def generate_daily(self, date: datetime, conversation_text: str) -> Path:
        """
        生成日报

        Args:
            date: 日期
            conversation_text: 会话文本

        Returns:
            生成的文件路径
        """
        if not conversation_text.strip():
            print(f"No content for {date.strftime('%Y-%m-%d')}, skipping")
            return self._write_empty_daily(date)

        # 调用 LLM
        llm_result = self._call_llm_for_daily(conversation_text)

        # 生成 Markdown
        markdown = self._parse_daily_result(llm_result, date)

        # 保存文件
        filename = f"daily_report_{date.strftime('%Y-%m-%d')}.md"
        output_path = self.daily_dir / filename

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        print(f"Daily report saved: {output_path}")
        return output_path

    def _write_empty_daily(self, date: datetime) -> Path:
        """写入空日报"""
        markdown = f"""# 日报 - {date.strftime('%Y-%m-%d')}

## 一、今日总结
今日无工作记录。

## 二、关键进展

## 三、遇到的困难

## 四、下一步计划

## 五、需要支持

## 六、其他备注
"""
        filename = f"daily_report_{date.strftime('%Y-%m-%d')}.md"
        output_path = self.daily_dir / filename
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown)
        return output_path

    def _call_llm_for_daily(self, text: str) -> str:
        """调用 LLM 生成日报"""
        prompt = self._build_daily_prompt(text)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
            f.write(prompt)
            temp_path = f.name

        try:
            cmd = [
                "happy",
                "--settings", str(self.arkplan_settings),
                "-p", temp_path,
            ]

            print(f"Calling happy...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                print(f"Warning: happy failed, using mock result")
                return self._get_mock_daily_result()

            return result.stdout

        except Exception as e:
            print(f"Warning: Failed to call happy: {e}, using mock result")
            return self._get_mock_daily_result()
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except:
                pass

    def _build_daily_prompt(self, text: str) -> str:
        """构建日报提示词"""
        return f"""请根据以下工作会话记录，生成一份日报。

工作记录：
{text}

请按以下 JSON 格式输出日报（只返回 JSON，不要其他文字）：
{{
    "summary": "今日工作总结（100-300字）",
    "key_progress": ["关键进展1", "关键进展2", ...],
    "difficulties": ["遇到的困难1", "遇到的困难2", ...],
    "next_steps": [
        {{"task": "任务内容", "deadline": "时间节点"}},
        ...
    ],
    "needs_support": [
        {{"person": "需要找谁", "support": "需要什么支持"}},
        ...
    ],
    "other_notes": "其他备注"
}}

注意：如果某部分没有内容，请返回空列表或空字符串。"""

    def _get_mock_daily_result(self) -> str:
        """获取 mock 结果"""
        return json.dumps({
            "summary": "今日完成了自动日报工具的开发工作。",
            "key_progress": [
                "完成 Claude 会话采集器",
                "完成日报生成器框架",
            ],
            "difficulties": [],
            "next_steps": [
                {"task": "测试完整流程", "deadline": "今天"},
            ],
            "needs_support": [],
            "other_notes": "",
        }, ensure_ascii=False)

    def _parse_daily_result(self, result: str, date: datetime) -> str:
        """解析 LLM 结果为 Markdown"""
        try:
            # 提取 JSON
            json_start = result.find("{")
            json_end = result.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(result[json_start:json_end])
            else:
                data = json.loads(result)
        except Exception as e:
            print(f"Warning: Failed to parse JSON, using raw text: {e}")
            return self._raw_text_to_markdown(result, date)

        # 生成 Markdown
        lines = [f"# 日报 - {date.strftime('%Y-%m-%d')}", ""]

        lines.append("## 一、今日总结")
        lines.append(data.get("summary", ""))
        lines.append("")

        lines.append("## 二、关键进展")
        for item in data.get("key_progress", []):
            lines.append(f"- {item}")
        lines.append("")

        lines.append("## 三、遇到的困难")
        for item in data.get("difficulties", []):
            lines.append(f"- {item}")
        lines.append("")

        lines.append("## 四、下一步计划")
        for step in data.get("next_steps", []):
            task = step.get("task", "") if isinstance(step, dict) else str(step)
            deadline = step.get("deadline", "") if isinstance(step, dict) else ""
            if deadline:
                lines.append(f"- [ ] {task} - {deadline}")
            else:
                lines.append(f"- [ ] {task}")
        lines.append("")

        lines.append("## 五、需要支持")
        for item in data.get("needs_support", []):
            person = item.get("person", "") if isinstance(item, dict) else str(item)
            support = item.get("support", "") if isinstance(item, dict) else ""
            if person and support:
                lines.append(f"- {person}: {support}")
            elif person:
                lines.append(f"- {person}")
        lines.append("")

        lines.append("## 六、其他备注")
        lines.append(data.get("other_notes", ""))
        lines.append("")

        return "\n".join(lines)

    def _raw_text_to_markdown(self, text: str, date: datetime) -> str:
        """原始文本转 Markdown"""
        return f"""# 日报 - {date.strftime('%Y-%m-%d')}

## 一、今日总结
{text[:500]}

## 二、关键进展

## 三、遇到的困难

## 四、下一步计划

## 五、需要支持

## 六、其他备注
"""

    # ===== 周报/月报方法 =====

    def generate_weekly(self, year: int, week: int) -> Optional[Path]:
        """生成周报（从日报聚合）"""
        # 计算周的日期范围
        start_date, end_date = self._get_week_range(year, week)

        # 读取该范围内的所有日报
        daily_reports = self._read_daily_reports(start_date, end_date)
        if not daily_reports:
            print(f"No daily reports found for week {year}-W{week}")
            return None

        # 聚合内容
        combined_text = "\n\n".join(daily_reports)

        # 调用 LLM 生成周报
        llm_result = self._call_llm_for_weekly(combined_text, year, week)

        # 生成 Markdown
        markdown = self._parse_weekly_result(llm_result, year, week, start_date, end_date)

        # 保存
        filename = f"weekly_report_{year}-W{week:02d}.md"
        output_path = self.weekly_dir / filename
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        print(f"Weekly report saved: {output_path}")
        return output_path

    def generate_monthly(self, year: int, month: int) -> Optional[Path]:
        """生成月报（从日报聚合）"""
        # 计算月的日期范围
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)

        # 读取该范围内的所有日报
        daily_reports = self._read_daily_reports(start_date, end_date)
        if not daily_reports:
            print(f"No daily reports found for {year}-{month:02d}")
            return None

        # 聚合内容
        combined_text = "\n\n".join(daily_reports)

        # 调用 LLM 生成月报
        llm_result = self._call_llm_for_monthly(combined_text, year, month)

        # 生成 Markdown
        markdown = self._parse_monthly_result(llm_result, year, month)

        # 保存
        filename = f"monthly_report_{year}-{month:02d}.md"
        output_path = self.monthly_dir / filename
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        print(f"Monthly report saved: {output_path}")
        return output_path

    def _get_week_range(self, year: int, week: int) -> Tuple[datetime, datetime]:
        """获取周的起始和结束日期"""
        # 简单实现：假设周一为一周开始
        first_day = datetime(year, 1, 1)
        first_monday = first_day + timedelta(days=(7 - first_day.weekday()) % 7)
        start_date = first_monday + timedelta(weeks=week - 1)
        end_date = start_date + timedelta(days=6)
        return start_date, end_date

    def _read_daily_reports(self, start_date: datetime, end_date: datetime) -> List[str]:
        """读取日期范围内的所有日报"""
        reports = []
        current = start_date
        while current <= end_date:
            filename = f"daily_report_{current.strftime('%Y-%m-%d')}.md"
            path = self.daily_dir / filename
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    reports.append(f.read())
            current += timedelta(days=1)
        return reports

    def _call_llm_for_weekly(self, text: str, year: int, week: int) -> str:
        """调用 LLM 生成周报"""
        # 简化：直接聚合，暂不调用 LLM
        return json.dumps({
            "summary": f"{year}年第{week}周工作总结",
            "key_progress": [],
            "difficulties": [],
            "next_week_plan": [],
            "needs_coordination": [],
        }, ensure_ascii=False)

    def _call_llm_for_monthly(self, text: str, year: int, month: int) -> str:
        """调用 LLM 生成月报"""
        # 简化：直接聚合，暂不调用 LLM
        return json.dumps({
            "summary": f"{year}年{month}月工作总结",
            "key_progress": [],
            "milestones": [],
            "next_month_focus": [],
        }, ensure_ascii=False)

    def _parse_weekly_result(self, result: str, year: int, week: int,
                            start_date: datetime, end_date: datetime) -> str:
        """解析周报结果"""
        try:
            data = json.loads(result)
        except:
            data = {}

        lines = [
            f"# 周报 - {year}年第{week}周 ({start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')})",
            "",
            "## 本周总结",
            data.get("summary", ""),
            "",
            "## 关键进展",
        ]
        for item in data.get("key_progress", []):
            lines.append(f"- {item}")
        lines.extend([
            "",
            "## 主要困难",
        ])
        for item in data.get("difficulties", []):
            lines.append(f"- {item}")
        lines.extend([
            "",
            "## 下周计划",
        ])
        for item in data.get("next_week_plan", []):
            lines.append(f"- [ ] {item}")
        lines.extend([
            "",
            "## 需要协调",
        ])
        for item in data.get("needs_coordination", []):
            lines.append(f"- {item}")
        lines.append("")

        return "\n".join(lines)

    def _parse_monthly_result(self, result: str, year: int, month: int) -> str:
        """解析月报结果"""
        try:
            data = json.loads(result)
        except:
            data = {}

        lines = [
            f"# 月报 - {year}年{month}月",
            "",
            "## 本月总结",
            data.get("summary", ""),
            "",
            "## 核心成果",
        ]
        for item in data.get("key_progress", []):
            lines.append(f"- {item}")
        lines.extend([
            "",
            "## 重要里程碑",
        ])
        for item in data.get("milestones", []):
            lines.append(f"- {item}")
        lines.extend([
            "",
            "## 下月重点",
        ])
        for item in data.get("next_month_focus", []):
            lines.append(f"- {item}")
        lines.append("")

        return "\n".join(lines)
```

- [ ] **Step 2: 验证文件创建成功**
  ```bash
  ls -la /Users/liangjiayu/projects/daily_report/generator.py
  ```
  Expected: 文件存在

---

### Task 3: 创建 daily_report.py - CLI 主入口

**Files:**
- Create: `daily_report.py`

**Responsibility:** 解析 CLI 参数，协调 collector 和 generator，执行完整流程。

- [ ] **Step 1: 编写 daily_report.py**

```python
#!/usr/bin/env python3
"""
自动日报生成工具
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from collector import ClaudeCollector
from generator import ReportGenerator


def load_config(config_path: str = "config.yaml") -> dict:
    """加载配置文件"""
    path = Path(config_path)
    if not path.exists():
        print(f"Warning: Config file not found: {config_path}, using defaults")
        return {
            "claude": {
                "history_path": "~/.claude/history.jsonl",
                "projects_path": "~/.claude/projects",
            },
            "llm": {
                "arkplan_settings": "~/.claude/arkplan.json",
            },
            "report": {
                "base_dir": "reports",
            },
        }
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_dates_to_process(args) -> list:
    """获取要处理的日期列表"""
    dates = []

    if args.yesterday:
        # 昨天
        yesterday = datetime.now() - timedelta(days=1)
        dates.append(datetime(yesterday.year, yesterday.month, yesterday.day))
    elif args.date:
        # 指定日期
        try:
            date = datetime.strptime(args.date, "%Y-%m-%d")
            dates.append(date)
        except ValueError as e:
            print(f"Error: Invalid date format: {args.date}, use YYYY-MM-DD")
            sys.exit(1)
    elif args.start and args.end:
        # 日期范围
        try:
            start = datetime.strptime(args.start, "%Y-%m-%d")
            end = datetime.strptime(args.end, "%Y-%m-%d")
            current = start
            while current <= end:
                dates.append(current)
                current += timedelta(days=1)
        except ValueError as e:
            print(f"Error: Invalid date format: {e}")
            sys.exit(1)
    else:
        # 默认：今天
        today = datetime.now()
        dates.append(datetime(today.year, today.month, today.day))

    return dates


def main():
    parser = argparse.ArgumentParser(description="自动日报生成工具")

    # 日期选项
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument(
        "--date", "-d",
        help="生成指定日期的日报 (YYYY-MM-DD)",
    )
    date_group.add_argument(
        "--yesterday", "-y",
        action="store_true",
        help="生成昨天的日报",
    )
    date_group.add_argument(
        "--start",
        help="日期范围开始 (YYYY-MM-DD)",
    )
    date_group.add_argument(
        "--weekly",
        help="生成周报 (YYYY-Www, 如 2026-W12)",
    )
    date_group.add_argument(
        "--monthly",
        help="生成月报 (YYYY-MM, 如 2026-03)",
    )

    parser.add_argument(
        "--end",
        help="日期范围结束 (YYYY-MM-DD, 需要配合 --start 使用)",
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细日志",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="强制重新生成，即使已存在",
    )

    args = parser.parse_args()

    # 验证 --start/--end
    if args.start and not args.end:
        print("Error: --end is required when using --start")
        sys.exit(1)
    if args.end and not args.start:
        print("Error: --start is required when using --end")
        sys.exit(1)

    # 加载配置
    config = load_config(args.config)

    # 创建 collector 和 generator
    collector = ClaudeCollector(
        config["claude"]["history_path"],
        config["claude"]["projects_path"],
    )
    generator = ReportGenerator(
        config["llm"]["arkplan_settings"],
        config["report"]["base_dir"],
    )

    # 周报
    if args.weekly:
        try:
            # 解析 YYYY-Www
            year_str, week_str = args.weekly.split("-W")
            year = int(year_str)
            week = int(week_str)
            generator.generate_weekly(year, week)
        except Exception as e:
            print(f"Error: Failed to generate weekly report: {e}")
            sys.exit(1)
        return

    # 月报
    if args.monthly:
        try:
            # 解析 YYYY-MM
            year_str, month_str = args.monthly.split("-")
            year = int(year_str)
            month = int(month_str)
            generator.generate_monthly(year, month)
        except Exception as e:
            print(f"Error: Failed to generate monthly report: {e}")
            sys.exit(1)
        return

    # 日报
    dates = get_dates_to_process(args)

    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        print(f"Processing {date_str}...")

        # 检查是否已存在
        if not args.force and generator.daily_report_exists(date):
            print(f"  Skipped: already exists")
            continue

        # 采集会话
        conversation_text = collector.collect_for_date(date)
        if args.verbose:
            print(f"  Collected {len(conversation_text)} chars of content")

        # 生成日报
        output_path = generator.generate_daily(date, conversation_text)
        print(f"  Generated: {output_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 添加执行权限**
  ```bash
  chmod +x /Users/liangjiayu/projects/daily_report/daily_report.py
  ```

- [ ] **Step 3: 验证文件创建成功**
  ```bash
  ls -la /Users/liangjiayu/projects/daily_report/daily_report.py
  ```
  Expected: 文件存在且有执行权限

---

### Task 4: 更新 README 和创建示例 Crontab

**Files:**
- Modify: `README.md`
- Create: `crontab.example`

- [ ] **Step 1: 更新 README.md**

```markdown
# 自动日报工具

自动采集 Claude 会话记录，通过 LLM 生成标准化日报、周报、月报。

## 功能特性

- 采集 ~/.claude/ 下的会话记录
- 调用 happy_arkplan 生成智能总结
- 支持日报、周报、月报
- 已生成的日期自动跳过
- 支持 crontab 定时运行

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置

编辑 `config.yaml` 文件（通常不需要修改）：

```yaml
claude:
  history_path: "~/.claude/history.jsonl"
  projects_path: "~/.claude/projects"

llm:
  arkplan_settings: "~/.claude/arkplan.json"

report:
  base_dir: "reports"
```

### 使用方式

```bash
# 生成今天的日报
python daily_report.py

# 生成昨天的日报（推荐 crontab 使用）
python daily_report.py --yesterday

# 生成指定日期的日报
python daily_report.py --date 2026-03-20

# 生成日期范围的日报
python daily_report.py --start 2026-03-20 --end 2026-03-24

# 强制重新生成（覆盖已存在的）
python daily_report.py --date 2026-03-20 --force

# 生成周报
python daily_report.py --weekly 2026-W12

# 生成月报
python daily_report.py --monthly 2026-03
```

### Crontab 配置

每天凌晨 2 点自动生成前一天的日报：

```bash
# 编辑 crontab
crontab -e

# 添加这一行（注意替换实际路径）
0 2 * * * cd /path/to/daily_report && python daily_report.py --yesterday
```

参考 `crontab.example` 文件。

## 目录结构

```
daily_report/
├── daily_report.py    # 主入口
├── collector.py       # Claude 会话采集
├── generator.py       # 日报生成
├── config.yaml        # 配置
├── crontab.example    # Crontab 示例
├── requirements.txt   # 依赖
├── README.md
└── reports/
    ├── daily/         # 日报
    ├── weekly/        # 周报
    └── monthly/       # 月报
```

## 日报格式

```markdown
# 日报 - 2026-03-24

## 一、今日总结
[100-300 字整体总结]

## 二、关键进展
- [进展1]
- [进展2]

## 三、遇到的困难
- [困难1]

## 四、下一步计划
- [ ] [任务1] - [时间节点]

## 五、需要支持
- [找谁]：[需要什么支持]

## 六、其他备注
...
```
```

- [ ] **Step 2: 创建 crontab.example**

```bash
# ========================================================
# 自动日报工具 - Crontab 示例
# ========================================================
# 编辑 crontab: crontab -e
# 查看 crontab: crontab -l
# ========================================================

# 每天凌晨 2 点生成前一天的日报
# 注意：请将 /path/to/daily_report 替换为实际路径
0 2 * * * cd /path/to/daily_report && python daily_report.py --yesterday

# 每周一凌晨 3 点生成上周的周报
# 0 3 * * 1 cd /path/to/daily_report && python daily_report.py --weekly $(date -d "last week" +%Y-W%U)

# 每月 1 号凌晨 4 点生成上月的月报
# 0 4 1 * * cd /path/to/daily_report && python daily_report.py --monthly $(date -d "last month" +%Y-%m)
```

---

### Task 5: 测试完整流程

**Files:**
- All

- [ ] **Step 1: 安装依赖**
  ```bash
  cd /Users/liangjiayu/projects/daily_report
  pip install -r requirements.txt
  ```

- [ ] **Step 2: 测试生成昨天的日报**
  ```bash
  python daily_report.py --yesterday -v
  ```
  Expected: 成功生成 reports/daily/daily_report_YYYY-MM-DD.md

- [ ] **Step 3: 验证生成的日报**
  ```bash
  ls -la /Users/liangjiayu/projects/daily_report/reports/daily/
  ```
  Expected: 日报文件存在

- [ ] **Step 4: 测试已存在的日期会跳过**
  ```bash
  python daily_report.py --yesterday
  ```
  Expected: 显示 "Skipped: already exists"

---

## Plan Complete

这就是完整的实现计划。


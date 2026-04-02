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

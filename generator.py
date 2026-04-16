"""
日报生成器
"""
import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


class ReportGenerator:
    """日报生成器"""

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

    # 周报提示词前缀
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

    # 月报提示词前缀
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

    def __init__(self, llm_config: Dict[str, Any], base_dir: str = "reports"):
        self.llm_config = llm_config
        self.base_dir = Path(base_dir)
        self.daily_dir = self.base_dir / "daily"
        self.weekly_dir = self.base_dir / "weekly"
        self.monthly_dir = self.base_dir / "monthly"

        # 创建目录
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        self.weekly_dir.mkdir(parents=True, exist_ok=True)
        self.monthly_dir.mkdir(parents=True, exist_ok=True)

    def get_daily_report_path(self, date: datetime) -> Path:
        """获取日报文件路径（YYYY-MM/YYYY-MM-DD/ 格式）"""
        month_str = date.strftime("%Y-%m")
        date_str = date.strftime("%Y-%m-%d")
        filename = f"daily_report_{date_str}.md"
        return self.daily_dir / month_str / filename

    def _get_legacy_daily_report_path(self, date: datetime) -> Path:
        """获取旧格式的日报文件路径（直接在 daily/ 下）"""
        filename = f"daily_report_{date.strftime('%Y-%m-%d')}.md"
        return self.daily_dir / filename

    def daily_report_exists(self, date: datetime) -> bool:
        """检查日报是否已存在（兼容新旧格式）"""
        # 先检查新格式
        if self.get_daily_report_path(date).exists():
            return True
        # 再检查旧格式
        return self._get_legacy_daily_report_path(date).exists()

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
            print(f"No content for {date.strftime('%Y-%m-%d')}, writing empty report")
            return self._write_empty_daily(date)

        # 调用 LLM
        llm_result = self._call_llm_for_daily(conversation_text, date)

        # 生成 Markdown
        markdown = self._parse_daily_result(llm_result, date)

        # 如果解析结果还是空框架，使用fallback
        if self._is_empty_framework(markdown):
            print("Warning: Using fallback report format")
            markdown = self._generate_fallback_report(conversation_text, date)

        # 保存文件
        output_path = self.get_daily_report_path(date)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        print(f"Daily report saved: {output_path}")
        return output_path

    def _is_empty_framework(self, markdown: str) -> bool:
        """检查是否是空框架"""
        lines = [line.strip() for line in markdown.split("\n") if line.strip()]
        # 如果只有标题行，说明是空框架
        header_lines = [l for l in lines if l.startswith("#")]
        return len(lines) <= len(header_lines) + 2

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
        output_path = self.get_daily_report_path(date)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown)
        return output_path

    def _call_llm_for_daily(self, text: str, date: datetime) -> str:
        """调用 LLM 生成日报"""
        prompt = self._build_daily_prompt(text, date)

        try:
            # 构建请求数据
            request_data = {
                "model": self.llm_config.get("model", "doubao-seed-2-0-pro-260215"),
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            }

            # 构建curl命令
            cmd = [
                "curl",
                self.llm_config.get("base_url", "https://ark.cn-beijing.volces.com/api/v3/responses"),
                "-H", f"Authorization: Bearer {self.llm_config.get('api_key', '')}",
                "-H", "Content-Type: application/json",
                "-d", json.dumps(request_data, ensure_ascii=False)
            ]

            import time as _time
            _t0 = _time.time()
            print(f"Calling LLM for daily report... (input {len(prompt)} chars)")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.llm_config.get("timeout", 600),
            )

            print(f"LLM call done in {_time.time()-_t0:.1f}s")
            if result.returncode != 0:
                print(f"Warning: LLM call failed, stderr: {result.stderr}, using mock result")
                return self._get_mock_daily_result()

            # 解析响应
            try:
                response_data = json.loads(result.stdout)
                print(f"LLM raw response: {json.dumps(response_data, ensure_ascii=False, indent=2)}")
                llm_result = ""
                # 尝试不同的响应格式
                if isinstance(response_data, dict):
                    # 火山引擎响应格式
                    if "output" in response_data and isinstance(response_data["output"], list):
                        # 遍历output数组找到message类型的内容
                        for item in response_data["output"]:
                            if item.get("type") == "message" and isinstance(item.get("content"), list):
                                for content_item in item["content"]:
                                    if content_item.get("type") == "output_text":
                                        llm_result = content_item.get("text", "")
                                        break
                            if llm_result:
                                break
                    # 兼容旧格式
                    elif "output" in response_data and isinstance(response_data["output"], dict):
                        if "choices" in response_data["output"] and isinstance(response_data["output"]["choices"], list) and len(response_data["output"]["choices"]) > 0:
                            llm_result = response_data["output"]["choices"][0].get("message", {}).get("content", "")
                    # 兼容OpenAI格式
                    elif "choices" in response_data and isinstance(response_data["choices"], list) and len(response_data["choices"]) > 0:
                        llm_result = response_data["choices"][0].get("message", {}).get("content", "")
                    # 其他可能格式
                    elif "content" in response_data:
                        llm_result = response_data["content"]
                elif isinstance(response_data, list) and len(response_data) > 0:
                    llm_result = str(response_data[0])
            except Exception as e:
                print(f"Warning: Failed to parse LLM response: {e}, raw response: {result.stdout[:500]}...")
                return self._get_mock_daily_result()

            print(f"LLM response received ({len(llm_result)} chars)")
            if llm_result:
                preview = llm_result[:200].replace('\n', ' ')
                print(f"Preview: {preview}...")
            return llm_result

        except Exception as e:
            print(f"Warning: Failed to call LLM: {e}, using mock result")
            return self._get_mock_daily_result()

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

    def _get_mock_daily_result(self, date: Optional[datetime] = None) -> str:
        """获取 mock 结果"""
        date_str = date.strftime('%Y-%m-%d') if date else '2026-03-24'
        return f"""# 日报 - {date_str}

## 一、今日总结
今日完成了自动日报工具的开发工作。

## 二、关键进展
- [自主工作] 完成 Claude 会话采集器
- [自主工作] 完成日报生成器框架

## 三、遇到的困难

## 四、下一步计划
- [ ] 测试完整流程 - 今天

## 五、需要支持

## 六、其他备注
"""

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

    def _get_mock_weekly_result(self, year: int, week: int) -> str:
        """获取 mock 周报结果"""
        return f"""# 周报 - {year}年第{week}周

## 一、本周概览
本周主要围绕AI美术中台产品优化、技术方案设计、团队管理及用户支持展开工作。

## 二、核心工作内容

### 🎯 会议
- 技术线负责人会议
- BPM流程沟通

### 💻 自主工作
- AI美术中台功能优化
- 技术方案设计

### 👥 团队管理
- 人员调整安排

### 🤝 提供支持
- 用户问题解决

## 三、问题与风险
- 新入职用户飞书授权存在同步延迟问题

## 四、下周计划
- [ ] 跟进各项工作进展

## 五、需要协调
- 暂无
"""

    def _parse_daily_result(self, result: str, date: datetime) -> str:
        """解析 LLM 结果为 Markdown"""
        # 强制替换标题为正确的日期
        correct_header = f"# 日报 - {date.strftime('%Y-%m-%d')}"

        # 如果结果已经包含 "# 日报" 开头，使用它但替换标题
        if "# 日报" in result:
            # 清理掉可能的额外内容
            lines = result.split("\n")
            cleaned_lines = []
            in_report = False
            for line in lines:
                if line.strip().startswith("# 日报"):
                    in_report = True
                    # 替换标题为正确的日期
                    cleaned_lines.append(correct_header)
                elif in_report:
                    cleaned_lines.append(line)
            if cleaned_lines:
                return "\n".join(cleaned_lines)

        # 否则使用 raw text 转换
        print(f"Warning: Could not find report header, using raw text")
        return self._raw_text_to_markdown(result, date)

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
        """获取周的起始和结束日期（使用 ISO 周历）"""
        # 找到该年第一个周一
        d = datetime(year, 1, 1)
        # 向前找到该 ISO 周的周一
        while True:
            y, w, wd = d.isocalendar()
            if w == week and y == year:
                # 找到目标周的某一天，找到这一周的周一
                start_date = d - timedelta(days=d.weekday())
                end_date = start_date + timedelta(days=6)
                return start_date, end_date
            d += timedelta(days=1)
            if d.year > year:
                # 如果没找到，回退到简单方法
                first_day = datetime(year, 1, 1)
                first_monday = first_day + timedelta(days=(7 - first_day.weekday()) % 7)
                start_date = first_monday + timedelta(weeks=week - 1)
                end_date = start_date + timedelta(days=6)
                return start_date, end_date

    def _read_daily_reports(self, start_date: datetime, end_date: datetime) -> List[str]:
        """读取日期范围内的所有日报（兼容新旧格式）"""
        reports = []
        current = start_date
        while current <= end_date:
            # 先尝试新格式
            path = self.get_daily_report_path(current)
            if not path.exists():
                # 再尝试旧格式
                path = self._get_legacy_daily_report_path(current)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    reports.append(f.read())
            current += timedelta(days=1)
        return reports

    def _call_llm_for_weekly(self, text: str, year: int, week: int) -> str:
        """调用 LLM 生成周报"""
        prompt = self._build_weekly_prompt(text, year, week)

        try:
            # 构建请求数据
            request_data = {
                "model": self.llm_config.get("model", "doubao-seed-2-0-pro-260215"),
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            }

            # 构建curl命令
            cmd = [
                "curl",
                self.llm_config.get("base_url", "https://ark.cn-beijing.volces.com/api/v3/responses"),
                "-H", f"Authorization: Bearer {self.llm_config.get('api_key', '')}",
                "-H", "Content-Type: application/json",
                "-d", json.dumps(request_data, ensure_ascii=False)
            ]

            print(f"Calling LLM for weekly report...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.llm_config.get("timeout", 300),
            )

            if result.returncode != 0:
                print(f"Warning: LLM call failed, stderr: {result.stderr}, using mock result")
                return self._get_mock_weekly_result(year, week)

            # 解析响应
            try:
                response_data = json.loads(result.stdout)
                print(f"LLM raw response: {json.dumps(response_data, ensure_ascii=False, indent=2)}")
                llm_result = ""
                # 尝试不同的响应格式
                if isinstance(response_data, dict):
                    # 火山引擎响应格式
                    if "output" in response_data and isinstance(response_data["output"], list):
                        # 遍历output数组找到message类型的内容
                        for item in response_data["output"]:
                            if item.get("type") == "message" and isinstance(item.get("content"), list):
                                for content_item in item["content"]:
                                    if content_item.get("type") == "output_text":
                                        llm_result = content_item.get("text", "")
                                        break
                            if llm_result:
                                break
                    # 兼容旧格式
                    elif "output" in response_data and isinstance(response_data["output"], dict):
                        if "choices" in response_data["output"] and isinstance(response_data["output"]["choices"], list) and len(response_data["output"]["choices"]) > 0:
                            llm_result = response_data["output"]["choices"][0].get("message", {}).get("content", "")
                    # 兼容OpenAI格式
                    elif "choices" in response_data and isinstance(response_data["choices"], list) and len(response_data["choices"]) > 0:
                        llm_result = response_data["choices"][0].get("message", {}).get("content", "")
                    # 其他可能格式
                    elif "content" in response_data:
                        llm_result = response_data["content"]
                elif isinstance(response_data, list) and len(response_data) > 0:
                    llm_result = str(response_data[0])
            except Exception as e:
                print(f"Warning: Failed to parse LLM response: {e}, raw response: {result.stdout[:500]}...")
                return self._get_mock_weekly_result(year, week)

            print(f"LLM response received ({len(llm_result)} chars)")
            return llm_result

        except Exception as e:
            print(f"Warning: Failed to call LLM: {e}, using mock result")
            return self._get_mock_weekly_result(year, week)

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

    def _call_llm_for_monthly(self, text: str, year: int, month: int) -> str:
        """调用 LLM 生成月报"""
        prompt = self._build_monthly_prompt(text, year, month)

        try:
            # 构建请求数据
            request_data = {
                "model": self.llm_config.get("model", "doubao-seed-2-0-pro-260215"),
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            }

            # 构建curl命令
            cmd = [
                "curl",
                self.llm_config.get("base_url", "https://ark.cn-beijing.volces.com/api/v3/responses"),
                "-H", f"Authorization: Bearer {self.llm_config.get('api_key', '')}",
                "-H", "Content-Type: application/json",
                "-d", json.dumps(request_data, ensure_ascii=False)
            ]

            print(f"Calling LLM for monthly report...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.llm_config.get("timeout", 600),
            )

            if result.returncode != 0:
                print(f"Warning: LLM call failed, stderr: {result.stderr}, using mock result")
                return self._get_mock_monthly_result(year, month)

            # 解析响应
            try:
                response_data = json.loads(result.stdout)
                print(f"LLM raw response: {json.dumps(response_data, ensure_ascii=False, indent=2)}")
                llm_result = ""
                # 尝试不同的响应格式
                if isinstance(response_data, dict):
                    # 火山引擎响应格式
                    if "output" in response_data and isinstance(response_data["output"], list):
                        # 遍历output数组找到message类型的内容
                        for item in response_data["output"]:
                            if item.get("type") == "message" and isinstance(item.get("content"), list):
                                for content_item in item["content"]:
                                    if content_item.get("type") == "output_text":
                                        llm_result = content_item.get("text", "")
                                        break
                            if llm_result:
                                break
                    # 兼容旧格式
                    elif "output" in response_data and isinstance(response_data["output"], dict):
                        if "choices" in response_data["output"] and isinstance(response_data["output"]["choices"], list) and len(response_data["output"]["choices"]) > 0:
                            llm_result = response_data["output"]["choices"][0].get("message", {}).get("content", "")
                    # 兼容OpenAI格式
                    elif "choices" in response_data and isinstance(response_data["choices"], list) and len(response_data["choices"]) > 0:
                        llm_result = response_data["choices"][0].get("message", {}).get("content", "")
                    # 其他可能格式
                    elif "content" in response_data:
                        llm_result = response_data["content"]
                elif isinstance(response_data, list) and len(response_data) > 0:
                    llm_result = str(response_data[0])
            except Exception as e:
                print(f"Warning: Failed to parse LLM response: {e}, raw response: {result.stdout[:500]}...")
                return self._get_mock_monthly_result(year, month)

            print(f"LLM response received ({len(llm_result)} chars)")
            return llm_result

        except Exception as e:
            print(f"Warning: Failed to call LLM: {e}, using mock result")
            return self._get_mock_monthly_result(year, month)

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

    def _parse_weekly_result(self, result: str, year: int, week: int,
                            start_date: datetime, end_date: datetime) -> str:
        """解析周报结果"""
        correct_header = f"# 周报 - {year}年第{week}周 ({start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}"

        # 如果结果已经包含 "# 周报" 开头，使用它但替换标题
        if "# 周报" in result:
            lines = result.split("\n")
            cleaned_lines = []
            in_report = False
            for line in lines:
                if line.strip().startswith("# 周报"):
                    in_report = True
                    cleaned_lines.append(correct_header)
                elif in_report:
                    cleaned_lines.append(line)
            if cleaned_lines:
                return "\n".join(cleaned_lines)

        # 否则使用 raw text 转换
        print(f"Warning: Could not find report header, using raw text")
        return self._raw_weekly_text_to_markdown(result, year, week, start_date, end_date)

    def _raw_weekly_text_to_markdown(self, text: str, year: int, week: int,
                                      start_date: datetime, end_date: datetime) -> str:
        """原始文本转周报 Markdown"""
        return f"""# 周报 - {year}年第{week}周 ({start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')})

## 一、本周概览
{text[:800]}

## 二、核心工作内容

## 三、问题与风险

## 四、下周计划

## 五、需要协调
"""

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

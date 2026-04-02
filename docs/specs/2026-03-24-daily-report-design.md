# 自动日报工具设计文档

**日期:** 2026-03-24
**作者:** AI Assistant
**状态:** 待审核

## 概述

一个简单的多文件脚本，通过 crontab 定时运行，自动采集 Claude 会话记录，调用 LLM 生成日报、周报、月报。

## 目标

- 每天凌晨 2 点自动生成前一天的日报
- 支持按日期范围批量生成
- 支持从日报聚合生成周报/月报
- 已生成的日期自动跳过
- 简单、独立、不依赖复杂框架

## 非目标

- 不做插件化架构（当前阶段）
- 不做飞书集成（当前阶段）
- 不做人员分类（当前阶段）

---

## 文件结构

```
daily_report/
├── daily_report.py    # 主入口 + CLI 参数解析
├── collector.py       # Claude 会话采集
├── generator.py       # LLM 调用 + 日报/周报/月报生成
├── config.yaml        # 配置文件
└── reports/
    ├── daily/         # 日报: daily_report_YYYY-MM-DD.md
    ├── weekly/        # 周报: weekly_report_YYYY-Www.md
    └── monthly/       # 月报: monthly_report_YYYY-MM.md
```

---

## 核心流程

### 日报生成流程

```
1. 解析 CLI 参数，确定要生成的日期
   ├─ 默认：今天
   ├─ --date YYYY-MM-DD：指定日期
   ├─ --yesterday：昨天
   └─ --start / --end：日期范围

2. 对每个日期：
   a. 检查 reports/daily/daily_report_YYYY-MM-DD.md 是否存在
   b. 存在 → 跳过
   c. 不存在 → 继续

3. 采集该日期的 Claude 会话：
   a. 读取 ~/.claude/history.jsonl
   b. 读取 ~/.claude/projects/*/*.jsonl
   c. 筛选该日期 00:00:00 ~ 23:59:59 的会话

4. 构建提示词，写入临时文件

5. 调用 happy 命令：
   happy --settings ~/.claude/arkplan.json -p <temp_file>

6. 解析 LLM 输出，生成 Markdown 格式日报

7. 保存到 reports/daily/daily_report_YYYY-MM-DD.md
```

### 周报/月报生成流程

```
1. 解析 CLI 参数，确定周期
   ├─ --weekly YYYY-Www：指定周（如 2026-W12）
   └─ --monthly YYYY-MM：指定月（如 2026-03）

2. 确定该周期包含的日期范围

3. 读取该范围内所有日报文件

4. 聚合所有日报内容

5. 调用 LLM 生成周报/月报总结

6. 保存到 reports/weekly/ 或 reports/monthly/
```

---

## 数据格式

### Claude 会话数据来源

**1. ~/.claude/history.jsonl**
- 每行一个 JSON 对象
- 字段：
  - `display`: 用户输入内容
  - `timestamp`: 时间戳（毫秒）
  - `project`: 项目路径
  - `sessionId`: 会话 ID（可选）
  - `pastedContents`: 粘贴内容（可选）

**2. ~/.claude/projects/{project_dir}/{sessionId}.jsonl**
- 完整对话记录（包含 AI 回复）

### 日报格式

```markdown
# 日报 - 2026-03-24

## 一、今日总结
[100-300 字整体工作内容总结]

## 二、关键进展
- [关键进展 1]
- [关键进展 2]
- ...

## 三、遇到的困难
- [困难 1]
- [困难 2]
- ...

## 四、下一步计划
- [ ] [任务 1] - [时间节点]
- [ ] [任务 2] - [时间节点]
- ...

## 五、需要支持
- [需要找谁]：[需要什么支持]
- ...

## 六、其他备注
[其他需要记录的内容]
```

### 周报格式

```markdown
# 周报 - 2026年第12周 (2026-03-18 ~ 2026-03-24)

## 本周总结
[整体工作总结]

## 关键进展
- [关键进展 1]
- [关键进展 2]
- ...

## 主要困难
- [困难 1]
- ...

## 下周计划
- [ ] [计划 1]
- ...

## 需要协调
- [协调事项 1]
- ...
```

### 月报格式

```markdown
# 月报 - 2026年3月

## 本月总结
[整体工作总结]

## 核心成果
- [成果 1]
- ...

## 重要里程碑
- [里程碑 1]
- ...

## 下月重点
- [重点 1]
- ...
```

---

## CLI 参数

| 参数 | 说明 | 示例 |
|------|------|------|
| (无) | 生成今天的日报 | `python daily_report.py` |
| `--date YYYY-MM-DD` | 生成指定日期的日报 | `--date 2026-03-20` |
| `--yesterday` | 生成昨天的日报 | `--yesterday` |
| `--start YYYY-MM-DD` | 日期范围开始 | `--start 2026-03-20` |
| `--end YYYY-MM-DD` | 日期范围结束 | `--end 2026-03-24` |
| `--weekly YYYY-Www` | 生成周报 | `--weekly 2026-W12` |
| `--monthly YYYY-MM` | 生成月报 | `--monthly 2026-03` |
| `--config FILE` | 配置文件路径 | `--config myconfig.yaml` |
| `-v`, `--verbose` | 详细日志 | `-v` |

---

## 配置文件 (config.yaml)

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

---

## LLM 提示词

### 日报生成提示词

```
请根据以下工作会话记录，生成一份日报。

工作记录：
{会话内容}

请按以下 JSON 格式输出（只返回 JSON，不要其他文字）：
{
    "summary": "今日工作总结（100-300字）",
    "key_progress": ["关键进展1", "关键进展2", ...],
    "difficulties": ["遇到的困难1", "遇到的困难2", ...],
    "next_steps": [
        {"task": "任务内容", "deadline": "时间节点"},
        ...
    ],
    "needs_support": [
        {"person": "需要找谁", "support": "需要什么支持"},
        ...
    ],
    "other_notes": "其他备注"
}

注意：如果某部分没有内容，请返回空列表或空字符串。
```

### 周报生成提示词

```
请根据以下日报内容，生成一份周报。

日报内容：
{所有日报聚合内容}

请按以下 JSON 格式输出：
{
    "summary": "本周总结",
    "key_progress": ["关键进展1", ...],
    "difficulties": ["主要困难1", ...],
    "next_week_plan": ["下周计划1", ...],
    "needs_coordination": ["需要协调1", ...]
}
```

---

## Crontab 配置

```bash
# 每天凌晨 2 点生成前一天的日报
0 2 * * * cd /path/to/daily_report && python daily_report.py --yesterday
```

---

## 模块职责

### daily_report.py
- CLI 参数解析
- 流程调度
- 调用 collector 和 generator

### collector.py
- 读取 ~/.claude/history.jsonl
- 读取 ~/.claude/projects/*/*.jsonl
- 按日期筛选会话
- 返回会话文本

### generator.py
- 构建提示词
- 调用 happy 命令行
- 解析 LLM 输出
- 生成 Markdown 日报/周报/月报
- 保存文件

---

## 错误处理

- 文件不存在 → 记录 warning，继续
- LLM 调用失败 → 记录 error，跳过该日期
- JSON 解析失败 → 使用备用模板或记录原始输出
- 日期范围无效 → 提示错误

---

## 验收标准

1. [ ] 能成功采集 Claude 会话
2. [ ] 能调用 happy 生成日报
3. [ ] 已生成的日期自动跳过
4. [ ] 支持 --date、--yesterday、--start/--end
5. [ ] 支持周报/月报从日报聚合
6. [ ] crontab 能正常运行
7. [ ] 生成的日报格式符合规范


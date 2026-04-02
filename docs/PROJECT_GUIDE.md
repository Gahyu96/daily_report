# 项目规范指南

## 目录结构

```
daily_report/
├── .claude/              # Claude Code 项目配置（不提交）
├── docs/                 # 文档目录
│   ├── specs/           # 设计文档
│   ├── plans/           # 实现计划
│   └── PROJECT_GUIDE.md # 本文件
├── reports/              # 生成的日报（不提交）
│   ├── daily/
│   ├── weekly/
│   └── monthly/
├── daily_report.py       # 主入口
├── collector.py          # Claude 会话采集
├── generator.py          # 日报生成
├── config.yaml           # 配置文件
├── crontab.example       # Crontab 示例
├── requirements.txt      # 依赖
├── .gitignore           # Git 忽略规则
└── README.md            # 项目说明
```

## 文档规范

### 设计文档 (docs/specs/)

- 命名格式：`YYYY-MM-DD-<feature-name>-design.md`
- 内容：需求分析、架构设计、接口定义、验收标准

### 实现计划 (docs/plans/)

- 命名格式：`YYYY-MM-DD-<feature-name>-implementation.md`
- 内容：分步实现计划、代码示例、测试步骤

## 日报生成优化说明

### Prompt 优化点

1. **工作类型区分**
   - 「自主工作」：自己主导的设计、开发、决策
   - 「下属支持」：帮助下属、review 代码、指导下属
   - 每个关键进展标注类型：`[自主工作] xxx` 或 `[下属支持] xxx`

2. **任务完成状态判断**
   - 仔细阅读所有会话，判断任务是否已完成
   - 关键词："完成了"、"已解决"、"搞定了" → 已完成
   - 已完成的任务不放入「下一步计划」

3. **下一步计划**
   - 只放真正未完成的工作
   - 每个任务要有明确的时间节点

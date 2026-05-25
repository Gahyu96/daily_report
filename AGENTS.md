# AGENTS.md - 全身份通用配置

## 工作模式

### 人工模式（需要设计决策时）
Superpowers 主导：brainstorming（HARD-GATE）→ 领域技能 → writing-plans → 执行 → verification

### AI 自主模式（标准明确时）
标准路径：/ralph-loop "<completion-promise prompt>" --max-iterations <n> --completion-promise "DONE"
进阶路径（多组件/有依赖）：autonomous-loops skill → Ralphinho/RFC-DAG
参考：docs/sop/v2/09-插件技能组合详解.md（Loop 模式选择）

## 插件优先级
1. 用户明确要求 — 最高
2. superpowers（纪律骨架）— 次之
3. marketing-skills / c-level-skills — 领域补充
4. 默认系统行为 — 最低

## 身份识别

任务涉及 → 对应工具链：
- 产品规划/PRD/OKR → brainstorming + cpo-advisor
- 策略/回测/量化 → brainstorming + TDD + ralph-loop
- 文章/文案/SEO → brainstorming + marketing-ops
- 企业咨询/方案 → brainstorming + chief-of-staff
- Agent/MCP/工具 → brainstorming + agentic-engineering
- 融资/BP/投资人 → brainstorming + investor-materials

## 初始化
- marketing-context（marketing-skills）
- /cs:setup（c-level-skills）

## planning-with-files-zh
- 复杂任务前先创建 task_plan.md、findings.md、progress.md
- 触发词：任务规划、项目计划、制定计划、分解任务、多步骤规划

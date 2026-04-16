# 日报增强功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有日报结构中新增三个章节（今日金句、决策逻辑与SOP方法论、行业资讯）

**Architecture:** 修改 generator.py 中的 prompt 前缀、输出模板、fallback 模板、空报告模板和 mock 结果

**Tech Stack:** Python 3.x

---

## 文件映射

| 文件 | 操作 | 说明 |
|------|------|------|
| `generator.py:17-67` | 修改 | 更新 `DAILY_PROMPT_PREFIX`，新增分析要求 |
| `generator.py:340-446` | 修改 | 更新 `_build_daily_prompt()` 输出模板 |
| `generator.py:193-226` | 修改 | 更新 `_generate_fallback_report()` 模板 |
| `generator.py:228-249` | 修改 | 更新 `_write_empty_daily()` 模板 |
| `generator.py:448-468` | 修改 | 更新 `_get_mock_daily_result()` 模板 |

---

## 任务分解

### Task 1: 更新 DAILY_PROMPT_PREFIX

**Files:**
- Modify: `generator.py:17-67`

- [ ] **Step 1: 读取当前 DAILY_PROMPT_PREFIX**

确认当前内容位置在第 17-67 行

- [ ] **Step 2: 在 DAILY_PROMPT_PREFIX 末尾（第 67 行之前）新增分析要求**

在 `---` 之前添加：

```
【重要：知识沉淀说明】
请从今日工作内容中额外提取以下知识沉淀内容（如无合适内容可省略相关章节）：

1. 今日金句：
   - 从今日工作中提炼 1-2 句最有启发性的话
   - 可以是会议中的精彩发言、自己的感悟、或从文档中读到的关键点
   - 格式：用引用块 `>` 呈现，注明来源

2. 决策逻辑：
   - 记录今天做过的重要决策
   - 用"背景-选项-结论"三段式呈现
   - 背景：为什么需要做这个决策
   - 选项：考虑过哪些方案
   - 结论：最终选择及核心理由

3. SOP沉淀：
   - 如果今天摸索出了可复用的工作流程，总结成标准化操作步骤
   - 包含：适用场景、操作步骤、注意事项

4. 行业资讯：
   - 如果今天关注到行业动态、技术趋势、竞品信息，记录下来
   - 包含：核心要点、对我的影响/启发
```

- [ ] **Step 3: 验证修改**

确认新增内容已正确插入，格式正确

---

### Task 2: 更新 _build_daily_prompt() 输出模板

**Files:**
- Modify: `generator.py:385-446`

- [ ] **Step 1: 定位当前模板结束位置**

找到"六、其他备注"章节和"附录：数据源索引"之间的位置（约第 435-439 行）

- [ ] **Step 2: 在"六、其他备注"之后、"---"之前插入新章节模板**

当前内容：
```
## 六、其他备注
【可能计划执行】的任务列表（如无则省略）

---

## 附录：数据源索引
```

修改为：
```
## 六、其他备注
【可能计划执行】的任务列表（如无则省略）

## 七、今日金句
> [1-2句有启发性的话，来自今日工作中的感悟、会议中的发言、或读过的资料]
> 来源: [相关来源]

## 八、决策逻辑与SOP方法论

### 决策逻辑
- [决策1名称]
  - 背景: [为什么需要做这个决策]
  - 选项: [考虑过哪些方案]
  - 结论: [最终选择及核心理由]
  - 来源: [相关来源]

### SOP沉淀
- [SOP名称]
  - 适用场景: [什么时候用这个SOP]
  - 操作步骤: [1/2/3...]
  - 注意事项: [关键风险或避坑点]
  - 来源: [相关来源]

## 九、行业资讯
- [资讯标题]
  - 核心要点: [2-3个关键信息]
  - 对我的影响/启发: [这个资讯与我工作的关联]
  - 来源: [相关来源]

---

## 附录：数据源索引
```

- [ ] **Step 3: 验证修改**

确认新章节模板已正确插入，Markdown 格式正确

---

### Task 3: 更新 _generate_fallback_report() 模板

**Files:**
- Modify: `generator.py:193-226`

- [ ] **Step 1: 定位当前 fallback 模板**

找到 `_generate_fallback_report()` 方法中的 Markdown 模板（第 201-226 行）

- [ ] **Step 2: 在"六、其他备注"之后、"---"之前插入新章节框架**

当前内容：
```
## 六、其他备注

---

## 附录：数据源索引
```

修改为：
```
## 六、其他备注

## 七、今日金句

## 八、决策逻辑与SOP方法论

## 九、行业资讯

---

## 附录：数据源索引
```

- [ ] **Step 3: 验证修改**

确认新章节框架已正确插入

---

### Task 4: 更新 _write_empty_daily() 模板

**Files:**
- Modify: `generator.py:228-249`

- [ ] **Step 1: 定位当前空日报模板**

找到 `_write_empty_daily()` 方法中的 Markdown 模板（第 230-244 行）

- [ ] **Step 2: 在"六、其他备注"之后添加新章节框架**

当前内容：
```
## 六、其他备注
```

修改为：
```
## 六、其他备注

## 七、今日金句

## 八、决策逻辑与SOP方法论

## 九、行业资讯
```

- [ ] **Step 3: 验证修改**

确认新章节框架已正确插入

---

### Task 5: 更新 _get_mock_daily_result() 模板

**Files:**
- Modify: `generator.py:448-468`

- [ ] **Step 1: 定位当前 mock 模板**

找到 `_get_mock_daily_result()` 方法中的 Markdown 模板（第 451-468 行）

- [ ] **Step 2: 在"六、其他备注"之后添加新章节示例**

当前内容：
```
## 六、其他备注
```

修改为：
```
## 六、其他备注

## 七、今日金句
> 今天的工作让我深刻体会到：好的设计是把复杂的事情变简单，而不是把简单的事情变复杂。
> 来源: Claude 项目会话

## 八、决策逻辑与SOP方法论

### 决策逻辑
- 选择 prompt 增强方案
  - 背景: 需要在日报中新增知识沉淀内容
  - 选项: A) 修改所有报告类型；B) 仅修改日报；C) 创建新的报告类型
  - 结论: 选择 B，仅修改日报，因为需求明确针对日报，且影响范围可控
  - 来源: 自主工作

### SOP沉淀
- 日报 prompt 更新 SOP
  - 适用场景: 需要修改日报输出格式时
  - 操作步骤: 1. 更新 DAILY_PROMPT_PREFIX；2. 更新 _build_daily_prompt() 模板；3. 更新 fallback 和空报告模板；4. 更新 mock 结果
  - 注意事项: 保持所有模板的一致性，避免章节编号错乱
  - 来源: 自主工作

## 九、行业资讯
- AI 模型 prompt 工程最佳实践更新
  - 核心要点: 1. 明确的角色设定；2. 具体的输出格式要求；3. 分步骤的思考引导
  - 对我的影响/启发: 可以将这些最佳实践应用到日报生成的 prompt 中，提升输出质量
  - 来源: Claude 历史会话
```

- [ ] **Step 3: 验证修改**

确认新章节示例已正确插入，Markdown 格式正确

---

### Task 6: 验证并提交

**Files:**
- Test: `generator.py`

- [ ] **Step 1: 检查语法错误**

Run: `python3 -m py_compile generator.py`
Expected: 无输出（表示编译成功）

- [ ] **Step 2: 查看 git diff**

Run: `git diff generator.py`
Expected: 只修改了预期的位置，无意外变更

- [ ] **Step 3: 提交代码**

```bash
git add generator.py docs/superpowers/specs/2026-04-16-daily-report-enhancements-design.md docs/superpowers/plans/2026-04-16-daily-report-enhancements.md
git commit -m "feat: 增强日报，新增金句、决策逻辑与SOP、行业资讯章节

- 更新 DAILY_PROMPT_PREFIX，新增知识沉淀分析要求
- 更新 _build_daily_prompt() 输出模板，新增三个章节
- 更新 fallback、空报告、mock 模板保持一致"
```

---

## 验证检查清单

- [ ] Spec 覆盖检查
  - [ ] 今日金句章节 → Task 1 + Task 2
  - [ ] 决策逻辑与SOP方法论章节 → Task 1 + Task 2
  - [ ] 行业资讯章节 → Task 1 + Task 2
  - [ ] Fallback 兼容 → Task 3
  - [ ] 空报告模板 → Task 4
  - [ ] Mock 数据 → Task 5

- [ ] Placeholder 扫描
  - [ ] 所有代码块都是完整可执行的
  - [ ] 所有文件路径都是准确的
  - [ ] 所有命令都有预期输出

- [ ] 一致性检查
  - [ ] 所有模板中的章节编号一致（七、八、九）
  - [ ] 章节顺序一致（金句 → 决策逻辑与SOP → 行业资讯）
  - [ ] Markdown 格式一致

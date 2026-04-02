# 日报系统优化设计文档

**日期**: 2026-03-25
**版本**: v1.0
**状态**: 设计中

## 概述

本次优化解决日报系统的以下问题：

1. Claude 会话记录采集后未有效总结到日报
2. 日报内容未总结，仅以附录形式呈现原始内容
3. 缺少内容类型分类（会议/自主工作/团队管理/提供支持）
4. 机器人 JSON 内容被截断
5. 缺少按来源分离的缓存机制

## 目标

- ✅ 所有来源内容都经过总结，不再有原始内容附录
- ✅ 按内容类型分类呈现
- ✅ 每个总结点标注真实来源
- ✅ 完善的缓存机制
- ✅ JSON 内容不截断，长会话取最后部分

## 目录结构

```
daily_report/
├── cache/                          # 新增：缓存目录
│   └── 2026-03-25/               # 按日期分子目录
│       ├── claude_history.md
│       ├── claude_projects.md
│       ├── feishu_chats.md
│       └── feishu_docs.md
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-03-25-daily-report-optimization-design.md
├── cache_manager.py                # 新增：缓存管理模块
├── collector.py                    # 改造：返回结构化数据
├── generator.py                    # 改造：新提示词 + 新结构
├── feishu/
│   └── collector.py                # 增强：智能纪要识别
└── daily_report.py                 # 改造：集成缓存
```

## 模块设计

### 1. CacheManager (cache_manager.py)

缓存管理模块，负责按日期和来源组织缓存。

**接口定义**:

```python
from pathlib import Path
from datetime import datetime
from typing import Optional

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

    def write_cache(self, date: datetime, source: str, content: str, metadata: Optional[dict] = None):
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

**缓存文件格式**:

```markdown
=== 元数据 ===
采集时间: 2026-03-25 10:30:00
来源: claude_history
条数: 15

=== 内容 ===
[原始采集内容]
```

### 2. ClaudeCollector 改造 (collector.py)

保持向后兼容，新增结构化采集方法。

**新增方法**:

```python
class ClaudeCollector:
    # 现有方法保持不变

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

### 3. FeishuCollector 增强 (feishu/collector.py)

增强智能纪要识别和文档采集。

**新增/修改逻辑**:

1. 从飞书会话消息中提取文档链接
2. 识别标题包含"智能纪要"、"会议纪要"、"纪要"的文档
3. 优先导出这些文档
4. 返回结构化数据

### 4. ReportGenerator 改造 (generator.py)

#### 新的日报输出结构

```markdown
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
[可能计划执行的任务、其他观察]

---

## 附录：数据源索引
- Claude 历史会话: N 条消息
- Claude 项目会话: N 个会话
- 飞书会话: N 个
- 飞书文档: N 个（含智能纪要 M 个）
```

#### 提示词修改要点

1. 移除「附录：原始工作记录」相关要求
2. 新增：按 4 种类型分类输出（会议/自主工作/团队管理/提供支持）
3. 新增：每个要点标注来源
4. 新增：飞书智能纪要优先作为会议内容
5. 明确：Claude history 和 projects 都是重要来源，飞书聊天记录也是重要来源
6. 明确：不要附录原始内容，全部经过总结

### 5. daily_report.py 主流程改造

**修改 collect_all_sources**:

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
        metadata = {"条数": str(content.count("\n--- 会话:")) if content else "0"}
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
        metadata = {"条数": str(content.count("\n--- 会话:")) if content else "0"}
        cache_mgr.write_cache(date, source, content, metadata)
    else:
        content = cache_mgr.read_cache(date, source) or ""
    structured_data[source] = content
    if content:
        parts.append("=== Claude 项目会话 ===\n" + content)

    # 3. 飞书集成
    if config.get("feishu", {}).get("enabled", False) and validate_feishu_config(config):
        feishu_data = collect_feishu_structured(date, config, cache_mgr, force)
        structured_data.update(feishu_data)
        if feishu_data.get("feishu_chats"):
            parts.append("=== 飞书会话 ===\n" + feishu_data["feishu_chats"])
        if feishu_data.get("feishu_docs"):
            parts.append("=== 飞书文档 ===\n" + feishu_data["feishu_docs"])

    # 4. 继承任务
    inheritance_mgr = TaskInheritanceManager(config["report"]["base_dir"])
    yesterday = date - timedelta(days=1)
    inherited_tasks = inheritance_mgr.get_incomplete_tasks_from_daily(yesterday)
    if inherited_tasks:
        tasks_text = inheritance_mgr._format_tasks_for_prompt(inherited_tasks)
        parts.append(tasks_text)

    combined_text = "\n\n".join(parts)
    return combined_text, structured_data


def collect_feishu_structured(
    date: datetime,
    config: dict,
    cache_mgr: CacheManager,
    force: bool = False
) -> Dict[str, str]:
    """收集飞书结构化数据"""
    result = {}
    feishu_config = config.get("feishu", {})

    # 认证、采集逻辑保持不变
    # ... 省略具体实现 ...

    # 分别缓存 feishu_chats 和 feishu_docs
    # ...

    return result
```

## 改造步骤

### Step 1: 新建 cache_manager.py
- 实现 CacheManager 类
- 实现缓存读写接口

### Step 2: 改造 collector.py
- 新增 collect_structured() 方法
- 新增 collect_history_for_date() 和 collect_projects_for_date()
- 新增 _truncate_long_content() 方法

### Step 3: 增强 feishu/collector.py
- 增强智能纪要识别
- 优先导出"智能纪要"文档

### Step 4: 重写 generator.py 提示词
- 更新 DAILY_PROMPT_PREFIX
- 更新 _build_daily_prompt()
- 移除 fallback 中的附录
- 更新 _generate_fallback_report()

### Step 5: 改造 daily_report.py
- 集成 CacheManager
- 修改 collect_all_sources() 返回结构化数据
- 新增 collect_feishu_structured()

### Step 6: 测试完整流程
- 测试缓存机制
- 测试新的日报结构
- 验证内容总结效果

## 注意事项

1. **文件大小限制**: 每个文件不超过 1300 行，必要时拆分
2. **向后兼容**: 保持现有接口不变，只新增方法
3. **JSON 处理**: 机器人 JSON 完整保留，不截断
4. **长会话处理**: Claude projects 会话过长时取最后部分
5. **来源标注**: 每个总结点都要标注清楚来源

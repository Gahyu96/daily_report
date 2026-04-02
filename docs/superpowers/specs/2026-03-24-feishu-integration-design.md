# 飞书集成设计文档

**日期**: 2026-03-24
**项目**: daily_report
**状态**: 待审核

## 概述

在现有的 daily_report 项目基础上，集成飞书聊天记录和文档采集功能，同时添加未完成任务继承机制。

## 目标

1. 采集飞书聊天记录（群聊 + 私聊）并缓存到本地
2. 通过 LLM 过滤闲聊，提取工作相关内容
3. 导出飞书文档内容（聊天中提到的 + 最近访问的）
4. 继承前一天/周/月未完成的任务
5. 自动管理飞书 OAuth token，支持自动刷新

## 现有代码说明

项目已存在以下核心文件（可参考）：
- `generator.py`: 日报生成器，包含 `_build_daily_prompt` 方法用于构建 LLM 提示词
- `collector.py`: Claude 会话采集器
- `daily_report.py`: 主入口，包含 `load_config` 配置加载函数

## 架构设计

### 目录结构

```
daily_report/
├── feishu/                    # 飞书模块目录
│   ├── __init__.py
│   ├── __main__.py            # 模块入口，支持 python -m feishu
│   ├── auth.py                # 认证模块
│   ├── collector.py           # 采集模块
│   ├── exporter.py            # 文档导出模块
│   └── filter.py              # LLM 闲聊过滤模块
├── inheritance/               # 任务继承模块
│   ├── __init__.py
│   └── manager.py
├── config.yaml                # (更新) 添加飞书配置
├── daily_report.py            # (更新) 整合飞书数据源
├── generator.py               # (更新) 提示词更新
├── .gitignore                 # (更新) 添加飞书缓存
└── ...

# 共享认证（全局）
~/.feishu_env/
└── token_cache.json           # token 缓存（权限 0600）
```

### config.yaml 现有结构说明

现有 config.yaml 包含以下配置项：
- `claude`: Claude 会话路径配置
- `llm`: LLM 配置（arkplan_settings）
- `report`: 日报输出配置

新的飞书配置将添加为顶级 `feishu` 键。

## 核心模块设计

### 1. feishu/auth.py - 飞书认证模块

**职责**:
- OAuth 2.0 网页授权流程（首次获取 user_access_token）
- 自动刷新 user_access_token（使用 refresh_token）
- Token 持久化（保存到 `~/.feishu_env/token_cache.json`）
- 命令行入口支持刷新操作
- 确保目录和文件权限安全

**类定义**:
```python
class FeishuAuthenticator:
    def __init__(self, app_id: str, app_secret: str, env_dir: str = "~/.feishu_env",
                 redirect_uri: str = "http://localhost:8080/callback")
    def get_authorization_url(self) -> str
    def exchange_code_for_token(self, code: str) -> dict
    def get_access_token(self) -> str
    def refresh_access_token(self) -> dict
    def _save_token_cache(self, token_data: dict) -> None
    def _load_token_cache(self) -> Optional[dict]
    def _ensure_env_dir(self) -> None  # 创建目录并设置权限 0700
```

**Token 缓存格式**:
```json
{
  "user_access_token": "u-xxx",
  "refresh_token": "r-xxx",
  "expires_at": 1234567890,
  "refresh_expires_at": 1234567890
}
```

**飞书 API 端点与 Scope**:
- OAuth Scope: `im:message,drive:drive,drive:file`
- 获取授权 URL: `https://open.feishu.cn/open-apis/authen/v1/authorize?app_id={app_id}&redirect_uri={redirect_uri}&response_type=code&scope=im:message drive:drive drive:file`
- 用 code 换取 token: `POST https://open.feishu.cn/open-apis/authen/v1/access_token`
- 刷新 token: `POST https://open.feishu.cn/open-apis/authen/v1/refresh_access_token`

**API 请求/响应示例**:
```python
# 换取 token 请求
POST /open-apis/authen/v1/access_token
Body: {
  "grant_type": "authorization_code",
  "client_id": "{app_id}",
  "client_secret": "{app_secret}",
  "code": "{code}"
}

# 响应示例
{
  "code": 0,
  "data": {
    "access_token": "u-xxx",
    "refresh_token": "r-xxx",
    "expires_in": 86400,
    "refresh_expires_in": 2593500
  }
}
```

**错误处理**:
- `TokenExpiredError`: access_token 过期，需要刷新
- `RefreshTokenExpiredError`: refresh_token 过期，需要重新授权
- `APIError`: 飞书 API 返回错误（含错误码和消息）
- `NetworkError`: 网络请求失败
- 所有错误都应该记录日志，并给出明确的用户提示

### 2. feishu/collector.py - 采集模块

**职责**:
- 获取指定日期的所有聊天消息（群聊 + 私聊）
- 按会话分组，保存为 Markdown 格式
- 提取聊天中的飞书文档链接
- 获取用户最近访问的文档列表
- 支持增量采集（缓存存在时跳过，支持 force 刷新）

**类定义**:
```python
from dataclasses import dataclass

@dataclass
class ChatMessage:
    chat_id: str
    chat_name: str
    chat_type: str  # "group" | "p2p"
    sender_id: str
    sender_name: str
    content: str
    timestamp: datetime

@dataclass
class DocInfo:
    doc_url: str
    doc_title: str
    doc_type: str  # "docx" | "sheet" | "bitable"
    last_accessed: datetime

class FeishuCollector:
    def __init__(self, access_token: str, cache_base_dir: str = "reports/feishu_chat_cache")
    def collect_chat_for_date(self, date: datetime, force: bool = False) -> Path
    def get_recent_docs(self, days: int = 7) -> List[DocInfo]
    def extract_doc_links_from_chat(self, chat_cache_path: Path) -> List[str]
    def _get_chats_list(self) -> List[dict]
    def _get_chat_messages(self, chat_id: str, start_time: int, end_time: int) -> List[ChatMessage]
    def _save_chat_cache(self, date: datetime, messages: List[ChatMessage]) -> Path
```

**飞书 API 端点**:
- 获取会话列表: `GET https://open.feishu.cn/open-apis/im/v1/chats`
- 获取会话消息: `GET https://open.feishu.cn/open-apis/im/v1/messages`
- 获取用户最近文档: `GET https://open.feishu.cn/open-apis/drive/v1/files` (通过访问时间筛选)

**聊天缓存格式** (Markdown):
```markdown
# 飞书聊天记录 - 2026-03-24

## 群聊：产品研发群 (chat_id: oc_xxx)
- [10:30:15] 张三: 那个功能怎么样了？
- [10:31:22] 我: 正在做，预计下午完成
- [10:32:08] 李四: 好的，等你 https://example.feishu.cn/docx/xxx

## 私聊：王五 (chat_id: oc_yyy)
- [14:00:05] 王五: 帮我看下这个文档
```

**错误处理**:
- `ChatListError`: 获取会话列表失败
- `MessageListError`: 获取消息列表失败
- `RateLimitError`: 触发 API 限流，需要等待后重试
- 分页获取消息时处理 `has_more` 标志
- 对于部分失败的会话，记录警告但继续处理其他会话
- 指数退避重试：1s, 2s, 4s，最多 3 次

### 3. feishu/filter.py - LLM 闲聊过滤模块（新增）

**职责**:
- 读取聊天缓存文件
- 将消息分片（每片不超过 15k token）
- 调用 LLM 判断每条消息是否与工作相关
- 提取工作相关的消息片段
- 合并结果供日报生成使用

**类定义**:
```python
class ChatFilter:
    def __init__(self, arkplan_settings: str, token_limit: int = 15000):
        """
        Args:
            arkplan_settings: arkplan.json 路径，用于加载 happy 配置
            token_limit: 每片最大 token 数
        """
        self.arkplan_settings = Path(arkplan_settings)
        self.token_limit = token_limit

    def filter_chat(self, chat_cache_path: Path) -> str:
        """
        过滤聊天记录，只保留工作相关内容

        Returns:
            过滤后的文本内容
        """
        # 实现策略：
        # 1. 读取聊天缓存文件内容
        # 2. 调用 _split_into_chunks() 分片
        # 3. 对每片调用 _call_llm_filter()
        # 4. 合并结果，去除 "无工作相关内容" 的片
        # 5. 如果全部被过滤，返回 "无工作相关内容"
        pass

    def _split_into_chunks(self, content: str) -> List[str]:
        """
        将内容分片，确保每片不超过 token_limit

        Token 计数方式：使用简单估算（中文字符 = 1 token，英文单词 ≈ 1 token）

        实现策略：
        1. 按会话分组（## 群聊/私聊 标题作为边界）
        2. 对每个会话估算 token 数
        3. 将单个会话或多个会话合并，确保不超过 token_limit
        4. 保持会话完整性，不拆分单个会话内部
        """
        pass

    def _call_llm_filter(self, chunk: str) -> str:
        """
        调用 LLM 过滤单条内容

        通过 subprocess 调用 happy:
            happy --settings <arkplan_settings> -p <temp_prompt_file>

        实现策略：
        1. 将 FILTER_PROMPT 与 chunk 拼接，写入临时文件
        2. 调用 happy 子进程
        3. 读取 stdout 作为结果
        4. 如果返回码非 0，抛出 LLMCallError
        5. 清理临时文件
        """
        pass
```

**LLM 过滤提示词**:
```python
FILTER_PROMPT = """你是一个工作内容过滤助手。请从以下飞书聊天记录中，提取所有与工作相关的内容，过滤掉纯闲聊。

【工作内容定义】
- 任务安排、进度汇报、工作讨论
- 项目相关的沟通、问题解决
- 文档协作、代码 review
- 会议安排、会议纪要
- 任何与工作职责相关的对话

【闲聊定义】
- 纯问候、打招呼
- 生活琐事、娱乐八卦
- 与工作无关的闲聊

【输入】
{chat_content}

【输出要求】
- 只输出与工作相关的内容，保持原有的时间、人物、对话结构
- 如果某段对话部分相关部分不相关，只保留相关部分
- 如果没有任何工作相关内容，输出 "无工作相关内容"
- 不要添加任何额外的解释或说明
- 保持 Markdown 格式（群聊/私聊分组）

【重要】
- 严格判断，不要把闲聊误判为工作内容
- 但也不要漏过任何与工作相关的信息
- 对于模糊的内容，保守处理（不确定的就保留）
"""
```

**错误处理**:
- `LLMCallError`: LLM 调用失败，使用原始内容降级处理
- 记录警告日志，但不阻断流程
- 如果过滤完全失败，返回全部原始内容

### 4. feishu/exporter.py - 文档导出与智能总结模块

**职责**:
- 调用 `feishu-docx-export` skill 导出文档到临时目录
- 读取导出的 Markdown 内容
- 混合方案处理：短文档直接注入，长文档先总结
- 清理临时文件

**feishu-docx-export skill 说明**:
- 来源：项目已有 skill，位于 `.claude/skills/feishu-docx-export/`
- 功能：导出飞书文档（docx/sheets/bitable/wiki）为 Markdown
- 使用方式：通过 Skill 工具或 happy 命令行调用

**类定义**:
```python
class FeishuDocExporter:
    def __init__(self, temp_dir: str = "/tmp/feishu_docs",
                 arkplan_settings: str = "~/.claude/arkplan.json",
                 summary_threshold: int = 3500):  # 超过 3500 字符则总结
        self.temp_dir = Path(temp_dir)
        self.arkplan_settings = Path(arkplan_settings)
        self.summary_threshold = summary_threshold

    def export_doc(self, doc_url: str) -> Optional[str]
    def export_docs(self, doc_urls: List[str]) -> Dict[str, str]
    def cleanup(self) -> None
    def _call_feishu_export_skill(self, doc_url: str) -> Optional[Path]
    def _read_exported_doc(self, export_path: Path) -> str
    def _summarize_doc_if_needed(self, content: str, doc_url: str) -> str
        """
        混合方案：
        - 内容长度 <= summary_threshold: 直接返回原内容
        - 内容长度 > summary_threshold: 调用 LLM 生成摘要
        """
```

**文档总结提示词**:
```python
DOC_SUMMARY_PROMPT = """请对以下飞书文档内容生成一个简洁的摘要，突出与工作相关的关键信息。

【要求】
- 摘要长度控制在 300-500 字
- 保留关键结论、任务、决策、时间节点
- 如果是会议纪要，保留参会人、议题、决议
- 如果是项目文档，保留项目状态、关键里程碑、待办事项
- 不要遗漏重要的工作信息

【文档内容】
{doc_content}

【输出格式】
直接输出摘要，不要添加额外说明。
"""
```

**feishu-docx-export skill 使用方式**:
```bash
# 通过 Python subprocess 调用导出
happy --settings ~/.claude/arkplan.json --skill feishu-docx-export --arg doc_url="<doc_url>"

# Skill 成功判断标准：
# - 返回码为 0
# - 输出包含 Markdown 内容或文件路径
# - 如果失败，返回非 0 或错误信息
```

**导出内容格式**:
```
=== 文档: {doc_title} ===
{processed_content}  # 可能是原内容，也可能是摘要（标注 "[摘要]"）

```

**错误处理**:
- `DocExportError`: 文档导出失败，记录警告，跳过该文档
- `DocSummaryError`: 文档总结失败，降级使用原内容（如果不超长）或截断
- 单个文档失败不影响其他文档导出
- 临时目录使用完毕后确保清理（使用 try/finally）
- 如果 temp_dir 不存在，自动创建

### 5. inheritance/manager.py - 任务继承模块

**职责**:
- 读取前一天/周/月的报告
- 提取其中未完成的任务（`[ ]` 标记的）
- 提供给新报告使用

**类定义**:
```python
@dataclass
class InheritedTask:
    task_text: str
    source_date: str  # 来源日期，如 "2026-03-23"
    source_type: str  # "daily" | "weekly" | "monthly"

class TaskInheritanceManager:
    def __init__(self, reports_base_dir: str = "reports")
    def get_incomplete_tasks_from_daily(self, date: datetime) -> List[InheritedTask]
    def get_incomplete_tasks_from_weekly(self, year: int, week: int) -> List[InheritedTask]
    def get_incomplete_tasks_from_monthly(self, year: int, month: int) -> List[InheritedTask]
    def _extract_incomplete_tasks(self, report_content: str, source_date: str, source_type: str) -> List[InheritedTask]
    def _format_tasks_for_prompt(self, tasks: List[InheritedTask]) -> str
```

**未完成任务识别规则**:
1. 匹配 Markdown 复选框语法: `- [ ] 任务内容`
2. 排除已完成的任务: `- [x]` 或 `- [X]`
3. 保留任务的完整文本（包括时间节点）
4. 如果有嵌套列表，只提取顶层任务

**格式化输出示例**（给 LLM 提示词用）:
```
【昨日未完成任务】
以下是前一天未完成的任务，请在今日日报中继承并更新状态：
- [ ] 完成飞书认证模块开发 - 2026-03-24
- [ ] 编写测试用例 - 本周内
```

**周报/月报任务继承说明**:
- 周报继承：读取上一周周报的未完成任务
- 月报继承：读取上一个月月报的未完成任务
- 继承逻辑与日报相同：识别 `- [ ]` 标记的任务
- 格式化提示词标题相应改为「上周未完成任务」或「上月未完成任务」

**错误处理**:
- 如果前一天报告不存在，返回空列表
- 如果解析失败，记录警告并返回空列表
- 不阻断主流程

### 6. config.yaml 更新

```yaml
# 现有配置保持不变
claude:
  history_path: "~/.claude/history.jsonl"
  projects_path: "~/.claude/projects"

llm:
  arkplan_settings: "~/.claude/arkplan.json"

report:
  base_dir: "reports"

# 新增：飞书配置
feishu:
  enabled: true  # 是否启用飞书集成
  app_id: "your_app_id_here"
  app_secret: "your_app_secret_here"
  env_dir: "~/.feishu_env"
  chat_cache_dir: "reports/feishu_chat_cache"
  temp_dir: "/tmp/feishu_docs"
  llm_token_limit: 15000
  recent_docs_days: 7
  doc_summary_threshold: 3500  # 文档超过这个字符数则先生成摘要
  redirect_uri: "http://localhost:8080/callback"  # OAuth 回调地址
```

### 7. .gitignore 更新

```gitignore
# 新增：飞书缓存
reports/feishu_chat_cache/
```

## 配置验证逻辑

在 `daily_report.py` 中添加配置验证：
```python
def validate_feishu_config(config: dict) -> bool:
    """验证飞书配置是否完整"""
    feishu_config = config.get("feishu", {})
    if not feishu_config.get("enabled", False):
        return True  # 未启用，无需验证
    required_keys = ["app_id", "app_secret"]
    for key in required_keys:
        if not feishu_config.get(key):
            print(f"Warning: feishu.{key} 未配置，飞书集成将不可用")
            return False
    return True
```

## 数据流程（详细版）

### 主流程整合（daily_report.py 更新）

```python
# 新增的整合流程
def collect_all_sources(date: datetime, config: dict, force: bool = False) -> str:
    """
    收集所有数据源：Claude 会话 + 飞书聊天 + 飞书文档 + 继承任务
    """
    parts = []

    # 1. Claude 会话（现有）
    claude_collector = ClaudeCollector(...)
    claude_content = claude_collector.collect_for_date(date)
    if claude_content:
        parts.append("=== Claude 会话记录 ===\n" + claude_content)

    # 2. 飞书集成（新增）
    if config.get("feishu", {}).get("enabled", False):
        feishu_content = collect_feishu_sources(date, config, force)
        if feishu_content:
            parts.append(feishu_content)

    # 3. 继承任务（新增）
    inheritance_mgr = TaskInheritanceManager(...)
    yesterday = date - timedelta(days=1)
    inherited_tasks = inheritance_mgr.get_incomplete_tasks_from_daily(yesterday)
    if inherited_tasks:
        tasks_text = inheritance_mgr._format_tasks_for_prompt(inherited_tasks)
        parts.append(tasks_text)

    return "\n\n".join(parts)

def collect_feishu_sources(date: datetime, config: dict, force: bool = False) -> str:
    """收集飞书数据源"""
    parts = []
    feishu_config = config.get("feishu", {})

    # 认证
    auth = FeishuAuthenticator(
        feishu_config["app_id"],
        feishu_config["app_secret"],
        feishu_config.get("env_dir", "~/.feishu_env"),
        feishu_config.get("redirect_uri", "http://localhost:8080/callback")
    )
    try:
        access_token = auth.get_access_token()
    except RefreshTokenExpiredError:
        print("飞书 refresh_token 已过期，请重新运行 'python -m feishu auth' 授权")
        return ""
    except Exception as e:
        print(f"飞书认证失败: {e}")
        return ""

    # 采集聊天记录
    collector = FeishuCollector(access_token, feishu_config.get("chat_cache_dir", "reports/feishu_chat_cache"))
    chat_cache_path = collector.collect_chat_for_date(date, force=force)

    # LLM 过滤闲聊
    chat_filter = ChatFilter(
        config["llm"]["arkplan_settings"],
        feishu_config.get("llm_token_limit", 15000)
    )
    filtered_chat = chat_filter.filter_chat(chat_cache_path)
    if filtered_chat and filtered_chat != "无工作相关内容":
        parts.append("=== 飞书聊天（已过滤）===\n" + filtered_chat)

    # 导出文档
    doc_links = collector.extract_doc_links_from_chat(chat_cache_path)
    recent_docs = collector.get_recent_docs(days=feishu_config.get("recent_docs_days", 7))
    all_doc_urls = doc_links + [d.doc_url for d in recent_docs]

    # 去重策略：基于 URL 字符串完全匹配去重
    unique_doc_urls = list(dict.fromkeys(all_doc_urls))  # 保持顺序去重

    if unique_doc_urls:
        exporter = FeishuDocExporter(
            feishu_config.get("temp_dir", "/tmp/feishu_docs"),
            config["llm"]["arkplan_settings"],
            feishu_config.get("doc_summary_threshold", 3500)
        )
        try:
            doc_contents = exporter.export_docs(unique_doc_urls)
        finally:
            exporter.cleanup()

        if doc_contents:
            parts.append("=== 飞书文档 ===\n")
            for url, content in doc_contents.items():
                parts.append(f"--- {url} ---\n{content}")

    return "\n\n".join(parts)
```

## LLM 提示词更新（generator.py）

### 日报提示词更新

在 `generator.py` 的 `_build_daily_prompt` 方法中，在开头添加以下内容：

```python
DAILY_PROMPT_PREFIX = """【重要：继承任务说明】
如果输入中包含「昨日未完成任务」部分，请：
1. 将这些任务作为今天日报的「四、下一步计划」的基础
2. 对于今天会话中提到已经完成的继承任务，移到「二、关键进展」中，并标记为已完成
3. 对于今天会话中提到有新进展但未完成的继承任务，保留在「下一步计划」中，但更新任务描述
4. 对于没有提到的继承任务，继续保留在「下一步计划」中

【重要：飞书聊天说明】
输入中可能包含「飞书聊天（已过滤）」部分，这是从飞书聊天中提取的工作相关内容。请：
1. 将其与 Claude 会话记录合并分析
2. 同样区分「自主工作」和「下属支持」
3. 从中提取关键进展、遇到的困难等

【重要：飞书文档说明】
输入中可能包含「飞书文档」部分，这是从飞书文档中导出的内容。请：
1. 参考文档内容理解工作背景
2. 如果文档是今天创建或编辑的，可以在关键进展中提及
3. 不要直接大段复制文档内容，而是总结与今日工作相关的部分

---

"""

# 然后拼接原有的提示词
```

### 周报/月报提示词更新

周报/月报提示词同样添加继承任务说明，标题相应改为「上周未完成任务」或「上月未完成任务」。

## CRON 配置

```bash
# 飞书 token 自动刷新（每天凌晨 1 点）
0 1 * * * cd /path/to/daily_report && python -m feishu refresh

# 每日日报生成（凌晨 2 点）
0 2 * * * cd /path/to/daily_report && python daily_report.py --yesterday
```

### feishu/__main__.py - 模块入口（支持 python -m feishu）

```python
"""
飞书模块入口，支持 python -m feishu 命令
"""
import argparse
import sys
from pathlib import Path

# 添加父目录到 path 以便导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from feishu.auth import FeishuAuthenticator
from daily_report import load_config

def main():
    parser = argparse.ArgumentParser(description="飞书认证管理")
    parser.add_argument("command", choices=["auth", "refresh"], help="命令: auth-首次授权, refresh-刷新token")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    args = parser.parse_args()

    config = load_config(args.config)
    feishu_config = config.get("feishu", {})

    if not feishu_config:
        print("错误: 配置文件中未找到 feishu 配置")
        sys.exit(1)

    auth = FeishuAuthenticator(
        feishu_config["app_id"],
        feishu_config["app_secret"],
        feishu_config.get("env_dir", "~/.feishu_env"),
        feishu_config.get("redirect_uri", "http://localhost:8080/callback")
    )

    if args.command == "auth":
        # 首次授权流程
        url = auth.get_authorization_url()
        print(f"请访问以下 URL 进行授权:\n{url}")
        code = input("请输入授权码: ")
        token_data = auth.exchange_code_for_token(code)
        print(f"授权成功! Token 已保存")
    elif args.command == "refresh":
        # 刷新 token
        try:
            token_data = auth.refresh_access_token()
            print(f"Token 刷新成功! 新过期时间: {token_data['expires_at']}")
        except RefreshTokenExpiredError:
            print("错误: refresh_token 已过期，请重新运行 'python -m feishu auth' 进行授权")
            sys.exit(1)

if __name__ == "__main__":
    main()
```

## 错误处理策略

### 错误分类与处理

| 错误类型 | 触发场景 | 处理方式 | 用户体验 |
|---------|---------|---------|---------|
| `TokenExpiredError` | access_token 过期 | 自动调用 refresh_access_token() | 透明，用户无感知 |
| `RefreshTokenExpiredError` | refresh_token 过期 | 提示用户重新运行授权命令 | 明确提示，引导重新授权 |
| `RateLimitError` | API 触发限流 | 指数退避重试（最多 3 次，间隔 1s/2s/4s） | 自动重试，失败则记录警告 |
| `NetworkError` | 网络请求失败 | 重试 2 次，间隔 1s | 自动重试，失败则记录警告 |
| `ChatListError` | 获取会话列表失败 | 跳过飞书聊天采集，继续 Claude 会话 | 记录警告，日报继续生成 |
| `DocExportError` | 文档导出失败 | 跳过该文档，继续其他文档 | 记录警告，不影响其他文档 |
| `LLMCallError` | LLM 过滤失败 | 使用原始聊天内容降级 | 记录警告，日报继续生成 |

### 降级策略

1. **飞书聊天完全不可用** → 只使用 Claude 会话生成日报
2. **LLM 过滤失败** → 使用原始聊天内容
3. **文档导出失败** → 跳过文档，只使用聊天记录
4. **任务继承失败** → 不继承任务，正常生成日报

## 风险与注意事项

1. **Token 安全**: `~/.feishu_env` 目录权限设置为 0700，token_cache.json 权限设置为 0600；在 `_ensure_env_dir()` 和 `_save_token_cache()` 中显式设置
2. **API 限流**: 飞书 API 有调用频率限制，添加指数退避重试（1s, 2s, 4s）
3. **Token 有效期**: user_access_token 有效期约 15 天，refresh_token 有效期约 30 天；每天刷新确保不会过期
4. **大量消息处理**: 某天消息特别多时，按会话分片处理，每片不超过 15k token；token 计数采用简单估算（中文字符=1 token，英文单词≈1 token）
5. **增量采集**: 聊天缓存已存在时跳过采集，支持 `--force` 强制重新采集
6. **隐私保护**: 飞书聊天缓存文件不提交到 git，添加到 .gitignore
7. **文档去重**: 使用 URL 完全匹配去重，保持首次出现的顺序

## 测试计划

1. **单元测试**:
   - 任务继承模块：测试未完成任务提取
   - 聊天过滤模块：测试 LLM 提示词逻辑
   - 认证模块：测试 token 缓存读写和权限设置

2. **集成测试**:
   - 完整流程：从授权到日报生成
   - 错误场景：token 过期、网络失败等

3. **手动测试**:
   - 首次授权流程
   - Token 刷新 cron
   - 飞书聊天开关切换

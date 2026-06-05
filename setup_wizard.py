"""
初始化引导工具
"""
from pathlib import Path
from typing import Any, Dict, List

import yaml


DEFAULT_FEISHU_SCOPE = (
    "contact:user.basic_profile:readonly contact:user.base:readonly "
    "contact:user.id:readonly contact:user.email:readonly "
    "contact:user.department:readonly contact:user:search "
    "contact:department.base:readonly directory:department.base:read "
    "directory:department:list directory:department:read "
    "directory:employee.base.base:read directory:employee.base.department:read "
    "directory:employee.base.email:read directory:employee.base.name.name:read "
    "directory:employee:list directory:employee:read im:chat im:message "
    "calendar:calendar calendar:calendar:read calendar:calendar:readonly "
    "calendar:calendar.event:read docs:doc docs:doc:readonly "
    "docs:document.content:read docs:document:copy docs:document:export "
    "drive:drive drive:file drive:file:readonly drive:file:download "
    "vc:meeting vc:meeting:readonly vc:record:readonly minutes:minutes "
    "minutes:minutes:readonly wiki:wiki wiki:wiki:readonly search:docs:read "
    "offline_access sheets:spreadsheet docx:document board:whiteboard:node:read "
    "bitable:app docs:doc contact:contact.base:readonly board:whiteboard:node:read"
)


def build_config(
    enable_feishu: bool = True,
    enable_codex: bool = True,
    redirect_uri: str = "http://localhost:8080/callback",
) -> Dict[str, Any]:
    """构建默认配置，敏感信息使用 os.environ/VAR 引用"""
    return {
        "claude": {
            "history_path": "~/.claude/history.jsonl",
            "projects_path": "~/.claude/projects",
        },
        "codex": {
            "enabled": enable_codex,
            "sessions_path": "~/.codex/sessions",
            "history_path": "~/.codex/history.jsonl",
            "exclude_keywords": [
                "xueqiu",
                "quant",
                "daily_report",
                "daily-report",
            ],
        },
        "llm": {
            "api_key": "os.environ/ARK_API_KEY",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3/responses",
            "model": "doubao-seed-2-0-pro-260215",
            "timeout": 600,
        },
        "report": {
            "base_dir": "reports",
        },
        "feishu": {
            "enabled": enable_feishu,
            "app_id": "os.environ/FEISHU_APP_ID",
            "app_secret": "os.environ/FEISHU_APP_SECRET",
            "env_dir": "~/.feishu_env",
            "chat_cache_dir": "cache/feishu_chat_cache",
            "temp_dir": "cache/feishu_docs_cache",
            "llm_token_limit": 15000,
            "recent_docs_days": 7,
            "doc_summary_threshold": 10000,
            "redirect_uri": redirect_uri,
            "scope": DEFAULT_FEISHU_SCOPE,
        },
    }


def write_config(path: Path, config: Dict[str, Any], force: bool = False) -> bool:
    """写入配置文件；默认不覆盖已有配置"""
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    return True


def build_next_steps() -> List[str]:
    """返回初始化后的下一步命令提示"""
    return [
        "1. 如需重新生成配置: python daily_report.py --init --force",
        "2. 配置环境变量: ARK_API_KEY, FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_REDIRECT_URI",
        "3. 飞书授权并自动承接回调: python -m feishu auth --callback",
        "4. 查看飞书授权状态: python -m feishu status",
        "5. Codex 会话会自动纳入日报；当天没有 Codex 会话时会自动跳过",
        "6. 生成昨天日报: python daily_report.py --yesterday",
    ]


def run_init(config_path: str = "config.yaml", force: bool = False) -> bool:
    """执行终端初始化引导"""
    path = Path(config_path)
    config = build_config()
    wrote = write_config(path, config, force=force)
    if wrote:
        print(f"已生成配置: {path}")
    else:
        print(f"配置已存在，未覆盖: {path}")
        print("如需覆盖，请运行: python daily_report.py --init --force")

    print("\n下一步:")
    for step in build_next_steps():
        print(f"  {step}")
    return wrote

"""
初始化引导工具
"""
import json
import os
import socket
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import requests
import yaml


DEFAULT_REDIRECT_URI = "http://localhost:8080/callback"
DEFAULT_CALLBACK_HOST = "127.0.0.1"
DEFAULT_CALLBACK_PORT = 8080

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
    redirect_uri: str = DEFAULT_REDIRECT_URI,
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
        },
        "llm": {
            "api_key": "os.environ/ARK_API_KEY",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3/responses",
            "model": "deepseek-v4-flash-260425",
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
            "user_aliases": [],
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
        "2. 配置环境变量: ARK_API_KEY, FEISHU_APP_ID, FEISHU_APP_SECRET",
        "3. 飞书授权并自动承接回调: python -m feishu auth --callback",
        "4. 查看飞书授权状态: python -m feishu status",
        "5. Codex 会话会自动纳入日报；当天没有 Codex 会话时会自动跳过",
        "6. 生成昨天日报: python daily_report.py --yesterday",
    ]


def build_local_next_steps() -> List[str]:
    """返回本地用户初始化后的启动步骤"""
    return [
        "1. 配置环境变量: ARK_API_KEY, FEISHU_APP_ID, FEISHU_APP_SECRET",
        "2. 检查本地环境: python daily_report.py doctor",
        "3. 飞书授权并自动承接回调: python -m feishu auth --callback",
        "4. 再次确认授权状态: python -m feishu status",
        "5. 生成昨天日报: python daily_report.py --yesterday",
    ]


def _resolve_env_reference(value: Any, env: Mapping[str, str]) -> Any:
    if isinstance(value, str) and value.startswith("os.environ/"):
        env_var = value[len("os.environ/"):]
        return env.get(env_var, value)
    return value


def _missing_env_refs(values: Mapping[str, Any], env: Mapping[str, str]) -> List[str]:
    missing = []
    for value in values.values():
        if isinstance(value, str) and value.startswith("os.environ/"):
            env_var = value[len("os.environ/"):]
            if not env.get(env_var):
                missing.append(env_var)
    return missing


def _is_missing_value(value: Any) -> bool:
    return value in (None, "") or (
        isinstance(value, str) and value.startswith("os.environ/")
    )


def is_port_available(host: str = DEFAULT_CALLBACK_HOST, port: int = DEFAULT_CALLBACK_PORT) -> bool:
    """检查本地端口是否可用于 OAuth callback"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
        return True
    except OSError:
        return False


def choose_callback_port(
    host: str = DEFAULT_CALLBACK_HOST,
    preferred_port: int = DEFAULT_CALLBACK_PORT,
    port_checker: Callable[[str, int], bool] = is_port_available,
    max_attempts: int = 20,
) -> Optional[int]:
    """选择 OAuth callback 可用端口，优先使用 preferred_port"""
    for offset in range(max_attempts):
        candidate = preferred_port + offset
        if port_checker(host, candidate):
            return candidate
    return None


def rewrite_local_callback_uri(redirect_uri: str, port: int) -> str:
    """将本地 OAuth callback redirect_uri 改到实际监听端口"""
    if not redirect_uri or redirect_uri.startswith("os.environ/"):
        return f"http://localhost:{port}/callback"
    parsed = urlparse(redirect_uri)
    if not parsed.scheme or not parsed.hostname:
        return f"http://localhost:{port}/callback"
    hostname = parsed.hostname
    if hostname not in {"localhost", "127.0.0.1"}:
        return redirect_uri
    netloc = f"{hostname}:{port}"
    return urlunparse(parsed._replace(netloc=netloc))


def check_llm_endpoint(llm_config: Dict[str, Any]) -> Tuple[bool, str]:
    """用极小请求检查 LLM endpoint 是否可请求"""
    api_key = llm_config.get("api_key")
    base_url = llm_config.get("base_url")
    model = llm_config.get("model")
    if _is_missing_value(api_key):
        return False, "missing api key: ARK_API_KEY"
    if _is_missing_value(base_url):
        return False, "missing llm.base_url"
    if _is_missing_value(model):
        return False, "missing llm.model"

    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "ping",
                    }
                ],
            }
        ],
    }
    timeout = min(int(llm_config.get("timeout", 30)), 30)
    try:
        response = requests.post(
            base_url,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return False, f"request failed: {exc}"
    if response.status_code >= 400:
        return False, f"HTTP {response.status_code}: {response.text[:200]}"
    return True, f"HTTP {response.status_code}"


def _check_token_cache(env_dir: str, now: int) -> Tuple[bool, str]:
    token_path = Path(os.path.expanduser(env_dir)) / "token_cache.json"
    if not token_path.exists():
        return False, "未找到 token 缓存，请运行: python -m feishu auth --callback"
    try:
        token_data = json.loads(token_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"token 缓存读取失败: {exc}"
    refresh_expires_at = int(token_data.get("refresh_expires_at", 0))
    access_expires_at = int(token_data.get("expires_at", 0))
    if refresh_expires_at <= now:
        return False, "refresh_token 已过期，请运行: python -m feishu auth --callback"
    if access_expires_at <= now:
        return False, "access_token 已过期，请运行: python -m feishu refresh"
    return True, "token 缓存有效"


def _check_directory(path_value: Any) -> Tuple[bool, str]:
    path = Path(os.path.expanduser(str(path_value)))
    if path.exists() and path.is_dir():
        return True, str(path)
    return False, f"目录不存在: {path}"


def collect_local_doctor_checks(
    config: Dict[str, Any],
    env: Optional[Mapping[str, str]] = None,
    port_checker: Callable[[str, int], bool] = is_port_available,
    endpoint_checker: Callable[[Dict[str, Any]], Tuple[bool, str]] = check_llm_endpoint,
    now: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """收集本地初始化环境检查结果，不直接退出进程"""
    env = os.environ if env is None else env
    now = int(time.time()) if now is None else now
    feishu_config = config.get("feishu", {})
    llm_config = dict(config.get("llm", {}))

    app_id = _resolve_env_reference(feishu_config.get("app_id"), env)
    app_secret = _resolve_env_reference(feishu_config.get("app_secret"), env)
    redirect_uri = _resolve_env_reference(feishu_config.get("redirect_uri"), env)
    llm_config["api_key"] = _resolve_env_reference(llm_config.get("api_key"), env)
    missing_feishu = _missing_env_refs(
        {
            "app_id": feishu_config.get("app_id"),
            "app_secret": feishu_config.get("app_secret"),
        },
        env,
    )

    checks: List[Dict[str, Any]] = []
    credentials_ok = not missing_feishu and not _is_missing_value(app_id) and not _is_missing_value(app_secret)
    checks.append({
        "name": "Feishu app id/secret",
        "ok": credentials_ok,
        "message": "已配置" if credentials_ok else f"缺少环境变量: {', '.join(missing_feishu or ['FEISHU_APP_ID', 'FEISHU_APP_SECRET'])}",
    })

    redirect_ok = redirect_uri == DEFAULT_REDIRECT_URI
    checks.append({
        "name": "Feishu redirect URI",
        "ok": redirect_ok,
        "message": "已匹配" if redirect_ok else f"当前为 {redirect_uri}，建议设置为 {DEFAULT_REDIRECT_URI}",
    })

    callback_port = choose_callback_port(
        DEFAULT_CALLBACK_HOST,
        DEFAULT_CALLBACK_PORT,
        port_checker=port_checker,
    )
    port_ok = callback_port is not None
    if callback_port == DEFAULT_CALLBACK_PORT:
        port_message = "可监听"
    elif callback_port is not None:
        port_message = f"8080 已占用，将使用备用端口 {callback_port}；请确认飞书后台允许 http://localhost:{callback_port}/callback"
    else:
        port_message = "未找到可用端口，OAuth callback 可能失败"
    checks.append({
        "name": "OAuth callback port",
        "ok": port_ok,
        "message": port_message,
    })

    token_ok, token_message = _check_token_cache(
        feishu_config.get("env_dir", "~/.feishu_env"),
        now,
    )
    checks.append({
        "name": "Feishu token",
        "ok": token_ok,
        "message": token_message,
    })

    claude_ok, claude_message = _check_directory(config.get("claude", {}).get("projects_path", "~/.claude/projects"))
    checks.append({
        "name": "Claude projects directory",
        "ok": claude_ok,
        "message": claude_message,
    })

    codex_ok, codex_message = _check_directory(config.get("codex", {}).get("sessions_path", "~/.codex/sessions"))
    checks.append({
        "name": "Codex sessions directory",
        "ok": codex_ok,
        "message": codex_message,
    })

    llm_ok, llm_message = endpoint_checker(llm_config)
    checks.append({
        "name": "LLM endpoint",
        "ok": llm_ok,
        "message": llm_message,
    })

    return checks


def print_doctor_checks(checks: List[Dict[str, Any]]) -> bool:
    """打印 doctor 检查结果，返回是否全部通过"""
    all_ok = True
    print("本地初始化检查:")
    for check in checks:
        marker = "OK" if check["ok"] else "FAIL"
        if not check["ok"]:
            all_ok = False
        print(f"  [{marker}] {check['name']}: {check['message']}")
    return all_ok


def run_doctor(config: Dict[str, Any]) -> bool:
    """执行本地环境 doctor 检查"""
    return print_doctor_checks(collect_local_doctor_checks(config))


def run_local_init(config_path: str = "config.yaml", force: bool = False) -> bool:
    """面向本地用户的一键初始化入口"""
    path = Path(config_path)
    config = build_config()
    wrote = write_config(path, config, force=force)
    if wrote:
        print(f"已生成本地配置: {path}")
    else:
        print(f"配置已存在，未覆盖: {path}")
        print("如需覆盖，请运行: python daily_report.py --force init local")

    print("\n本地启动步骤:")
    for step in build_local_next_steps():
        print(f"  {step}")
    return wrote


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

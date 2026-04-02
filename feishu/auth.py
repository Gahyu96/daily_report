"""
飞书 OAuth 认证模块
"""
import json
import os
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import requests


# 自定义异常
class TokenExpiredError(Exception):
    """Access token 过期"""
    pass


class RefreshTokenExpiredError(Exception):
    """Refresh token 过期"""
    pass


class APIError(Exception):
    """飞书 API 错误"""
    def __init__(self, code: int, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(f"API Error {code}: {msg}")


class NetworkError(Exception):
    """网络请求错误"""
    pass


class FeishuAuthenticator:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        env_dir: str = "~/.feishu_env",
        redirect_uri: str = "http://localhost:8080/callback",
        scope: str = ""
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.env_dir = Path(os.path.expanduser(env_dir))
        self.redirect_uri = redirect_uri
        self.scope = scope
        self.token_cache_path = self.env_dir / "token_cache.json"
        self._ensure_env_dir()

    def _ensure_env_dir(self) -> None:
        """确保环境目录存在并设置正确权限"""
        self.env_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.env_dir, 0o700)
        except Exception:
            pass

    def get_authorization_url(self) -> str:
        """获取授权 URL"""
        base_url = "https://open.feishu.cn/open-apis/authen/v1/authorize"
        params = {
            "app_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
        }
        if self.scope:
            params["scope"] = self.scope
        return f"{base_url}?{urllib.parse.urlencode(params)}"

    def _get_app_access_token(self) -> str:
        """获取 app_access_token"""
        url = "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal"
        body = {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }
        try:
            resp = requests.post(url, json=body, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise NetworkError(f"Network request failed: {e}") from e

        if data.get("code") != 0:
            raise APIError(data.get("code", -1), data.get("msg", "Unknown error"))

        return data["app_access_token"]

    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """用授权码换取 token"""
        # 先获取 app_access_token
        app_access_token = self._get_app_access_token()

        url = "https://open.feishu.cn/open-apis/authen/v1/access_token"
        headers = {
            "Authorization": f"Bearer {app_access_token}"
        }
        body = {
            "grant_type": "authorization_code",
            "code": code,
        }
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise NetworkError(f"Network request failed: {e}") from e

        if data.get("code") != 0:
            raise APIError(data.get("code", -1), data.get("msg", "Unknown error"))

        token_data = data["data"]
        now = int(time.time())
        token_data["expires_at"] = now + token_data["expires_in"]
        token_data["refresh_expires_at"] = now + token_data["refresh_expires_in"]

        self._save_token_cache(token_data)
        return token_data

    def get_access_token(self) -> str:
        """获取有效的 access_token（自动刷新）"""
        token_data = self._load_token_cache()
        if not token_data:
            raise TokenExpiredError("No token found, please authenticate first")

        now = int(time.time())
        if now >= token_data["expires_at"]:
            # Token 过期，尝试刷新
            token_data = self.refresh_access_token()

        return token_data["access_token"]

    def refresh_access_token(self) -> Dict[str, Any]:
        """刷新 access_token"""
        token_data = self._load_token_cache()
        if not token_data:
            raise TokenExpiredError("No token found, please authenticate first")

        now = int(time.time())
        if now >= token_data["refresh_expires_at"]:
            raise RefreshTokenExpiredError("Refresh token expired, please re-authenticate")

        url = "https://open.feishu.cn/open-apis/authen/v1/refresh_access_token"
        # 先获取 app_access_token
        app_access_token = self._get_app_access_token()
        headers = {
            "Authorization": f"Bearer {app_access_token}"
        }
        body = {
            "grant_type": "refresh_token",
            "refresh_token": token_data["refresh_token"],
        }
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise NetworkError(f"Network request failed: {e}") from e

        if data.get("code") != 0:
            raise APIError(data.get("code", -1), data.get("msg", "Unknown error"))

        new_token_data = data["data"]
        now = int(time.time())
        new_token_data["expires_at"] = now + new_token_data["expires_in"]
        new_token_data["refresh_expires_at"] = now + new_token_data["refresh_expires_in"]

        self._save_token_cache(new_token_data)
        return new_token_data

    def _save_token_cache(self, token_data: Dict[str, Any]) -> None:
        """保存 token 缓存"""
        with open(self.token_cache_path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, ensure_ascii=False, indent=2)
        try:
            os.chmod(self.token_cache_path, 0o600)
        except Exception:
            pass

    def _load_token_cache(self) -> Optional[Dict[str, Any]]:
        """加载 token 缓存"""
        if not self.token_cache_path.exists():
            return None
        try:
            with open(self.token_cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load token cache: {e}")
            return None

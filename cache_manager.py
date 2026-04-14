"""
缓存管理模块
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


class CacheManager:
    def __init__(self, base_dir: str = "cache"):
        self.base_dir = Path(base_dir)

    def get_cache_dir(self, date: datetime) -> Path:
        """获取指定日期的缓存目录（YYYY-MM/YYYY-MM-DD/ 格式）"""
        month_str = date.strftime("%Y-%m")
        date_str = date.strftime("%Y-%m-%d")
        cache_dir = self.base_dir / month_str / date_str
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def _get_legacy_cache_dir(self, date: datetime) -> Path:
        """获取旧格式的缓存目录（YYYY-MM-DD/ 格式）"""
        date_str = date.strftime("%Y-%m-%d")
        return self.base_dir / date_str

    def get_cache_path(self, date: datetime, source: str) -> Path:
        """获取指定来源的缓存文件路径"""
        cache_dir = self.get_cache_dir(date)
        return cache_dir / f"{source}.md"

    def has_cache(self, date: datetime, source: str) -> bool:
        """检查缓存是否存在（兼容新旧格式）"""
        # 先检查新格式
        if self.get_cache_path(date, source).exists():
            return True
        # 再检查旧格式
        legacy_path = self._get_legacy_cache_dir(date) / f"{source}.md"
        return legacy_path.exists()

    def read_cache(self, date: datetime, source: str) -> Optional[str]:
        """读取缓存（兼容新旧格式）"""
        cache_path = self.get_cache_path(date, source)
        if not cache_path.exists():
            # 尝试旧格式
            legacy_path = self._get_legacy_cache_dir(date) / f"{source}.md"
            if legacy_path.exists():
                cache_path = legacy_path
            else:
                return None
        with open(cache_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 跳过元数据部分，返回内容
        if "=== 内容 ===" in content:
            return content.split("=== 内容 ===", 1)[1].strip()
        return content

    def write_cache(self, date: datetime, source: str, content: str, metadata: Optional[Dict[str, Any]] = None):
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

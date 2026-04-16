"""
飞书文档导出与智能总结模块
"""
import sys
import subprocess
import shutil
import re
import hashlib
import concurrent.futures
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, List

sys.path.insert(0, str(Path(__file__).parent.parent))
from feishu.auth import FeishuAuthenticator


class DocExportError(Exception):
    """文档导出失败"""
    pass


class DocSummaryError(Exception):
    """文档总结失败"""
    pass


class FeishuDocExporter:
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

    def __init__(
        self,
        temp_dir: str = "/tmp/feishu_docs",
        llm_config_or_arkplan: any = "~/.claude/arkplan.json",
        summary_threshold: int = 3500,
        doc_cache_dir: str = "cache/feishu_doc_cache",
        cache_ttl_days: int = 7,
        feishu_config: Optional[Dict] = None
    ):
        self.temp_dir = Path(temp_dir)
        # 向后兼容：支持字符串（arkplan_settings路径）或 dict（llm_config）
        if isinstance(llm_config_or_arkplan, dict):
            self.llm_config = llm_config_or_arkplan
            self.arkplan_settings = Path(llm_config_or_arkplan.get("arkplan_settings", "~/.claude/arkplan.json"))
        else:
            self.llm_config = {}
            self.arkplan_settings = Path(llm_config_or_arkplan)
        self.summary_threshold = summary_threshold
        self.doc_cache_dir = Path(doc_cache_dir)
        self.cache_ttl_days = cache_ttl_days
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.doc_cache_dir.mkdir(parents=True, exist_ok=True)
        self.feishu_config = feishu_config

    def _get_url_hash(self, doc_url: str) -> str:
        """从 URL 生成 hash"""
        return hashlib.md5(doc_url.encode('utf-8')).hexdigest()[:16]

    def _sanitize_filename(self, name: str) -> str:
        """清理文件名"""
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        name = name.replace('\n', ' ').replace('\r', '')
        return name.strip()[:100]

    def _get_cache_folder(self, doc_url: str, doc_title: Optional[str] = None) -> Path:
        """获取缓存文件夹路径"""
        url_hash = self._get_url_hash(doc_url)
        if doc_title:
            folder_name = f"{self._sanitize_filename(doc_title)}_{url_hash}"
        else:
            # 没有标题时，尝试查找已存在的文件夹
            for folder in self.doc_cache_dir.iterdir():
                if folder.is_dir() and folder.name.endswith(f"_{url_hash}"):
                    return folder
            folder_name = f"doc_{url_hash}"
        return self.doc_cache_dir / folder_name

    def _get_md_path(self, cache_folder: Path, doc_title: Optional[str] = None) -> Optional[Path]:
        """在缓存文件夹中找到 md 文件"""
        md_files = list(cache_folder.glob("*.md"))
        if md_files:
            return md_files[0]
        # 如果没有找到且有标题，尝试构造路径
        if doc_title:
            url_hash = cache_folder.name.split("_")[-1]
            return cache_folder / f"{self._sanitize_filename(doc_title)}_{url_hash}.md"
        return None

    def _is_cache_valid(self, cache_folder: Path) -> bool:
        """检查缓存是否有效"""
        if not cache_folder.exists():
            return False
        md_file = self._get_md_path(cache_folder)
        if not md_file or not md_file.exists():
            return False
        mtime = datetime.fromtimestamp(md_file.stat().st_mtime)
        return datetime.now() - mtime < timedelta(days=self.cache_ttl_days)

    def _get_access_token(self) -> Optional[str]:
        """从 feishu 配置获取 access_token"""
        if not self.feishu_config:
            return None
        try:
            auth = FeishuAuthenticator(
                self.feishu_config["app_id"],
                self.feishu_config["app_secret"],
                self.feishu_config.get("env_dir", "~/.feishu_env"),
                self.feishu_config.get("redirect_uri", "http://localhost:8080/callback"),
                self.feishu_config.get("scope", "")
            )
            return auth.get_access_token()
        except Exception:
            return None

    def _build_export_cmd(self, doc_url: str, output_dir: Path) -> List[str]:
        """构建 feishu-docx export 命令，包含 token 参数"""
        cmd = ["feishu-docx", "export", doc_url, "-o", str(output_dir)]
        access_token = self._get_access_token()
        if access_token:
            cmd.extend(["-t", access_token])
        return cmd

    def export_doc(self, doc_url: str) -> Optional[str]:
        """导出单个文档（带缓存）"""
        url_hash = self._get_url_hash(doc_url)

        # 第一步：先导出到临时目录，获取文档标题
        temp_export_dir = self.temp_dir / f"export_{url_hash}"
        if temp_export_dir.exists():
            shutil.rmtree(temp_export_dir)
        temp_export_dir.mkdir(parents=True, exist_ok=True)

        doc_title = None
        try:
            cmd = self._build_export_cmd(doc_url, temp_export_dir)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                # 从输出中提取标题
                match = re.search(r"文档标题[:：]\s*(.+)", result.stdout + result.stderr)
                if match:
                    doc_title = match.group(1).strip()
        except Exception:
            pass

        # 检查缓存
        cache_folder = self._get_cache_folder(doc_url, doc_title)
        if self._is_cache_valid(cache_folder):
            md_file = self._get_md_path(cache_folder, doc_title)
            if md_file and md_file.exists():
                # 清理临时目录
                if temp_export_dir.exists():
                    shutil.rmtree(temp_export_dir)
                with open(md_file, "r", encoding="utf-8") as f:
                    return f.read()

        # 缓存无效，需要重新导出
        print(f"正在导出文档: {doc_url}")

        # 清理旧缓存
        if cache_folder.exists():
            shutil.rmtree(cache_folder)

        # 如果临时目录有导出的内容，直接移动到缓存位置
        temp_md_files = list(temp_export_dir.glob("*.md"))
        if temp_md_files and doc_title:
            temp_md = temp_md_files[0]

            # 创建缓存文件夹
            cache_folder.mkdir(parents=True, exist_ok=True)

            # 新文件名：标题_hash.md
            new_md_name = f"{self._sanitize_filename(doc_title)}_{url_hash}.md"
            new_md_path = cache_folder / new_md_name

            # 移动文件
            shutil.move(str(temp_md), str(new_md_path))
            # 图片文件夹名与 md 同名（feishu-docx 约定），保持原名以兼容 .md 内的相对路径引用
            temp_assets = temp_export_dir / temp_md.stem
            if temp_assets.exists():
                shutil.move(str(temp_assets), str(cache_folder / temp_assets.name))

            # 清理临时目录
            if temp_export_dir.exists():
                shutil.rmtree(temp_export_dir)

            # 读取内容
            content = self._read_exported_doc(new_md_path)
            if content:
                return self._summarize_doc_if_needed(content, doc_url)

        # 如果临时目录没有内容，或者没有获取到标题，重新导出到缓存文件夹
        if temp_export_dir.exists():
            shutil.rmtree(temp_export_dir)

        # 直接导出到缓存文件夹
        cache_folder.mkdir(parents=True, exist_ok=True)

        try:
            cmd = self._build_export_cmd(doc_url, cache_folder)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                raise DocExportError(f"feishu-docx failed with code {result.returncode}: {result.stderr}")

            # 如果还没有标题，从输出中提取
            if not doc_title:
                match = re.search(r"文档标题[:：]\s*(.+)", result.stdout + result.stderr)
                if match:
                    doc_title = match.group(1).strip()

            # 找到导出的 md 文件并重命名
            md_file = self._get_md_path(cache_folder)
            if not md_file:
                return None

            if doc_title:
                # 重命名文件：标题_hash.md
                new_md_name = f"{self._sanitize_filename(doc_title)}_{url_hash}.md"
                new_md_path = cache_folder / new_md_name

                if md_file.name != new_md_name:
                    # 重命名 md 文件；图片文件夹保持原名，.md 内的相对路径引用不受影响
                    md_file.rename(new_md_path)
                    md_file = new_md_path

            # 读取内容
            content = self._read_exported_doc(md_file)
            if not content:
                return None

            return self._summarize_doc_if_needed(content, doc_url)

        except subprocess.TimeoutExpired as e:
            raise DocExportError(f"feishu-docx timed out: {e}") from e
        except FileNotFoundError:
            # 如果 feishu-docx 命令不存在，尝试使用 python 模块
            try:
                cmd = [
                    sys.executable,
                    "-m",
                    "feishu_docx",
                    "export",
                    doc_url,
                    "-o", str(cache_folder)
                ]
                access_token = self._get_access_token()
                if access_token:
                    cmd.extend(["-t", access_token])
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

                if result.returncode != 0:
                    raise DocExportError(f"feishu-docx module failed with code {result.returncode}: {result.stderr}")

                md_file = self._get_md_path(cache_folder)
                if not md_file:
                    return None

                content = self._read_exported_doc(md_file)
                if not content:
                    return None

                return self._summarize_doc_if_needed(content, doc_url)

            except Exception as e2:
                raise DocExportError(f"feishu-docx not found and module failed: {e2}") from e2

    def export_docs(self, doc_urls: List[str], max_concurrent: int = 4) -> Dict[str, str]:
        """批量并发导出文档"""
        results = {}

        def _export(url: str):
            try:
                content = self.export_doc(url)
                return url, content
            except Exception:
                return url, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            for url, content in executor.map(_export, doc_urls):
                if content:
                    results[url] = content

        return results

    def cleanup(self) -> None:
        """清理临时目录"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _read_exported_doc(self, export_path: Path) -> Optional[str]:
        """读取导出的文档"""
        if not export_path.exists():
            return None
        try:
            with open(export_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return None

    def _summarize_doc_if_needed(self, content: str, doc_url: str) -> str:
        """混合方案：短文档直接返回，长文档先总结"""
        if len(content) <= self.summary_threshold:
            return content

        try:
            summary = self._call_doc_summary(content)
            return f"[摘要] {summary}"
        except DocSummaryError as e:
            return content[:self.summary_threshold] + "\n\n[内容过长已截断]"

    def _call_doc_summary(self, content: str) -> str:
        """调用 LLM 生成文档摘要"""
        import tempfile
        prompt = self.DOC_SUMMARY_PROMPT.format(doc_content=content[:10000])  # 限制输入长度

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
            f.write(prompt)
            temp_path = f.name

        try:
            cmd = [
                "claude",
                "--settings", str(self.arkplan_settings),
                "-p", temp_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                raise DocSummaryError(f"LLM failed with code {result.returncode}: {result.stderr}")

            return result.stdout.strip()

        except subprocess.TimeoutExpired as e:
            raise DocSummaryError(f"Summary timed out: {e}") from e
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass

"""
BaseScraper：YouTube 爬虫基础类

采集方式：使用 yt-dlp 调用 YouTube 内部接口，无需 API Key，无需账号。
"""

import glob
import json
import os
import shutil
import subprocess
import sys
from typing import Optional

from config import OUTPUT_DIR, COMMENT_COUNT
from utils import ensure_dir, safe_text, now_str, save_json, save_csv


def _find_ytdlp() -> list:
    """找到 yt-dlp 可执行文件，返回命令前缀列表。"""
    yt_dlp_bin = shutil.which("yt-dlp")
    if not yt_dlp_bin:
        for candidate in sorted(
            glob.glob(os.path.expanduser("~/Library/Python/*/bin/yt-dlp")),
            reverse=True,
        ):
            if os.path.isfile(candidate):
                yt_dlp_bin = candidate
                break
    if yt_dlp_bin:
        return [yt_dlp_bin]
    return [shutil.which("python3") or sys.executable, "-m", "yt_dlp"]


class BaseScraper:
    def __init__(self, run_label: str, download_videos: bool = False, server=None):
        self.server = server
        self._loop = None
        if server:
            try:
                self._loop = __import__('asyncio').get_running_loop()
            except RuntimeError:
                pass
        self.run_dir = os.path.join(OUTPUT_DIR, f"{run_label}_{now_str()}")
        ensure_dir(self.run_dir)
        self.videos: list = []
        self.all_comments: list = []
        self.download_videos = download_videos
        self.ytdlp_cmd = _find_ytdlp()

    def _log(self, msg: str, end: str = "\n"):
        if self.server and hasattr(self.server, "_log"):
            res = self.server._log(msg)
            if __import__("asyncio").iscoroutine(res):
                try:
                    loop = __import__("asyncio").get_running_loop()
                    loop.create_task(res)
                except RuntimeError:
                    if hasattr(self, "_loop") and self._loop and not self._loop.is_closed():
                        __import__("asyncio").run_coroutine_threadsafe(res, self._loop)
        else:
            sys.stdout.write(str(msg) + end)
            sys.stdout.flush()

    # ── yt-dlp 调用 ───────────────────────────────────────────────────────────

    def _run_ytdlp(self, args: list) -> Optional[str]:
        """运行 yt-dlp 并返回 stdout，失败返回 None。"""
        cmd = self.ytdlp_cmd + args
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                return result.stdout
            err = result.stderr.strip().splitlines()
            # 过滤掉警告行，只显示最后的错误
            errors = [l for l in err if "ERROR" in l or "error" in l.lower()]
            if errors:
                self._log(f"  [yt-dlp 错误] {errors[-1][:120]}")
            return None
        except subprocess.TimeoutExpired:
            self._log("  [超时] yt-dlp 请求超时")
            return None
        except Exception as e:
            self._log(f"  [错误] {e}")
            return None

    def _fetch_info(self, url: str, extra_args: list = None) -> Optional[dict]:
        """获取单个视频或列表的元数据（JSON）。"""
        args = ["--dump-json", "--no-warnings", "--quiet", url]
        if extra_args:
            args = ["--no-warnings", "--quiet"] + extra_args + ["--dump-json", url]
        output = self._run_ytdlp(args)
        if not output:
            return None
        # dump-json 可能输出多行（每行一个视频），取第一行
        first_line = output.strip().splitlines()[0]
        try:
            return json.loads(first_line)
        except json.JSONDecodeError:
            return None

    def _fetch_info_list(self, url: str, flat: bool = True) -> list:
        """
        获取频道/播放列表/搜索结果的视频列表。
        flat=True 时只获取基本信息（快），flat=False 获取完整信息（慢但有播放量）。
        """
        args = self.ytdlp_cmd + [
            "--dump-json",
            "--no-warnings",
            "--quiet",
        ]
        if flat:
            args += ["--flat-playlist"]
        args.append(url)

        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=180
            )
            items = []
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            return items
        except Exception as e:
            self._log(f"  [错误] {e}")
            return []

    # ── 视频解析 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_video(d: dict) -> dict:
        vid = d.get("id") or d.get("url", "").split("v=")[-1].split("&")[0]
        return {
            "video_id":      vid,
            "title":         safe_text(d.get("title", "")),
            "channel_id":    d.get("channel_id", ""),
            "channel_title": safe_text(d.get("channel", d.get("uploader", ""))),
            "description":   safe_text(d.get("description", ""))[:300],
            "published_at":  d.get("upload_date", ""),
            "view_count":    d.get("view_count") or 0,
            "like_count":    d.get("like_count") or 0,
            "comment_count": d.get("comment_count") or 0,
            "duration":      d.get("duration") or 0,
            "url":           f"https://www.youtube.com/watch?v={vid}",
        }

    # ── 评论采集 ──────────────────────────────────────────────────────────────

    def scrape_comments(self, video: dict) -> list:
        """抓取视频评论，使用 yt-dlp --write-comments。"""
        label = (video["title"] or video["video_id"])[:40]
        self._log(f"[评论] {label}")

        tmp_dir = os.path.join(self.run_dir, "_tmp_comments")
        ensure_dir(tmp_dir)
        out_tmpl = os.path.join(tmp_dir, f"{video['video_id']}.%(ext)s")

        args = self.ytdlp_cmd + [
            "--write-comments",
            "--write-info-json",
            "--skip-download",
            "--no-warnings",
            "--extractor-args", "youtube:player_client=tv_embedded",
            "--format", "sb0/mhtml/best",
            "--cookies-from-browser", "chrome",
            "-o", out_tmpl,
            video["url"],
        ]

        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=120)
            if result.returncode != 0 and result.stderr.strip():
                for line in result.stderr.strip().splitlines():
                    if "ERROR" in line or "WARNING" in line:
                        self._log(f"  [yt-dlp] {line.strip()[:120]}")
        except Exception as e:
            self._log(f"  [错误] {e}")
            return []

        # yt-dlp 将评论写入 {video_id}.info.json
        info_file = os.path.join(tmp_dir, f"{video['video_id']}.info.json")
        if not os.path.exists(info_file):
            # 列出 tmp_dir 中实际生成的文件，帮助调试
            created = os.listdir(tmp_dir) if os.path.exists(tmp_dir) else []
            if created:
                self._log(f"  [调试] tmp 目录文件：{created}")
            else:
                self._log("  [跳过] 无法获取评论（可能评论已关闭）")
            return []

        try:
            with open(info_file, "r", encoding="utf-8") as f:
                info = json.load(f)
        except Exception:
            self._log("  [跳过] 评论文件读取失败")
            return []

        raw_comments = info.get("comments", [])
        comments = []
        seen_ids: set = set()

        for c in raw_comments[:COMMENT_COUNT]:
            cid = c.get("id", "")
            if not cid or cid in seen_ids:
                continue
            text = safe_text(c.get("text", ""))
            if not text:
                continue
            seen_ids.add(cid)
            comments.append({
                "comment_id":  cid,
                "video_id":    video["video_id"],
                "author":      safe_text(c.get("author", "")),
                "text":        text,
                "like_count":  c.get("like_count") or 0,
                "time":        c.get("timestamp", ""),
                "is_reply":    c.get("parent", "root") != "root",
            })

        # 清理临时文件
        try:
            os.remove(info_file)
        except Exception:
            pass

        self._log(f"  → 共采集 {len(comments)} 条评论")
        return comments

    # ── 视频下载 ──────────────────────────────────────────────────────────────

    def _download_video(self, video: dict):
        """使用 yt-dlp 下载视频到 videos_media/ 目录。"""
        media_dir = os.path.join(self.run_dir, "videos_media")
        ensure_dir(media_dir)
        out_tmpl = os.path.join(media_dir, f"{video['video_id']}.%(ext)s")

        args = self.ytdlp_cmd + [
            "--no-warnings",
            "--extractor-args", "youtube:player_client=tv_embedded",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "-o", out_tmpl,
            video["url"],
        ]

        self._log(f"  [下载] {video['video_id']} ...", end="\r")
        try:
            result = subprocess.run(args, capture_output=True, text=True)
            if result.returncode == 0:
                self._log(f"  [下载完成] {video['video_id']}          ")
            else:
                err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "未知错误"
                self._log(f"  [下载失败] {video['video_id']}: {err[:120]}")
        except Exception as e:
            self._log(f"  [下载错误] {e}")

    # ── 汇总保存 ──────────────────────────────────────────────────────────────

    def _save_summary(self):
        if not self.all_comments:
            self._log("\n[汇总] 未采集到评论")
            return
        save_json(self.all_comments, os.path.join(self.run_dir, "all_comments.json"))
        save_csv(self.all_comments, os.path.join(self.run_dir, "all_comments.csv"))
        self._log(
            f"\n[完成] {len(self.videos)} 个视频 · {len(self.all_comments)} 条评论"
            f"\n[路径] {self.run_dir}/"
        )

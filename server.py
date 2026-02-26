import asyncio
import json
import os
import sys
import traceback
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

log_queue = asyncio.Queue()
resume_event = asyncio.Event()


class ScrapeCancelled(Exception):
    """Raised when user requests scrape cancellation."""
    pass


class ScrapeControl:
    IDLE    = "idle"
    RUNNING = "running"
    PAUSED  = "paused"
    STOPPED = "stopped"

    def __init__(self):
        self.state = self.IDLE
        self.pause_event = asyncio.Event()   # set=running, clear=paused
        self.stop_event  = asyncio.Event()   # set=stop requested
        self.pause_event.set()               # default: not paused

    def reset(self):
        self.state = self.RUNNING
        self.pause_event.set()
        self.stop_event.clear()


scrape_control = ScrapeControl()

# Set up global python path configuration before we start importing models dynamically
base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

# Override the config paths immediately so any scraped data goes to Social media_01/data
# instead of douyin/data or tiktok/data
from douyin import config as douyin_config
douyin_config.OUTPUT_DIR = os.path.join(base_dir, "data")

from tiktok import config as tiktok_config
tiktok_config.OUTPUT_DIR = os.path.join(base_dir, "data")

from reddit import config as reddit_config
reddit_config.OUTPUT_DIR = os.path.join(base_dir, "data")

from youtube import config as youtube_config
youtube_config.OUTPUT_DIR = os.path.join(base_dir, "data")

from x import config as x_config
x_config.OUTPUT_DIR = os.path.join(base_dir, "data")

import contextlib

@contextlib.contextmanager
def platform_env(platform_name: str):
    """
    Temporarily set up sys.path and sys.modules for a specific platform's imports.
    This resolves ModuleNotFoundError when platform scrapers do `import config`.
    It also prevents cross-platform namespace collisions for common module names.
    """
    platform_dir = os.path.abspath(os.path.join(base_dir, platform_name))
    original_path = list(sys.path)
    if platform_dir not in sys.path:
        sys.path.insert(0, platform_dir)

    conflict_prefixes = ("config", "utils", "main", "scraper")
    saved_modules = {}

    for mod in list(sys.modules.keys()):
        if mod in conflict_prefixes or mod.startswith("scraper."):
            saved_modules[mod] = sys.modules.pop(mod)

    # Alias the pre-loaded namespaces map to the global names so that overrides are respected
    if f"{platform_name}.config" in sys.modules:
        sys.modules["config"] = sys.modules[f"{platform_name}.config"]
    if f"{platform_name}.utils" in sys.modules:
        sys.modules["utils"] = sys.modules[f"{platform_name}.utils"]

    try:
        yield
    finally:
        sys.path[:] = original_path
        for mod in list(sys.modules.keys()):
            if mod in conflict_prefixes or mod.startswith("scraper."):
                del sys.modules[mod]
        for mod, val in saved_modules.items():
            sys.modules[mod] = val


class ScrapeRequest(BaseModel):
    platform: str
    target: str
    mode: str
    count: int = 20
    download_videos: bool = False
    sort_by: str = "1"
    time_filter: int = 0
    scrape_mode: str = "safe"  # "safe" | "fast"

class ChatRequest(BaseModel):
    provider: str
    api_key: str
    folder_paths: list[str]   # 1–10 folders
    prompt: str

class ServerAdapter:
    def __init__(self):
        self.user_continue_event = resume_event
        self.control = scrape_control

    async def _log(self, msg: str):
        # Forward to SSE logs
        await log_queue.put({"message": msg})

    async def request_user_intervention(self, msg: str):
        self.user_continue_event.clear()
        await log_queue.put({"type": "ACTION_REQUIRED", "message": msg})
        # The scraper itself will `await self.server.user_continue_event.wait()`

@app.get("/")
async def root():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.post("/api/scrape")
async def start_scrape(req: ScrapeRequest):
    asyncio.create_task(run_scraper(
        req.platform, req.target, req.mode, req.count,
        req.download_videos, req.sort_by, req.time_filter, req.scrape_mode
    ))
    return {"status": "started", "platform": req.platform, "target": req.target, "mode": req.mode, "count": req.count}

@app.post("/api/resume")
async def resume_scrape():
    resume_event.set()
    await log_queue.put({"message": "Resume signal received from UI"})
    return {"status": "resumed"}

@app.post("/api/pause")
async def pause_scrape():
    if scrape_control.state == ScrapeControl.RUNNING:
        scrape_control.state = ScrapeControl.PAUSED
        scrape_control.pause_event.clear()
        await log_queue.put({"type": "SCRAPE_PAUSED", "message": "[控制] 采集已暂停，等待恢复..."})
        return {"status": "paused"}
    elif scrape_control.state == ScrapeControl.PAUSED:
        scrape_control.state = ScrapeControl.RUNNING
        scrape_control.pause_event.set()
        await log_queue.put({"type": "SCRAPE_RESUMED", "message": "[控制] 采集已恢复"})
        return {"status": "resumed"}
    return {"status": scrape_control.state}

@app.post("/api/stop")
async def stop_scrape():
    scrape_control.stop_event.set()
    scrape_control.pause_event.set()  # unblock any paused wait
    scrape_control.state = ScrapeControl.STOPPED
    await log_queue.put({"type": "SCRAPE_STOPPING", "message": "[控制] 正在停止采集..."})
    return {"status": "stopping"}

@app.get("/api/status")
async def get_status():
    return {"state": scrape_control.state}

@app.get("/api/data/files")
async def get_data_files():
    data_dir = os.path.join(base_dir, "data")
    if not os.path.exists(data_dir):
        return {"files": [], "meta": {}}

    folders = []
    meta = {}
    for entry in os.scandir(data_dir):
        if entry.is_dir():
            folders.append(entry.name)
            meta[entry.name] = {
                "has_all_comments": os.path.isfile(os.path.join(entry.path, "all_comments.json"))
            }

    return {"files": sorted(folders, reverse=True), "meta": meta}

@app.post("/api/data/clean-empty")
async def clean_empty_folders():
    import shutil
    from pathlib import Path
    data_dir = Path(base_dir) / "data"
    if not data_dir.exists():
        return {"deleted": [], "count": 0}

    deleted = []
    for entry in data_dir.iterdir():
        if not entry.is_dir():
            continue
        # Empty = no files anywhere in the subtree
        if not any(p.is_file() for p in entry.rglob("*")):
            shutil.rmtree(entry)
            deleted.append(entry.name)

    return {"deleted": sorted(deleted), "count": len(deleted)}

@app.post("/api/chat")
async def chat_with_data(req: ChatRequest):
    data_dir = os.path.join(base_dir, "data")

    if not req.folder_paths:
        return {"error": "请至少选择一个数据文件夹"}
    if len(req.folder_paths) > 10:
        return {"error": "最多同时分析 10 个文件夹"}

    # Validate all paths and check all_comments.json exists
    validated = []
    for fp in req.folder_paths:
        target = os.path.abspath(os.path.join(data_dir, fp))
        if not target.startswith(data_dir):
            return {"error": f"Invalid folder path: {fp}"}
        if not os.path.isdir(target):
            return {"error": f"Folder not found: {fp}"}
        comments_file = os.path.join(target, "all_comments.json")
        if not os.path.isfile(comments_file):
            return {"error": "NO_COMMENTS_FILE"}
        validated.append((fp, comments_file))

    # Load and merge comments from all folders; reformat to compact text
    MAX_CONTENT_CHARS = 20000
    multi = len(validated) > 1
    sections = []

    try:
        for fp, comments_file in validated:
            with open(comments_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, list):
                return {"error": f"{fp}/all_comments.json 格式不符（期望 JSON 数组）"}

            total = len(raw)
            folder_lines = [f"\n{'='*30}\n📁 数据来源：{fp}（共 {total} 条评论）\n{'='*30}"]
            included = 0
            for c in raw:
                text = str(c.get("text") or c.get("content") or "").strip()
                if not text:
                    continue
                user  = str(c.get("username") or c.get("author") or "匿名").strip()
                likes = str(c.get("like_count") or c.get("likes") or "0").strip()
                line  = f"[{user}]({likes}赞): {text}"
                folder_lines.append(line)
                included += 1

            sections.append("\n".join(folder_lines))
            if total > included:
                sections[-1] += f"\n[已载入 {included}/{total} 条，其余因上下文限制省略]"

        file_content = "\n".join(sections)
        # Trim to budget
        if len(file_content) > MAX_CONTENT_CHARS:
            file_content = file_content[:MAX_CONTENT_CHARS] + "\n\n[数据已截断，超出上下文限制]"

    except json.JSONDecodeError as e:
        return {"error": f"all_comments.json 解析失败：{str(e)}"}
    except Exception as e:
        return {"error": f"读取数据失败: {str(e)}"}

    folder_label = "、".join(req.folder_paths)
    system_prompt = (
        f"你是一个社交媒体数据分析助手。以下是用户爬取的评论数据"
        f"（{'共 ' + str(len(validated)) + ' 个数据集：' + folder_label if multi else folder_label}），"
        f"请根据这些评论数据回答用户的问题。若数据未完整载入，请基于已有数据作答并说明。\n\n"
        f"{file_content}"
    )

    headers = {
        "Authorization": f"Bearer {req.api_key}",
        "Content-Type": "application/json"
    }

    if req.provider == "moonshot":
        url = "https://api.moonshot.cn/v1/chat/completions"
        model = "moonshot-v1-32k"  # 32k context avoids output truncation on large data
    elif req.provider == "zhipu":
        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        model = "glm-4"
    elif req.provider == "minimax":
        url = "https://api.minimax.chat/v1/chat/completions"
        model = "abab6.5s-chat"
    elif req.provider == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        model = "openai/gpt-4o-mini"
    else:
        return {"error": "Unsupported provider"}

    payload = {
        "model": model,
        "max_tokens": 2048,
        "stream": True,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": req.prompt}
        ]
    }

    async def stream_ai():
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    async for raw_line in resp.aiter_lines():
                        if not raw_line.startswith("data:"):
                            continue
                        data_str = raw_line[5:].strip()
                        if data_str == "[DONE]":
                            yield f"data: {json.dumps({'type': 'done'})}\n\n"
                            return
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield f"data: {json.dumps({'type': 'delta', 'content': delta})}\n\n"
                        except Exception:
                            pass
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(stream_ai(), media_type="text/event-stream")

async def run_scraper(platform, target, mode, count, download_videos=False, sort_by="1", time_filter=0, scrape_mode="safe"):
    adapter = ServerAdapter()

    # Reset control state for new scrape
    scrape_control.reset()
    await log_queue.put({"type": "SCRAPE_STARTED", "message": f"Starting scraper for {platform} - target: {target}, mode: {mode}, count: {count}, scrape_mode: {scrape_mode}"})

    try:
        scraper = None
        with platform_env(platform):
            if platform == "douyin":
                if mode == "keyword" and scrape_mode == "fast":
                    from douyin.scraper.keyword_fast import KeywordScraperFast
                    scraper = KeywordScraperFast(keyword=target, count=count, download_videos=download_videos, server=adapter, sort_by=sort_by, time_filter=time_filter)
                elif mode == "keyword":
                    from douyin.scraper.keyword import KeywordScraper
                    scraper = KeywordScraper(keyword=target, count=count, download_videos=download_videos, server=adapter, sort_by=sort_by, time_filter=time_filter)
                else:
                    from douyin.scraper.blogger import BloggerScraper
                    scraper = BloggerScraper(url_input=target, sort_mode="hot", count=count, download_videos=download_videos, server=adapter)

            elif platform == "tiktok":
                if mode == "keyword" and scrape_mode == "fast":
                    from tiktok.scraper.keyword_fast import KeywordScraperFast
                    scraper = KeywordScraperFast(keyword=target, count=count, download_videos=download_videos, server=adapter, sort_by=sort_by, time_filter=time_filter)
                elif mode == "keyword":
                    from tiktok.scraper.keyword import KeywordScraper
                    scraper = KeywordScraper(keyword=target, count=count, download_videos=download_videos, server=adapter, sort_by=sort_by, time_filter=time_filter)
                else:
                    from tiktok.scraper.blogger import BloggerScraper
                    scraper = BloggerScraper(url_input=target, sort_mode="hot", count=count, download_videos=download_videos, server=adapter)

            elif platform == "reddit":
                if mode == "keyword":
                    from reddit.scraper.keyword import KeywordScraper
                    scraper = KeywordScraper(keyword=target, count=count, download_videos=False, server=adapter)
                else:
                    from reddit.scraper.subreddit import SubredditScraper
                    scraper = SubredditScraper(url_input=target, sort_mode="hot", count=count, download_videos=False, server=adapter)

            elif platform == "youtube":
                if mode == "keyword":
                    from youtube.scraper.keyword import KeywordScraper
                    scraper = KeywordScraper(keyword=target, count=count, download_videos=download_videos, server=adapter)
                else:
                    from youtube.scraper.channel import ChannelScraper
                    scraper = ChannelScraper(channel_input=target, sort_mode="viewCount", count=count, download_videos=download_videos, server=adapter)

            elif platform == "x":
                if mode == "keyword":
                    from x.scraper.keyword import KeywordScraper
                    scraper = KeywordScraper(keyword=target, count=count, server=adapter)
                else:
                    from x.scraper.profile import ProfileScraper
                    scraper = ProfileScraper(user_input=target, count=count, server=adapter)

            else:
                await adapter._log(f"Platform {platform} not supported yet.")
                scrape_control.state = ScrapeControl.IDLE
                return

            import inspect
            if inspect.iscoroutinefunction(scraper.run) or inspect.iscoroutinefunction(getattr(scraper.__class__, 'run', None)):
                await scraper.run()
            else:
                await asyncio.get_event_loop().run_in_executor(None, scraper.run)

        scrape_control.state = ScrapeControl.IDLE
        await log_queue.put({"type": "SCRAPE_DONE", "message": f"[{platform}] Scraping complete!"})

    except ScrapeCancelled as e:
        scrape_control.state = ScrapeControl.IDLE
        await log_queue.put({"type": "SCRAPE_CANCELLED", "message": f"[已取消] {e}"})
    except Exception as e:
        scrape_control.state = ScrapeControl.IDLE
        err = traceback.format_exc()
        await log_queue.put({"type": "SCRAPE_DONE", "message": f"Error running scraper: {str(e)}\n{err}"})

@app.get("/api/logs")
async def sse_logs(request: Request):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                # Expect dict objects in log_queue now
                data = await asyncio.wait_for(log_queue.get(), timeout=1.0)
                yield f"data: {json.dumps(data)}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

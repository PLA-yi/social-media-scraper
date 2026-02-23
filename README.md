# Social Media Scraper Dashboard

A unified web dashboard for scraping **Douyin, TikTok, Reddit, X (Twitter), and YouTube** — built with FastAPI + Vue 3. All five scrapers are controlled from a single browser interface with real-time log streaming and an AI-powered comment analysis panel.

---

## Features

- **5 platforms in one UI** — Douyin, TikTok, Reddit, X, YouTube
- **Keyword search & profile/channel scraping** for each platform
- **Real-time terminal logs** streamed via SSE (no page refresh needed)
- **Manual intervention flow** — browser auto-opens for login/captcha; click Resume when done
- **AI chat analysis** — select up to 10 scraped datasets and chat with your comment data (streaming, token-by-token output)
- **Data management** — browse output folders, clean empty directories

---

## Quick Start

```bash
# 1. Install dependencies (per platform as needed)
pip install -r douyin/requirements.txt
pip install -r tiktok/requirements.txt
pip install -r reddit/requirements.txt
pip install -r x/requirements.txt
pip install -r youtube/requirements.txt

# 2. Start the server
python3 server.py

# 3. Open http://localhost:8000
```

**macOS one-click launch** (opens browser automatically):
```bash
./Start_Scraper.command
```

**Stop the server:**
```bash
kill -9 $(lsof -t -i :8000)
```

> YouTube also requires system-level `yt-dlp`: `brew install yt-dlp`

---

## Platform Overview

| Platform | Method | Auth |
|----------|--------|------|
| 抖音 (Douyin) | Playwright (Chromium) | Manual login → auto-saved cookies |
| TikTok | Playwright (Chromium) | Manual login → auto-saved cookies |
| Reddit | HTTP requests | Cookie-Editor browser export |
| X (Twitter) | twikit async client | Cookie-Editor browser export |
| YouTube | yt-dlp subprocess | No auth required |

---

## Data Output

Each run creates a timestamped folder under `data/`:

```
data/{label}_{YYYYMMDD_HHMMSS}/
├── videos.json / videos.csv        # Video/post/tweet metadata
├── all_comments.json / .csv        # All comments aggregated
└── comments/
    └── {item_id}.json              # Per-item comment files
```

---

## AI Analysis

The **AI Data Analysis** tab lets you load one or more `all_comments.json` files and ask questions about the data. Responses stream token-by-token.

Supported providers (bring your own API key):

| Provider | Model |
|----------|-------|
| Moonshot Kimi | `moonshot-v1-32k` |
| 智谱 ChatGLM | `glm-4` |
| MiniMax | `abab6.5s-chat` |
| OpenRouter | `openai/gpt-4o-mini` |

---

## Architecture

```
server.py          # FastAPI: routing, SSE logs, dynamic scraper loading
static/index.html  # Vue 3 + Tailwind CSS single-file UI (no build step)
data/              # All scraped output + shared cookies.json
douyin/ tiktok/ reddit/ x/ youtube/   # Platform scrapers
```

Key design patterns:
- **`platform_env()` context manager** — isolates `sys.path` and `sys.modules` per platform to prevent namespace collisions between the five `config`/`utils` modules
- **SSE log queue** — all `print()` replaced with `self._log()` → `asyncio.Queue` → `/api/logs` event stream
- **User intervention** — `request_user_intervention()` suspends the scraper and waits for the frontend Resume button instead of blocking `input()`

---

## Notes

- Python 3.10+ required (X/twikit uses `match` statements internally)
- Scraped data and `cookies.json` are excluded from this repository via `.gitignore`
- Playwright browsers must be installed: `playwright install chromium`

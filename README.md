# Social Media Scraper Dashboard

[中文版](./README.zh-CN.md)

A unified web dashboard for scraping **Douyin, TikTok, Reddit, X (Twitter), and YouTube** — built with FastAPI + Vue 3. All five scrapers are controlled from a single browser interface with real-time log streaming and an AI-powered comment analysis panel.

**Current version: v1.2.1**

---

## Features

- **5 platforms in one UI** — Douyin, TikTok, Reddit, X, YouTube
- **Keyword search & profile/channel scraping** for each platform
- **Safe mode & Fast mode** — Safe mode uses sequential browser scraping; Fast mode opens 3 concurrent browser tabs for ~3× speed (Douyin/TikTok keyword only)
- **Pause / Stop controls** — Pause and resume mid-run, or stop with data saved up to that point (Douyin/TikTok)
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

## Scrape Modes (Douyin / TikTok)

| Mode | How it works | Speed |
|------|-------------|-------|
| **Safe** | One browser tab, sequential per video | Baseline |
| **Fast** | 3 concurrent tabs in the same browser session | ~3× faster |

Both modes share the same login session and comment parsing logic. Fast mode requires no extra configuration.

### Pause / Stop

While a scrape is running, two control buttons appear in the UI:

- **⏸ Pause** — suspends the scrape (browser stays open); click again to resume
- **■ Stop** — terminates the run and saves all data collected so far

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
encrypt/           # Signature utilities (ABogus, XBogus, XGnarly)
douyin/ tiktok/ reddit/ x/ youtube/   # Platform scrapers
```

Key design patterns:
- **`platform_env()` context manager** — isolates `sys.path` and `sys.modules` per platform to prevent namespace collisions between the five `config`/`utils` modules
- **SSE log queue** — all `print()` replaced with `self._log()` → `asyncio.Queue` → `/api/logs` event stream
- **User intervention** — `request_user_intervention()` suspends the scraper and waits for the frontend Resume button instead of blocking `input()`
- **ScrapeControl state machine** — `idle / running / paused / stopped` states with `pause_event` and `stop_event` for cooperative cancellation

---

## Changelog

### v1.2.1
- **Fast scrape mode** (Douyin/TikTok keyword): 3 concurrent browser tabs in a shared session, ~3× speedup
- **Pause / Stop controls**: new `/api/pause` and `/api/stop` endpoints; UI buttons visible during active scrapes
- **Fix**: TikTok comment section now reliably opens (`data-e2e='comments'` added as primary click target, with retry logic)
- Added `encrypt/` package (ABogus, XBogus, XGnarly signature utilities)

### v1.2.0
- Unified FastAPI + Vue 3 dashboard replacing CLI-only workflow
- SSE real-time log streaming
- AI comment analysis panel (4 providers)
- Advanced search filters: sort by recency/popularity, time-window filtering

---

## Notes

- Python 3.10+ required (X/twikit uses `match` statements internally)
- Scraped data and `cookies.json` are excluded from this repository via `.gitignore`
- Playwright browsers must be installed: `playwright install chromium`

---

## License

[Apache License 2.0](./LICENSE)

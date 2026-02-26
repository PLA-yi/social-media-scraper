import os
import re
import json
import csv
from datetime import datetime


def parse_time_text_to_hours(time_text: str) -> float:
    """
    将视频/评论上显示的相对时间或短日期转换为距离现在的小时数。
    针对 TikTok 的常见英文时间格式进行解析。
    如果无法解析，则返回 -1.0
    """
    if not time_text:
        return -1.0

    text = str(time_text).strip().lower()

    if text in ("just now", "now"):
        return 0.0

    m = re.search(r'(\d+)\s*m(?:in)?(?:\s*ago)?', text) # e.g. "5m" or "5 min" or "5m ago"
    if m:
        return int(m.group(1)) / 60.0

    m = re.search(r'(\d+)\s*h(?:our|ours)?(?:\s*ago)?', text)
    if m:
        return float(m.group(1))

    m = re.search(r'(\d+)\s*d(?:ay|ays)?(?:\s*ago)?', text)
    if m:
        return float(m.group(1)) * 24.0

    m = re.search(r'(\d+)\s*w(?:eek|eeks)?(?:\s*ago)?', text)
    if m:
        return float(m.group(1)) * 168.0

    # Specific date e.g. "3-05" or "2023-12-25" or "12-25"
    m_date = re.search(r'(?:(\d{4})[-/])?\s*(\d{1,2})[-/]\s*(\d{1,2})', text)
    if m_date:
        now = datetime.now()
        year_str = m_date.group(1)
        month = int(m_date.group(2))
        day = int(m_date.group(3))
        year = int(year_str) if year_str else now.year

        try:
            target_date = datetime(year, month, day)
            if not year_str and target_date > now:
                target_date = datetime(year - 1, month, day)

            delta = now - target_date
            return max(0.0, delta.total_seconds() / 3600.0)
        except Exception:
            return -1.0

    return -1.0


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def safe_text(text) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def now_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_json(data, filepath: str):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  [保存] {filepath}")


def save_csv(rows: list, filepath: str):
    if not rows:
        return
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"  [保存] {filepath}")

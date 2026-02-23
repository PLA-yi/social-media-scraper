import os
import re
import json
import csv
from datetime import datetime


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

"""职位变化率监测脚本（时效性实验）。

每天对万行同一批列表页抓取一次职位清单，与前一天对比，
统计：新增、下架、仍在、更新日期变化，写入 churn_data/ 目录。
用于验证"招聘网站几天不变"的假设，决定产品定位（每日新闻 vs 静态目录）。

用法：python3 scripts/churn_probe.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date, datetime
from urllib.parse import urljoin

import urllib.request
import ssl

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "churn_data")
STATE_FILE = os.path.join(DATA_DIR, "churn_state.json")
HISTORY_FILE = os.path.join(DATA_DIR, "churn_history.json")

SEARCH_URL = "https://www.job910.com/job/search"
JOB_TYPES = [30, 10, 20, 40, 60, 70]
PAGES = 30
DELAY = 1.0

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers=HDRS)
    with urllib.request.urlopen(req, timeout=20, context=_CTX) as resp:
        return resp.read().decode("utf-8", "ignore")


def parse_list(html: str) -> list[dict]:
    """解析列表页职位卡片，返回 [{id, title, url, update_date}]。"""
    out = []
    # 以 job-item 卡片为单位切块解析
    items = re.split(r'<div class="job-item">', html)[1:]
    for block in items:
        m = re.search(r'/jobs_view_(\d+)\.html', block)
        if not m:
            continue
        jid = m.group(1)
        title_m = re.search(r'title="([^"]{4,80})"[^>]*>\s*[^<]*</a>', block) or \
                  re.search(r'class="left-name"[^>]*title="([^"]{4,80})"', block)
        title = title_m.group(1) if title_m else ""
        # 更新日期：列表卡片中 "更新于 08-06"
        date_m = re.search(r"更新于\s*</span>\s*([\d-]{5})", block) or \
                 re.search(r"(\d{2}-\d{2})", block)
        update_date = date_m.group(1) if date_m else ""
        out.append({"id": jid, "title": title, "url": f"https://www.job910.com/jobs_view_{jid}.html", "update_date": update_date})
    return out


def crawl_today() -> dict:
    """抓取全部类型页面，返回 {job_id: record}。"""
    records: dict[str, dict] = {}
    for jt in JOB_TYPES:
        for page in range(1, PAGES + 1):
            url = f"{SEARCH_URL}?jobType={jt}&pageIndex={page}"
            try:
                html = http_get(url)
            except Exception as e:  # noqa: BLE001
                print(f"  [{jt} p{page}] 失败: {e}", flush=True)
                continue
            for rec in parse_list(html):
                records[rec["id"]] = rec
            time.sleep(DELAY)
    return records


def load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def main() -> int:
    today = date.today().isoformat()
    print(f"[churn_probe] {datetime.now():%Y-%m-%d %H:%M:%S} 开始抓取 ...", flush=True)
    now_records = crawl_today()
    print(f"[churn_probe] 今日抓取 {len(now_records)} 个唯一职位", flush=True)

    prev = load_json(STATE_FILE, {})
    history = load_json(HISTORY_FILE, [])

    if prev:
        prev_ids = set(prev.keys())
        now_ids = set(now_records.keys())
        new_ids = now_ids - prev_ids
        gone_ids = prev_ids - now_ids
        common_ids = now_ids & prev_ids
        updated_dates = [
            jid for jid in common_ids
            if now_records[jid].get("update_date") and prev[jid].get("update_date")
            and now_records[jid]["update_date"] != prev[jid]["update_date"]
        ]
        record = {
            "date": today,
            "total": len(now_ids),
            "new": len(new_ids),
            "gone": len(gone_ids),
            "kept": len(common_ids),
            "update_date_changed": len(updated_dates),
            "new_sample": [now_records[j]["title"][:40] for j in list(new_ids)[:5]],
            "gone_sample": [prev[j]["title"][:40] for j in list(gone_ids)[:5]],
        }
        print(
            f"[churn_probe] 对比昨日: 新增 {record['new']} | 下架 {record['gone']} | "
            f"仍在 {record['kept']} | 更新日期变化 {record['update_date_changed']}",
            flush=True,
        )
    else:
        record = {
            "date": today,
            "total": len(now_records),
            "new": len(now_records),
            "gone": 0,
            "kept": 0,
            "update_date_changed": 0,
            "new_sample": [],
            "gone_sample": [],
            "note": "首日基线，无昨日可对比",
        }
        print(f"[churn_probe] 首日基线：{len(now_records)} 个职位", flush=True)

    history = [h for h in history if h.get("date") != today]
    history.append(record)
    history.sort(key=lambda h: h["date"])
    save_json(STATE_FILE, now_records)
    save_json(HISTORY_FILE, history)
    print(f"[churn_probe] 完成，历史记录 {len(history)} 天 -> {HISTORY_FILE}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""数据持久化：统一 JSON 文件 + 每日快照。"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from typing import Iterable

# 仓库根 = 本文件(crawler/storage.py)的上上级
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "crawler", "data")
WEB_DATA_DIR = os.path.join(REPO_ROOT, "web", "data")


def ensure_dirs() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(WEB_DATA_DIR, exist_ok=True)


def load_previous(path: str) -> list[dict]:
    """加载上一次抓取的记录（用于合并历史，保证增量去重）。"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def dedupe_by_url(records: Iterable[dict], max_age_days: int = 120) -> list[dict]:
    """按 url 去重，同链接保留最新；长期未再抓取的记录（超过 max_age_days）剔除。

    注意：用 crawl_date（抓取时间）判断新旧与过期，而不是 publish_date——
    招聘公告可能在 4 月发布但 8 月仍在报名期内，按发布时间剔除会误杀有效岗位。
    """
    seen: dict[str, dict] = {}
    today = datetime.now(timezone.utc).date()
    for r in records:
        url = (r.get("url") or "").strip()
        if not url:
            continue
        # 清理长期未抓取到的记录
        crawl = r.get("crawl_date") or ""
        if crawl:
            try:
                d = datetime.strptime(crawl[:10], "%Y-%m-%d").date()
                if (today - d).days > max_age_days:
                    continue
            except ValueError:
                pass
        old = seen.get(url)
        if old is None or (r.get("crawl_date") or "") > (old.get("crawl_date") or ""):
            seen[url] = r
    return list(seen.values())


def save_json(path: str, obj) -> None:
    ensure_dirs()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        # 紧凑格式（不缩进），显著减小文件体积
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def write_outputs(records: list[dict], run_info: dict) -> dict:
    """写出 web/data/jobs.json（前端用）与 crawler/data/ 每日快照。"""
    ensure_dirs()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    sorted_records = sorted(
        records,
        key=lambda r: (r.get("publish_date") or "", r.get("crawl_date") or ""),
        reverse=True,
    )

    def to_frontend(r: dict) -> dict:
        out = {
            "title": r.get("title", ""),
            "school": r.get("school", ""),
            "province": r.get("province", ""),
            "city": r.get("city", ""),
            "education": r.get("education", ""),
            "experience": r.get("experience", ""),
            "salary_text": r.get("salary_text", ""),
            "subject": r.get("subject", ""),
            "school_level": r.get("school_level", ""),
            "source": r.get("source", ""),
            "source_label": r.get("source_label", ""),
            "url": r.get("url", ""),
            "deadline": r.get("deadline", ""),
            "publish_date": r.get("publish_date", ""),
            "crawl_date": r.get("crawl_date", ""),
            # 是否今天新抓取（用于"今日新增"标记与筛选）
            "is_new": r.get("crawl_date", "") == today,
        }
        summary = (r.get("summary") or "").strip()
        if summary:
            out["summary"] = summary[:120]
        return out

    updated_at = run_info.get("updated_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))

    # 按来源拆分文件，避免单文件过大、便于前端并行加载
    by_source: dict[str, list[dict]] = {}
    for r in sorted_records:
        by_source.setdefault(r.get("source", "other"), []).append(to_frontend(r))

    jobs_paths: dict[str, str] = {}
    total = 0
    for src, jobs in by_source.items():
        total += len(jobs)
        payload = {
            "updated_at": updated_at,
            "source": src,
            "count": len(jobs),
            "jobs": jobs,
        }
        path = os.path.join(WEB_DATA_DIR, f"jobs-{src}.json")
        save_json(path, payload)
        jobs_paths[src] = path

    # 汇总文件（兼容旧版/便于快速查看总量）
    frontend_payload = {
        "updated_at": updated_at,
        "source_summary": run_info.get("source_summary", {}),
        "count": total,
        "jobs": [to_frontend(r) for r in sorted_records],
        "source_files": {k: f"jobs-{k}.json" for k in by_source},
    }
    jobs_path = os.path.join(WEB_DATA_DIR, "jobs.json")
    save_json(jobs_path, frontend_payload)

    # 每日快照（保留最近 14 天，其余清理，控制仓库体积）
    snapshot_path = os.path.join(DATA_DIR, f"snapshot-{today}.json")
    if not os.path.exists(snapshot_path):
        save_json(snapshot_path, sorted_records)
    _cleanup_old_snapshots(keep_days=14)

    return {"frontend_path": jobs_path, "snapshot_path": snapshot_path, "count": len(sorted_records), "source_files": jobs_paths}


def _cleanup_old_snapshots(keep_days: int = 14) -> None:
    files = [f for f in os.listdir(DATA_DIR) if f.startswith("snapshot-") and f.endswith(".json")]
    files.sort()
    for f in files[:-keep_days]:
        try:
            os.remove(os.path.join(DATA_DIR, f))
        except OSError:
            pass


def write_province_counts(records: list[dict]) -> str:
    """生成按省份统计的 JSON，供前端地图/统计使用。"""
    counts: dict[str, int] = {}
    for r in records:
        p = r.get("province") or "未知"
        counts[p] = counts.get(p, 0) + 1
    obj = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": counts,
    }
    path = os.path.join(WEB_DATA_DIR, "province-counts.json")
    save_json(path, obj)
    return path

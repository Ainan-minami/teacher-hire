"""爬虫运行器：调度各数据源、合并去重、写前端数据。"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone

# 保证 `python -m crawler.runner`（从仓库根目录运行）或直接 `python crawler/runner.py` 都可用
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from crawler.sources import config as source_config
from crawler.storage import (
    dedupe_by_url,
    write_outputs,
    write_province_counts,
)


@dataclass
class RunContext:
    """传递给各数据源模块的上下文。"""

    sources: dict = field(default_factory=lambda: source_config.SOURCES)
    source_status: dict = field(default_factory=dict)
    failures: list = field(default_factory=list)
    shallow: bool = False

    def record_status(self, name: str, ok: bool, count: int, message: str = "") -> None:
        self.source_status[name] = {
            "ok": ok,
            "count": count,
            "message": message[:200],
            "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def record_failure(self, name: str, exc: Exception) -> None:
        self.failures.append({"source": name, "error": str(exc)[:300]})
        traceback.print_exc()


def load_source(name: str):
    return importlib.import_module(f"crawler.sources.{name}")


def run_all(only: list[str] | None = None, shallow: bool = False) -> dict:
    ctx = RunContext(shallow=shallow)
    merged: list[dict] = []

    # 从上次快照恢复历史记录（保证跨日增量去重）
    from crawler.storage import DATA_DIR, load_previous
    snapshot_dir = DATA_DIR
    history: list[dict] = []
    if os.path.isdir(snapshot_dir):
        snaps = sorted(f for f in os.listdir(snapshot_dir) if f.startswith("snapshot-") and f.endswith(".json"))
        for snap in snaps[-1:]:
            history.extend(load_previous(os.path.join(snapshot_dir, snap)))
    merged.extend(history)

    for name, cfg in ctx.sources.items():
        if only and name not in only:
            continue
        if not cfg.get("enabled", True):
            continue
        started = time.time()
        try:
            module = load_source(name)
            records = module.run(ctx)
            merged.extend(records)
            ctx.record_status(name, True, len(records), f"{time.time()-started:.1f}s")
            print(f"[{name}] 新增 {len(records)} 条, 累计 {len(merged)} 条")
        except Exception as e:  # noqa: BLE001 - 单源失败不中断整体
            ctx.record_status(name, False, 0, str(e)[:200])
            ctx.record_failure(name, e)
            print(f"[{name}] 失败: {e}")

    # 统一填充抓取日期（用于跨日增量去重与"最后活跃"展示）
    crawl_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for r in merged:
        if not r.get("crawl_date"):
            r["crawl_date"] = crawl_date
        # 剔除已下线数据源的历史记录（如曾被替换的 bing 聚合）
        if r.get("source") not in ctx.sources:
            r["_dropped"] = True
    merged = [r for r in merged if not r.get("_dropped")]

    records = dedupe_by_url(merged, max_age_days=120)
    print(f"去重后共 {len(records)} 条")

    run_info = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_summary": ctx.source_status,
        "failures": ctx.failures,
    }
    paths = write_outputs(records, run_info)
    province_path = write_province_counts(records)

    # 把运行摘要同时写到 web/data/meta.json，便于前端展示"最近更新/来源健康度"
    meta = {
        "updated_at": run_info["updated_at"],
        "count": len(records),
        "source_summary": ctx.source_status,
    }
    from crawler.storage import save_json
    meta_path = os.path.join(os.path.dirname(paths["frontend_path"]), "meta.json")
    save_json(meta_path, meta)

    print(f"前端数据: {paths['frontend_path']} ({paths['count']} 条)")
    print(f"省份统计: {province_path}")
    return {"records": records, "info": run_info, "paths": paths}


def main() -> int:
    parser = argparse.ArgumentParser(description="教师招聘信息聚合爬虫")
    parser.add_argument("--only", nargs="*", help="只运行指定源，如 --only job910 bing")
    parser.add_argument("--shallow", action="store_true", help="浅抓取（减少页数，适合本地测试）")
    args = parser.parse_args()

    result = run_all(only=args.only, shallow=args.shallow)
    failed = [s for s, st in result["info"]["source_summary"].items() if not st["ok"]]
    if failed:
        print("警告：以下数据源失败 ->", failed)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())

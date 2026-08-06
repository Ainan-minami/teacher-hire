"""数据源爬虫模块。

每个模块实现 `run(ctx)`，ctx 为 `crawler.runner.RunContext`，
返回 `list[dict]`（统一 schema 的原始记录）。
"""

"""应届生招聘网（yjszp.com）爬虫。

首页即每日招聘公告流（约 30 条/页，`?page=N` 分页），
覆盖高校、中小学、事业单位等大量教师相关岗位。抓取后按关键词过滤教师岗。
"""

from __future__ import annotations

import re
from hashlib import md5
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from crawler.clean import (
    clean_text,
    extract_city,
    extract_deadline,
    extract_education,
    extract_experience,
    extract_salary,
    extract_school_level,
    extract_subject,
    guess_province,
    parse_chinese_date,
)
from crawler.fetch import FetchError, http_get, polite_delay
from crawler.sources import config as source_config

BASE = "https://www.yjszp.com"
HOME_URL = f"{BASE}/"

# 教师相关关键词（标题命中任一即保留）
TEACHER_KEYWORDS = [
    "教师", "老师", "教师招聘", "招聘教师", "教育系统", "教育局",
    "师范", "中小学", "职业院校", "职业学院", "中学", "小学", "幼儿园",
    "学院", "大学", "高校", "高教",
]
# 明确非教师类关键词（排除）
SKIP_KEYWORDS = ["供电局", "医院", "卫生院", "银行", "供电", "施工", "车间", "护理", "医生"]


def run(ctx) -> list[dict]:
    cfg = source_config.SOURCES["yjszp"]
    pages = cfg.get("pages")
    if ctx.shallow:
        pages = min(pages, 1)

    records: list[dict] = []
    seen: set[str] = set()
    for page in range(1, pages + 1):
        url = HOME_URL if page == 1 else f"{HOME_URL}?page={page}"
        try:
            html = http_get(url, delay=cfg["delay"])
        except FetchError as e:
            print(f"  [yjszp] 第{page}页失败: {e}")
            break
        items = _parse_list(html)
        if not items:
            break
        for it in items:
            if it["id"] not in seen:
                seen.add(it["id"])
                records.append(it)
        polite_delay(cfg["delay"], 0.3)
    return records


def _parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for a in soup.select("a[href*='/job/info/']"):
        href = a.get("href", "")
        title = clean_text(a.get_text(" ", strip=True))
        if not title or len(title) < 6:
            continue
        if not any(k in title for k in TEACHER_KEYWORDS):
            continue
        if any(k in title for k in SKIP_KEYWORDS):
            continue
        url = urljoin(BASE, href)
        text = title
        city = extract_city(text) or ""
        province = guess_province(text, city)
        # 标题里的日期如 "2026年XX招聘公告"
        pub = parse_chinese_date(text) or ""
        record = {
            "id": md5(url.encode("utf-8")).hexdigest()[:16],
            "title": title,
            "school": "",
            "url": url,
            "source": "yjszp",
            "source_label": source_config.SOURCE_LABELS["yjszp"],
            "province": province or "",
            "city": city or "",
            "education": extract_education(text) or "",
            "experience": extract_experience(text) or "",
            "salary": extract_salary(text) or "",
            "salary_text": "",
            "subject": extract_subject(text) or "",
            "school_level": extract_school_level(text) or "",
            "deadline": extract_deadline(text) or "",
            "publish_date": pub,
            "crawl_date": "",
            "summary": title[:160],
        }
        out.append(record)
    return out

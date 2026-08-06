"""教育部人才服务网（jybzp.chsi.com.cn）爬虫。

公告列表为表单 POST 分页（hidden input start 偏移），
每页 10 条，含标题、链接、发布日期。权威性高，覆盖教育部直属单位与高校。
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
from crawler.fetch import FetchError, http_post, polite_delay
from crawler.sources import config as source_config

BASE = "https://jybzp.chsi.com.cn"
LIST_URL = f"{BASE}/home/bul/announcement"


def run(ctx) -> list[dict]:
    cfg = source_config.SOURCES["jybzp"]
    pages = cfg.get("pages")
    if ctx.shallow:
        pages = min(pages, 1)

    records: list[dict] = []
    seen: set[str] = set()
    for category in cfg["categories"]:
        for page in range(pages):
            try:
                html = http_post(
                    LIST_URL,
                    data={"sourcetyp": category, "start": page * 10},
                    delay=cfg["delay"],
                )
            except FetchError as e:
                print(f"  [jybzp] {category} 第{page+1}页失败: {e}")
                break
            items = _parse_list(html, category)
            if not items:
                break
            for it in items:
                if it["id"] not in seen:
                    seen.add(it["id"])
                    records.append(it)
            polite_delay(cfg["delay"], 0.3)
    return records


def _parse_list(html: str, category: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for li in soup.select("ul.col-list li"):
        a = li.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        if "/home/bul/announcement/" not in href:
            continue
        title = clean_text(a.get_text(" ", strip=True))
        url = urljoin(BASE, href)
        date_el = li.find("span", class_="time")
        date_text = clean_text(date_el.get_text(" ", strip=True)) if date_el else ""
        pub = parse_chinese_date(date_text) or ""

        full_text = f"{title} {date_text} 教育部直属单位高校 招聘"
        city = extract_city(full_text) or ""
        province = guess_province(full_text, city)
        record = {
            "id": md5(url.encode("utf-8")).hexdigest()[:16],
            "title": title,
            "school": "",
            "url": url,
            "source": "jybzp",
            "source_label": source_config.SOURCE_LABELS["jybzp"],
            "province": province or "",
            "city": city or "",
            "education": extract_education(full_text) or "",
            "experience": extract_experience(full_text) or "",
            "salary": extract_salary(full_text) or "",
            "salary_text": "",
            "subject": extract_subject(full_text) or "",
            "school_level": extract_school_level(full_text) or "",
            "deadline": extract_deadline(full_text) or "",
            "publish_date": pub,
            "crawl_date": "",
            "summary": f"教育部人才服务网公告（{category}）",
        }
        out.append(record)
    return out

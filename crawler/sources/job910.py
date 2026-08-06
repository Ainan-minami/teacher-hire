"""万行教师人才网（job910.com）爬虫。

抓取策略：搜索列表页（jobType=30 教师类全量 / 10 民办中小学）的 HTML，
列表卡片自带 职位、学校、城市、薪资、学历、经验、更新日期 等结构化字段，
无需进入详情页，成本低且稳定。分页参数 pageIndex 经实测有效。
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

BASE = "https://www.job910.com"
SEARCH_URL = "https://www.job910.com/job/search"


def run(ctx) -> list[dict]:
    cfg = source_config.SOURCES["job910"]
    pages = cfg.get("pages")
    if ctx.shallow:
        pages = min(pages, 1)

    records: list[dict] = []
    seen_ids: set[str] = set()
    for job_type in cfg["job_types"]:
        for page in range(1, pages + 1):
            url = f"{SEARCH_URL}?jobType={job_type}&pageIndex={page}"
            try:
                html = http_get(url, delay=cfg["delay"])
            except FetchError as e:
                print(f"  [job910] 第{page}页失败: {e}")
                break
            items = _parse_list(html, url)
            if not items:
                break  # 列表为空或已到底
            for it in items:
                jid = it["id"]
                if jid not in seen_ids:
                    seen_ids.add(jid)
                    records.append(it)
            polite_delay(cfg["delay"], 0.4)
    return records


def _parse_list(html: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for item in soup.select("div.job-item"):
        try:
            title_a = item.select_one("a.left-name[href*='jobs_view']")
            if not title_a:
                continue
            href = title_a.get("href", "")
            url = urljoin(BASE, href)
            jid = re.search(r"jobs_view_(\d+)", href)
            if not jid:
                continue
            job_id = jid.group(1)

            title = clean_text(title_a.get_text(" ", strip=True))
            school_a = item.select_one("a.left-name[href*='school_view']")
            school = clean_text(school_a.get_text(" ", strip=True)) if school_a else ""

            lis = [clean_text(li.get_text(" ", strip=True)) for li in item.select("ul.content-left-2-left li")]
            # lis[0]=薪资 lis[1]=城市 lis[2]=学历 lis[3]=经验
            salary_raw = lis[0] if len(lis) > 0 else ""
            city_raw = lis[1] if len(lis) > 1 else ""
            edu_raw = lis[2] if len(lis) > 2 else ""
            exp_raw = lis[3] if len(lis) > 3 else ""

            tags = [
                clean_text(t.get_text(" ", strip=True))
                for t in item.select("div.content-left-3 p")
            ]
            tag_text = " ".join(t for t in tags if t)

            time_el = item.select_one("p.left-time")
            date_text = clean_text(time_el.get_text(" ", strip=True)) if time_el else ""
            pub = parse_chinese_date(date_text)
            if not pub:
                m = re.search(r"(?<!\d)(\d{2})-(\d{2})(?!\d)", date_text)
                if m:
                    year = _infer_year(int(m.group(1)), int(m.group(2)))
                    pub = f"{year}-{m.group(1)}-{m.group(2)}"

            full_text = f"{title} {school} {city_raw} {salary_raw} {edu_raw} {exp_raw} {tag_text}"
            city = extract_city(full_text) or city_raw
            province = guess_province(full_text, city)

            record = {
                "id": f"job910-{job_id}",
                "title": title,
                "school": school,
                "url": url,
                "source": "job910",
                "source_label": source_config.SOURCE_LABELS["job910"],
                "province": province or "",
                "city": city or "",
                "education": extract_education(full_text) or "",
                "experience": extract_experience(full_text) or "",
                "salary": extract_salary(salary_raw) or "",
                "salary_text": salary_raw,
                "subject": extract_subject(full_text) or "",
                "school_level": extract_school_level(full_text) or "",
                "deadline": extract_deadline(full_text) or "",
                "publish_date": pub or "",
                "crawl_date": "",
                "summary": tag_text or clean_text(item.get_text(" ", strip=True))[:120],
            }
            # 统一用 md5(url) 作为稳定主键
            record["id"] = md5(url.encode("utf-8")).hexdigest()[:16]
            out.append(record)
        except Exception as e:  # noqa: BLE001 - 单条解析失败跳过
            print(f"  [job910] 解析单条失败: {e}")
            continue
    return out


def _infer_year(month: int, day: int) -> int:
    """'08-06' 这类短日期：默认当年，若日期在未来则视为去年。"""
    from datetime import date

    today = date.today()
    try:
        d = date(today.year, month, day)
    except ValueError:
        return today.year
    if (d - today).days > 30:
        return today.year - 1
    return today.year

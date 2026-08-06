"""省教育厅/人事考试网公告通用爬虫。

策略：每个站先抓首页，找到"公告/通知/招聘"等列表入口；
再抓列表页前 N 页，按教师关键词过滤公告标题。
各站结构差异大，因此全部用通用启发式（链接文本+URL 日期特征），
单个站点失败不影响其他站点。
"""

from __future__ import annotations

import json
import os
import re
from hashlib import md5
from urllib.parse import urljoin, urlparse

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

# 已确认可达的省教育厅 / 人事考试 / 教育考试院站点
SITES = [
    {"name": "浙江人事考试", "home": "http://www.zjks.com/", "province": "浙江"},
    {"name": "广东教育考试院", "home": "https://eea.gd.gov.cn/", "province": "广东"},
    {"name": "湖北教育考试院", "home": "http://www.hbea.edu.cn/", "province": "湖北"},
    {"name": "湖北省教育厅", "home": "http://jyt.hubei.gov.cn/", "province": "湖北"},
    {"name": "福建省教育厅", "home": "http://jyt.fujian.gov.cn/", "province": "福建"},
    {"name": "辽宁省教育厅", "home": "http://jyt.ln.gov.cn/", "province": "辽宁"},
    {"name": "江西省教育厅", "home": "http://jyt.jiangxi.gov.cn/", "province": "江西"},
    {"name": "广西教育厅", "home": "http://jyt.gxzf.gov.cn/", "province": "广西"},
    {"name": "重庆市教委", "home": "http://jw.cq.gov.cn/", "province": "重庆"},
    {"name": "贵州省教育厅", "home": "http://jyt.guizhou.gov.cn/", "province": "贵州"},
    {"name": "云南省教育厅", "home": "https://jyt.yn.gov.cn/", "province": "云南"},
    {"name": "天津市教委", "home": "http://jy.tj.gov.cn/", "province": "天津"},
    {"name": "新疆教育厅", "home": "http://jyt.xinjiang.gov.cn/", "province": "新疆"},
    {"name": "吉林省人事考试", "home": "http://www.jlzkb.com/", "province": "吉林"},
]

# 首页找列表入口的关键词
LIST_KEYWORDS = ["公告", "通知", "招聘", "招考", "公示", "动态"]
# 公告标题教师招聘相关性关键词（必须命中其一）
TEACHER_KEYWORDS = [
    "教师招聘", "招聘教师", "教师公开", "招聘公告", "招聘简章", "公开招聘",
    "教师招聘考试", "特岗教师", "招聘教师公告", "招聘教师简章",
    "教师岗位", "招聘岗位", "教师岗", "教师招考", "招教",
    "教师选聘", "选聘教师", "教师引进", "引进教师", "人才引进",
]
# 排除非招聘内容
SKIP_KEYWORDS = [
    "高考", "中考", "分数线", "志愿填报", "自学考试", "成绩查询", "录取",
    "考研", "招生章程", "普通话", "教师资格证考试", "考试报名", "考前提醒",
    "成绩公布", "培训", "会议", "工作推进", "表彰", "公示名单", "拟加分",
    "答题卡", "试卷", "志愿征集", "投档",
]

# 列表入口缓存文件（避免每次从首页重新发现）
_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".prov_list_cache.json")


def run(ctx) -> list[dict]:
    cfg = source_config.SOURCES["prov_bureau"]
    cache = _load_cache()
    records: list[dict] = []
    seen: set[str] = set()

    for site in SITES:
        home = site["home"]
        try:
            list_urls = cache.get(home)
            if not list_urls:
                list_urls = _discover_list_urls(home, cfg["delay"])
                if list_urls:
                    cache[home] = list_urls
            items = _crawl_list_urls(site, list_urls, cfg["max_pages"], cfg["delay"])
            for it in items:
                if it["id"] not in seen:
                    seen.add(it["id"])
                    records.append(it)
            print(f"  [prov_bureau] {site['name']}: {len(items)} 条")
        except Exception as e:  # noqa: BLE001 - 单站失败不影响整体
            print(f"  [prov_bureau] {site['name']} 失败: {e}")
    _save_cache(cache)
    return records


def _load_cache() -> dict:
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict) -> None:
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def _discover_list_urls(home: str, delay: float) -> list[str]:
    """从首页锚文本中找到列表入口 URL。"""
    try:
        html = http_get(home, delay=delay)
    except FetchError:
        return []
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for a in soup.find_all("a", href=True):
        text = clean_text(a.get_text(" ", strip=True))
        href = a["href"]
        if not text or not href or href.startswith(("javascript", "#", "mailto", "http://www.gov.cn")):
            continue
        if any(k in text for k in LIST_KEYWORDS) and len(text) <= 12:
            url = urljoin(home, href)
            if url not in found:
                found.append(url)
    return found[:6]


def _crawl_list_urls(site: dict, list_urls: list[str], max_pages: int, delay: float) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for list_url in list_urls:
        for page in range(1, max_pages + 1):
            url = _page_url(list_url, page)
            try:
                html = http_get(url, delay=delay)
            except FetchError:
                break
            items = _parse_list_page(html, site)
            if not items:
                break
            for it in items:
                if it["id"] not in seen:
                    seen.add(it["id"])
                    out.append(it)
            polite_delay(delay, 0.3)
    return out


def _page_url(list_url: str, page: int) -> str:
    """尝试常见分页格式：index_N.html / ?page=N / index.html。"""
    if page == 1:
        return list_url
    if "index.html" in list_url:
        return list_url.replace("index.html", f"index_{page}.html")
    if list_url.endswith("/"):
        return f"{list_url}index_{page}.html"
    return f"{list_url}?page={page}"


def _parse_list_page(html: str, site: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for a in soup.find_all("a", href=True):
        title = clean_text(a.get_text(" ", strip=True))
        href = a["href"]
        if not title or len(title) < 8 or len(title) > 80:
            continue
        if not any(k in title for k in TEACHER_KEYWORDS):
            continue
        if any(k in title for k in SKIP_KEYWORDS):
            continue
        if not _looks_like_article_url(href):
            continue
        url = urljoin(site["home"], href)
        text = title
        city = extract_city(text) or ""
        province = guess_province(text, city) or site.get("province", "")
        record = {
            "id": md5(url.encode("utf-8")).hexdigest()[:16],
            "title": title,
            "school": "",
            "url": url,
            "source": "prov_bureau",
            "source_label": source_config.SOURCE_LABELS["prov_bureau"],
            "province": province,
            "city": city,
            "education": extract_education(text) or "",
            "experience": extract_experience(text) or "",
            "salary": extract_salary(text) or "",
            "salary_text": "",
            "subject": extract_subject(text) or "",
            "school_level": extract_school_level(text) or "",
            "deadline": extract_deadline(text) or "",
            "publish_date": parse_chinese_date(text) or "",
            "crawl_date": "",
            "summary": f"{site['name']}公告：{title[:120]}",
        }
        out.append(record)
    return out


def _looks_like_article_url(href: str) -> bool:
    """公告 URL 一般带日期或 .html/.shtml 后缀。"""
    if re.search(r"/20\d{2}[-/]", href):
        return True
    if re.search(r"t20\d{2}", href):
        return True
    path = urlparse(href).path
    return path.endswith((".html", ".shtml", ".htm"))

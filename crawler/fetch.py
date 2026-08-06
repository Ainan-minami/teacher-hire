"""网络请求公共层。

只用标准库 urllib（GitHub Actions 与本地均可运行），
内置重试、超时、UA 伪装与节流，避免引入 requests 依赖。
"""

from __future__ import annotations

import random
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE  # 部分站点证书链不完整，抓公开信息时放宽校验


class FetchError(RuntimeError):
    """网络/解析类错误的统一包装，便于上层统计失败原因。"""


def http_get(
    url: str,
    *,
    headers: Optional[dict] = None,
    timeout: int = 20,
    retries: int = 2,
    delay: float = 0.8,
    encoding: Optional[str] = None,
    max_bytes: int = 3_000_000,
) -> str:
    """GET 并返回解码后的文本。

    encoding 为 None 时优先使用响应头/HTML 声明的编码，否则按 UTF-8。
    """
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": DEFAULT_UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "Referer": "https://www.google.com/",
                    **(headers or {}),
                },
            )
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
                raw = resp.read(max_bytes)
                enc = encoding
                if enc is None:
                    enc = resp.headers.get_content_charset()
                if enc is None:
                    enc = detect_charset(raw)
                try:
                    return raw.decode(enc or "utf-8", "ignore")
                except (LookupError, UnicodeDecodeError):
                    return raw.decode("utf-8", "ignore")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(delay * (attempt + 1) + random.uniform(0, 0.4))
    raise FetchError(f"GET 失败: {url} -> {last_err}")


def http_post(
    url: str,
    data: dict,
    *,
    headers: Optional[dict] = None,
    timeout: int = 20,
    retries: int = 2,
    delay: float = 0.8,
    encoding: Optional[str] = None,
    max_bytes: int = 3_000_000,
) -> str:
    """表单 POST 并返回解码后的文本。"""
    last_err: Optional[Exception] = None
    body = urllib.parse.urlencode(data).encode("utf-8")
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "User-Agent": DEFAULT_UA,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    **(headers or {}),
                },
            )
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
                raw = resp.read(max_bytes)
                enc = encoding
                if enc is None:
                    enc = resp.headers.get_content_charset()
                if enc is None:
                    enc = detect_charset(raw)
                try:
                    return raw.decode(enc or "utf-8", "ignore")
                except (LookupError, UnicodeDecodeError):
                    return raw.decode("utf-8", "ignore")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(delay * (attempt + 1) + random.uniform(0, 0.4))
    raise FetchError(f"POST 失败: {url} -> {last_err}")


def detect_charset(raw: bytes) -> Optional[str]:
    """从 HTML 前 2KB 中探测 charset 声明。"""
    head = raw[:2048].decode("utf-8", "ignore")
    for token in ('charset="utf-8"', "charset=utf-8", "charset=gb2312", "charset=gbk",
                  'charset="gb2312"', 'charset="gbk"', "charset=gb18030", 'charset="gb18030"'):
        if token in head.lower():
            return token.split("=")[-1].strip('"')
    return None


def polite_delay(seconds: float = 1.2, jitter: float = 0.5) -> None:
    """请求间礼貌延迟，避免对目标站点造成压力。"""
    time.sleep(seconds + random.uniform(0, jitter))

# -*- coding: utf-8 -*-
"""Strict network policy built on the run-scoped shared transport."""

from __future__ import annotations

import concurrent.futures
import re
import subprocess
import threading
import time
from contextlib import contextmanager
from urllib.parse import urljoin, urlparse

import requests

from .transport import (
    DEFAULT_TRANSPORT,
    FetchedText,
    MAX_BODY_BYTES,
    canonical_url,
    same_origin,
)

# Compatibility transport is opt-in by exact normalized URL only. New sites
# must be verified before being added here; all other URLs keep strict TLS.
CURL_COMPATIBILITY_URLS: frozenset[str] = frozenset(
    {"https://7.www113368a.com:2053/gengxin/58.html"}
)
INSECURE_TLS_COMPATIBILITY_URLS: frozenset[str] = frozenset()
PERMANENT_HTTP_STATUSES = frozenset({400, 401, 403, 404, 405, 410})
TRANSIENT_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524})
_RUN_SCOPE_LOCK = threading.RLock()
_RUN_SCOPE_DEPTH = 0


class FetchError(RuntimeError):
    """A classified network failure that can be written to the failure TXT."""


@contextmanager
def run_transport_scope():
    """Keep URL/browser state inside one formal run, with nested multi-period reuse."""
    global _RUN_SCOPE_DEPTH
    _RUN_SCOPE_LOCK.acquire()
    outermost = _RUN_SCOPE_DEPTH == 0
    _RUN_SCOPE_DEPTH += 1
    try:
        if outermost:
            DEFAULT_TRANSPORT.clear()
        yield
    finally:
        _RUN_SCOPE_DEPTH -= 1
        try:
            if outermost:
                DEFAULT_TRANSPORT.clear()
                DEFAULT_TRANSPORT.close()
        finally:
            _RUN_SCOPE_LOCK.release()


def decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "big5"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _status_code(exc: Exception) -> int | None:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code
    return None


def is_transient_fetch_error(exc: Exception) -> bool:
    status = _status_code(exc)
    if status is not None:
        return status in TRANSIENT_HTTP_STATUSES
    return isinstance(
        exc,
        (
            requests.Timeout,
            requests.ConnectionError,
            requests.exceptions.SSLError,
            ConnectionResetError,
            TimeoutError,
            OSError,
        ),
    )


def should_retry_fetch_error(error: FetchError) -> bool:
    message = str(error)
    status_match = re.match(r"^HTTP\s+(\d{3})\b", message)
    if status_match and int(status_match.group(1)) in PERMANENT_HTTP_STATUSES:
        return False
    return "单站总超时" not in message


def _failure_message(exc: Exception) -> str:
    status = _status_code(exc)
    if status is not None:
        return f"HTTP {status}：{exc}"
    if isinstance(exc, requests.Timeout) or "timed out" in str(exc).lower():
        return f"访问超时：{exc}"
    if isinstance(exc, requests.exceptions.SSLError) or "ssl" in str(exc).lower() or "tls" in str(exc).lower():
        return f"SSL/TLS 抓取失败：{exc}"
    if isinstance(exc, requests.ConnectionError):
        return f"连接失败：{exc}"
    return f"网络抓取失败：{type(exc).__name__}: {exc}"


def _request_timeout(timeout: int, deadline: float | None) -> int:
    if timeout < 1:
        raise ValueError("单请求超时必须大于 0")
    if deadline is None:
        return timeout
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise FetchError("单站总超时：已停止后续请求")
    return max(1, min(timeout, int(remaining)))


def curl_command(url: str, timeout: int, verify_ssl: bool) -> list[str]:
    command = [
        "curl.exe",
        "--fail",
        "--silent",
        "--show-error",
        "--compressed",
        "--http1.1",
        "--connect-timeout",
        str(min(10, timeout)),
        "--max-time",
        str(timeout),
        "--max-filesize",
        str(MAX_BODY_BYTES),
        "--write-out",
        "\n__BANTOU_CURL_META__%{http_code}\t%{redirect_url}\t%{url_effective}",
        "-A",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "-H",
        "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
    ]
    if not verify_ssl:
        command.append("-k")
    return command + [url]


def fetch_with_curl(
    url: str,
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
) -> str:
    requested_url = canonical_url(url)
    current_url = requested_url
    redirect_chain: list[str] = []
    marker = b"\n__BANTOU_CURL_META__"
    for _hop in range(6):
        request_timeout = _request_timeout(timeout, deadline)
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                curl_command(current_url, request_timeout, verify_ssl),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=request_timeout + 5,
                check=False,
            )
        except FileNotFoundError as exc:
            raise FetchError("兼容 TLS 兜底失败：系统找不到 curl.exe") from exc
        except subprocess.TimeoutExpired as exc:
            raise FetchError(f"兼容 TLS 兜底超时：{exc}") from exc
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            raise FetchError(
                f"兼容 TLS 兜底失败：curl exit {completed.returncode}: {stderr}"
            )
        if marker not in completed.stdout:
            raise FetchError("兼容 TLS 兜底失败：curl 缺少响应元数据")
        body, raw_meta = completed.stdout.rsplit(marker, 1)
        if len(body) > MAX_BODY_BYTES:
            raise FetchError(
                f"兼容 TLS 兜底失败：响应正文超过 {MAX_BODY_BYTES} 字节上限"
            )
        meta = raw_meta.decode("utf-8", errors="replace").strip().split("\t")
        if len(meta) != 3 or not meta[0].isdigit():
            raise FetchError("兼容 TLS 兜底失败：curl 响应元数据无效")
        status = int(meta[0])
        redirect_url = meta[1].strip()
        effective_url = canonical_url(meta[2].strip() or current_url)
        if status in {301, 302, 303, 307, 308}:
            if not redirect_url:
                raise FetchError(f"兼容 TLS 兜底失败：HTTP {status} 缺少跳转地址")
            destination = canonical_url(urljoin(effective_url, redirect_url))
            if not same_origin(requested_url, destination):
                raise FetchError("兼容 TLS 兜底拒绝未登记的跨来源重定向")
            redirect_chain.append(effective_url)
            current_url = destination
            continue
        if status >= 400:
            raise FetchError(f"兼容 TLS 兜底失败：HTTP {status}")
        if not body:
            raise FetchError("兼容 TLS 兜底失败：curl 返回空内容")
        return FetchedText(
            decode_bytes(body), requested_url, effective_url, tuple(redirect_chain)
        )
    raise FetchError("兼容 TLS 兜底失败：重定向次数超过5次")


def fetch_text(
    url: str,
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
) -> str:
    """Fetch one URL with shared cache/single-flight and bounded retry policy."""
    normalized = canonical_url(url)
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            return DEFAULT_TRANSPORT.fetch_text(
                normalized, _request_timeout(timeout, deadline), verify_ssl
            )
        except FetchError:
            raise
        except Exception as exc:
            last_error = exc
            status = _status_code(exc)
            if status in PERMANENT_HTTP_STATUSES or not is_transient_fetch_error(exc):
                raise FetchError(_failure_message(exc)) from exc
            if attempt == 0:
                _request_timeout(timeout, deadline)
                time.sleep(0.25)

    if normalized in CURL_COMPATIBILITY_URLS:
        try:
            return fetch_with_curl(normalized, timeout, verify_ssl, deadline=deadline)
        except FetchError as curl_error:
            raise curl_error from last_error
    if last_error is None:
        raise FetchError("网络抓取失败：未知错误")
    raise FetchError(_failure_message(last_error)) from last_error


def fetch_resource_group(
    urls: list[str],
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
) -> list[tuple[str, str | None, Exception | None]]:
    if not urls:
        return []
    results: list[tuple[str, str | None, Exception | None]] = [(url, None, None) for url in urls]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(urls))) as executor:
        future_map = {
            executor.submit(fetch_text, url, timeout, verify_ssl, deadline=deadline): index
            for index, url in enumerate(urls)
        }
        for future in concurrent.futures.as_completed(future_map):
            index = future_map[future]
            url = urls[index]
            try:
                results[index] = (url, future.result(), None)
            except Exception as exc:
                results[index] = (url, None, exc)
    return results


def fetch_rendered_text(
    url: str,
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
    wait_until: str = "networkidle",
) -> str:
    return DEFAULT_TRANSPORT.fetch_rendered(
        url,
        _request_timeout(timeout, deadline),
        verify_ssl,
        html=False,
        wait_until=wait_until,
    )


def fetch_rendered_html(
    url: str,
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
    wait_until: str = "networkidle",
) -> str:
    return DEFAULT_TRANSPORT.fetch_rendered(
        url,
        _request_timeout(timeout, deadline),
        verify_ssl,
        html=True,
        wait_until=wait_until,
    )


def fetch_interactive_rendered_html(
    url: str,
    timeout: int,
    verify_ssl: bool,
    issue: int,
    site_name: str,
    *,
    deadline: float | None = None,
    wait_until: str = "load",
) -> str:
    return DEFAULT_TRANSPORT.fetch_rendered_interactive(
        url,
        _request_timeout(timeout, deadline),
        verify_ssl,
        issue=issue,
        site_name=site_name,
        wait_until=wait_until,
    )

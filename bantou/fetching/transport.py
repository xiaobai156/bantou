# -*- coding: utf-8 -*-
"""Run-scoped HTTP transport with connection reuse and URL single-flight."""

from __future__ import annotations

import concurrent.futures
import re
import threading
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit, urljoin
import time

import requests

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_META_CHARSET_RE = re.compile(
    rb"\bcharset\s*=\s*['\"]?\s*([a-z0-9_.-]+)", re.I
)
_WEAK_DEFAULT_ENCODINGS = {"ascii", "iso-8859-1", "latin-1", "latin1"}
MAX_BODY_BYTES = 16 * 1024 * 1024


def _click_interactive_card(page, issue: int, site_name: str, timeout: int) -> None:
    card_text = f"{issue}期: 白蛇传【绝杀半头】→{site_name}"
    card = page.get_by_text(card_text, exact=True)
    count = card.count()
    if count != 1:
        raise ValueError(f"目标卡片未唯一命中：{card_text}，找到{count}个")
    card.click(timeout=timeout * 1000)
    page.wait_for_function(
        """
        ([issue]) => {
            const text = document.body.innerText || "";
            return new RegExp(`${issue}期\\s*[:：]\\s*【绝杀半头】`).test(text);
        }
        """,
        arg=[str(issue)],
        timeout=timeout * 1000,
    )


def canonical_url(url: str) -> str:
    """Canonicalize only transport identity; the route fragment is never requested."""
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower() if parsed.hostname else ""
    port = parsed.port
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        host = f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, host, path, parsed.query, ""))



def canonical_browser_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    base = canonical_url(url)
    return base + ("#" + parsed.fragment if parsed.fragment else "")


def decode_response_content(raw: bytes, declared_encoding: str | None) -> str:
    """Decode HTML by its in-page charset before a weak HTTP default."""
    candidates: list[str] = []
    charset_match = _META_CHARSET_RE.search(raw[:8192])
    if charset_match:
        candidates.append(charset_match.group(1).decode("ascii", errors="ignore"))

    declared = (declared_encoding or "").strip()
    if declared and declared.lower() not in _WEAK_DEFAULT_ENCODINGS:
        candidates.append(declared)
    candidates.extend(("utf-8-sig", "utf-8", "gb18030", "big5"))
    if declared:
        candidates.append(declared)
    candidates.append("latin-1")

    seen: set[str] = set()
    for encoding in candidates:
        normalized = encoding.lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


@dataclass
class _Flight:
    event: threading.Event
    text: str | None = None
    error: Exception | None = None


from .browser_process import ProcessBrowserWorker as _BrowserWorker



class FetchedText(str):
    def __new__(cls, text, requested_url="", final_url="", redirect_chain=()):
        obj = super().__new__(cls, text)
        obj.requested_url = requested_url
        obj.final_url = final_url or requested_url
        obj.redirect_chain = tuple(redirect_chain)
        return obj


def same_origin(left: str, right: str) -> bool:
    def origin(value):
        parsed = urlsplit(value)
        return (parsed.scheme.lower(), parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    return origin(left) == origin(right)


class RunTransport:
    """Owns all HTTP state for one program run.

    The instance is safe for the crawler's thread pool: each worker receives a
    reusable Session, while identical normalized URLs are fetched once and
    shared among all waiting callers.
    """

    def __init__(self, *, max_per_domain: int = 2) -> None:
        if max_per_domain < 1:
            raise ValueError("max_per_domain 必须大于 0")
        self.max_per_domain = max_per_domain
        self._local = threading.local()
        self._lock = threading.RLock()
        self._sessions: set[requests.Session] = set()
        self._cache: dict[tuple[str, bool], str] = {}
        self._flights: dict[tuple[str, bool], _Flight] = {}
        self._domains: dict[str, threading.BoundedSemaphore] = {}
        self._render_cache: dict[tuple[str, str, bool], str] = {}
        self._render_flights: dict[tuple[str, str, bool], _Flight] = {}
        self._browser_workers: list[_BrowserWorker] = []
        self._browser_worker_index = 0

    def session_for(self, verify_ssl: bool) -> requests.Session:
        sessions = getattr(self._local, "sessions", None)
        if sessions is None:
            sessions = {}
            self._local.sessions = sessions
        session = sessions.get(verify_ssl)
        with self._lock:
            if session is None or session not in self._sessions:
                session = requests.Session()
                session.headers.update(DEFAULT_HEADERS)
                sessions[verify_ssl] = session
                self._sessions.add(session)
        return session

    def _domain_semaphore(self, url: str) -> threading.BoundedSemaphore:
        hostname = urlsplit(url).hostname or ""
        with self._lock:
            semaphore = self._domains.get(hostname)
            if semaphore is None:
                semaphore = threading.BoundedSemaphore(self.max_per_domain)
                self._domains[hostname] = semaphore
            return semaphore

    def _request_once(self, url: str, timeout: int, verify_ssl: bool) -> str:
        session = self.session_for(verify_ssl)
        deadline = time.monotonic() + timeout
        semaphore = self._domain_semaphore(url)
        if not semaphore.acquire(timeout=timeout):
            raise TimeoutError("单站总超时：等待域名请求槽超时")
        chain: list[str] = []
        current = url
        try:
            for _hop in range(6):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("单站总超时：重定向超时")
                with session.get(
                    current,
                    timeout=(min(10, remaining), min(10, remaining)),
                    verify=verify_ssl,
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    location = response.headers.get("Location")
                    if response.status_code in {301, 302, 303, 307, 308} and location:
                        destination = urljoin(current, location)
                        if not same_origin(url, destination):
                            raise requests.RequestException(
                                "禁止未登记的跨来源重定向"
                            )
                        chain.append(current)
                        current = destination
                        continue
                    response.raise_for_status()
                    declared_size = response.headers.get("Content-Length")
                    if (
                        declared_size
                        and declared_size.isdigit()
                        and int(declared_size) > MAX_BODY_BYTES
                    ):
                        raise requests.RequestException(
                            f"响应正文超过 {MAX_BODY_BYTES} 字节上限"
                        )
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if time.monotonic() >= deadline:
                            raise TimeoutError("单站总超时：响应正文读取超时")
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > MAX_BODY_BYTES:
                            raise requests.RequestException(
                                f"响应正文超过 {MAX_BODY_BYTES} 字节上限"
                            )
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    return FetchedText(
                        decode_response_content(raw, response.encoding),
                        url,
                        response.url or current,
                        chain,
                    )
            raise requests.TooManyRedirects("重定向次数超过5次")
        finally:
            semaphore.release()

    def fetch_text(self, url: str, timeout: int, verify_ssl: bool) -> str:
        normalized = canonical_url(url)
        key = (normalized, verify_ssl)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            flight = self._flights.get(key)
            if flight is None:
                flight = _Flight(threading.Event())
                self._flights[key] = flight
                owner = True
            else:
                owner = False

        if owner:
            try:
                text = self._request_once(normalized, timeout, verify_ssl)
            except Exception as exc:
                with self._lock:
                    flight.error = exc
                raise
            else:
                with self._lock:
                    self._cache[key] = text
                    flight.text = text
                return text
            finally:
                with self._lock:
                    self._flights.pop(key, None)
                    flight.event.set()

        if not flight.event.wait(timeout=timeout):
            raise TimeoutError("单站总超时：等待共享请求超时")
        if flight.error is not None:
            raise flight.error
        if flight.text is None:
            raise RuntimeError(f"URL 单飞未返回结果：{normalized}")
        return flight.text

    def _render_once(
        self,
        url: str,
        timeout: int,
        verify_ssl: bool,
        html: bool,
        wait_until: str = "networkidle",
        interaction: tuple[int, str] | None = None,
    ) -> str:
        with self._lock:
            if not self._browser_workers:
                self._browser_workers = [_BrowserWorker() for _ in range(2)]
            worker = self._browser_workers[
                self._browser_worker_index % len(self._browser_workers)
            ]
            self._browser_worker_index += 1
        return worker.render(
            url,
            timeout,
            verify_ssl,
            html,
            wait_until,
            interaction=interaction,
        )

    def fetch_rendered(
        self,
        url: str,
        timeout: int,
        verify_ssl: bool,
        *,
        html: bool,
        wait_until: str = "networkidle",
        interaction: tuple[int, str] | None = None,
    ) -> str:
        if wait_until not in {"domcontentloaded", "load", "networkidle"}:
            raise ValueError(f"浏览器等待方式无效：{wait_until}")
        normalized = canonical_browser_url(url)
        key = (
            "html" if html else "text",
            wait_until,
            normalized,
            verify_ssl,
            interaction,
        )
        with self._lock:
            if key in self._render_cache:
                return self._render_cache[key]
            flight = self._render_flights.get(key)
            if flight is None:
                flight = _Flight(threading.Event())
                self._render_flights[key] = flight
                owner = True
            else:
                owner = False
        if owner:
            try:
                text = self._render_once(
                    normalized,
                    timeout,
                    verify_ssl,
                    html,
                    wait_until,
                    interaction,
                )
            except Exception as exc:
                with self._lock:
                    flight.error = exc
                raise
            else:
                with self._lock:
                    self._render_cache[key] = text
                    flight.text = text
                return text
            finally:
                with self._lock:
                    self._render_flights.pop(key, None)
                    flight.event.set()
        if not flight.event.wait(timeout=timeout):
            raise TimeoutError("单站总超时：等待共享请求超时")
        if flight.error is not None:
            raise flight.error
        if flight.text is None:
            raise RuntimeError(f"浏览器 URL 单飞未返回结果：{normalized}")
        return flight.text

    def fetch_rendered_interactive(
        self,
        url: str,
        timeout: int,
        verify_ssl: bool,
        *,
        issue: int,
        site_name: str,
        wait_until: str = "load",
    ) -> str:
        return self.fetch_rendered(
            url,
            timeout,
            verify_ssl,
            html=True,
            wait_until=wait_until,
            interaction=(issue, site_name),
        )

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            for flight in self._flights.values():
                flight.event.set()
            self._flights.clear()
            self._render_cache.clear()
            for flight in self._render_flights.values():
                flight.event.set()
            self._render_flights.clear()
            self._domains.clear()

    def close(self) -> None:
        with self._lock:
            browser_workers = self._browser_workers
            self._browser_workers = []
            sessions = list(self._sessions)
            self._sessions.clear()
            try:
                self._local.sessions = {}
            except AttributeError:
                pass
        for worker in browser_workers:
            worker.close()
        for session in sessions:
            session.close()


DEFAULT_TRANSPORT = RunTransport()

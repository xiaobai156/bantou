# -*- coding: utf-8 -*-
"""Run-scoped HTTP transport with connection reuse and URL single-flight."""

from __future__ import annotations

import threading
import concurrent.futures
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

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


def _click_interactive_card(page, issue: int, site_name: str, timeout: int) -> None:
    card_text = f"{issue}期: 白蛇传【绝杀半头】→{site_name}"
    card = page.get_by_text(card_text, exact=True)
    count = card.count()
    if count != 1:
        raise ValueError(f"目标卡片未唯一命中：{card_text}，找到{count}个")
    card.click()
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


class _BrowserWorker:
    def __init__(self) -> None:
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._playwright = None
        self._browser = None
        self._browser_contexts: dict[bool, object] = {}

    def _render_owner(
        self,
        url: str,
        timeout: int,
        verify_ssl: bool,
        html: bool,
        wait_until: str,
        interaction: tuple[int, str] | None = None,
    ) -> str:
        from playwright.sync_api import sync_playwright

        if self._playwright is None:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
        context = self._browser_contexts.get(verify_ssl)
        if context is None:
            context = self._browser.new_context(ignore_https_errors=not verify_ssl)
            self._browser_contexts[verify_ssl] = context
        page = context.new_page()
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
            if interaction is not None:
                _click_interactive_card(page, *interaction, timeout=timeout)
            return page.content() if html else page.inner_text("body", timeout=timeout * 1000)
        finally:
            page.close()

    def render(
        self,
        url: str,
        timeout: int,
        verify_ssl: bool,
        html: bool,
        wait_until: str,
        interaction: tuple[int, str] | None = None,
    ) -> str:
        future = self.executor.submit(
            self._render_owner, url, timeout, verify_ssl, html, wait_until, interaction
        )
        return future.result(timeout=timeout + 10)

    def _close_owner(self) -> None:
        for context in self._browser_contexts.values():
            context.close()
        self._browser_contexts.clear()
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def close(self) -> None:
        try:
            self.executor.submit(self._close_owner).result(timeout=10)
        except concurrent.futures.TimeoutError:
            self.executor.shutdown(wait=False, cancel_futures=True)
        else:
            self.executor.shutdown(wait=True, cancel_futures=True)


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
        self._cache: dict[tuple[str, bool], str] = {}
        self._flights: dict[tuple[str, bool], _Flight] = {}
        self._domains: dict[str, threading.BoundedSemaphore] = {}
        self._render_cache: dict[tuple[str, str, bool], str] = {}
        self._render_flights: dict[tuple[str, str, bool], _Flight] = {}
        self._browser_executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._browser = None
        self._browser_contexts: dict[bool, object] = {}
        self._playwright = None
        self._browser_workers: list[_BrowserWorker] = []
        self._browser_worker_index = 0

    def session_for(self, verify_ssl: bool) -> requests.Session:
        sessions = getattr(self._local, "sessions", None)
        if sessions is None:
            sessions = {}
            self._local.sessions = sessions
        session = sessions.get(verify_ssl)
        if session is None:
            session = requests.Session()
            session.headers.update(DEFAULT_HEADERS)
            sessions[verify_ssl] = session
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
        with self._domain_semaphore(url):
            response = session.get(
                url,
                timeout=(min(10, timeout), timeout),
                verify=verify_ssl,
                allow_redirects=True,
            )
        for historic_response in [*response.history, response]:
            from_scheme = urlsplit(historic_response.url).scheme.lower()
            location = historic_response.headers.get("Location", "")
            to_scheme = urlsplit(location).scheme.lower()
            if from_scheme == "https" and to_scheme == "http":
                raise requests.RequestException("禁止 HTTPS 重定向到 HTTP，避免误抓")
        response.raise_for_status()
        return decode_response_content(response.content, response.encoding)

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

        flight.event.wait()
        if flight.error is not None:
            raise flight.error
        if flight.text is None:
            raise RuntimeError(f"URL 单飞未返回结果：{normalized}")
        return flight.text

    def _render_on_owner(
        self,
        url: str,
        timeout: int,
        verify_ssl: bool,
        html: bool,
        wait_until: str = "networkidle",
        interaction: tuple[int, str] | None = None,
    ) -> str:
        from playwright.sync_api import sync_playwright

        if self._playwright is None:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
        context = self._browser_contexts.get(verify_ssl)
        if context is None:
            context = self._browser.new_context(ignore_https_errors=not verify_ssl)
            self._browser_contexts[verify_ssl] = context
        page = context.new_page()
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
            if interaction is not None:
                _click_interactive_card(page, *interaction, timeout=timeout)
            return page.content() if html else page.inner_text("body", timeout=timeout * 1000)
        finally:
            page.close()

    def _render_once(
        self,
        url: str,
        timeout: int,
        verify_ssl: bool,
        html: bool,
        wait_until: str = "networkidle",
        interaction: tuple[int, str] | None = None,
    ) -> str:
        legacy_owner = self.__dict__.get("_render_on_owner")
        if legacy_owner is not None:
            with self._lock:
                if self._browser_executor is None:
                    self._browser_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                executor = self._browser_executor
            future = executor.submit(
                legacy_owner, url, timeout, verify_ssl, html, wait_until, interaction
            )
            return future.result(timeout=timeout + 10)
        with self._lock:
            if not self._browser_workers:
                self._browser_workers = [_BrowserWorker() for _ in range(4)]
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
        normalized = canonical_url(url)
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
        flight.event.wait()
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

    def close(self) -> None:
        with self._lock:
            browser_workers = self._browser_workers
            self._browser_workers = []
            executor = self._browser_executor
            self._browser_executor = None
        for worker in browser_workers:
            worker.close()
        if executor is None:
            return

        def close_owner() -> None:
            for context in self._browser_contexts.values():
                context.close()
            self._browser_contexts.clear()
            if self._browser is not None:
                self._browser.close()
                self._browser = None
            if self._playwright is not None:
                self._playwright.stop()
                self._playwright = None

        try:
            executor.submit(close_owner).result(timeout=10)
        except concurrent.futures.TimeoutError:
            executor.shutdown(wait=False, cancel_futures=True)
        else:
            executor.shutdown(wait=True, cancel_futures=True)


DEFAULT_TRANSPORT = RunTransport()

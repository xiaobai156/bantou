"""Reusable browser processes with a killable per-request time budget."""
from __future__ import annotations

import multiprocessing as mp
import os
import signal
import subprocess
import threading
import time
from urllib.parse import urlsplit


ANTI_BOT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
ANTI_BOT_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [{}, {}]});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
Object.defineProperty(window, 'chrome', {value: {runtime: {}}});
"""


def _wait_for_ready(page, issue, terms, selector, timeout):
    if issue is None or not terms:
        return
    page.wait_for_function(
        r"""
        ({issue, terms, selector}) => {
            const scope = selector ? document.querySelector(selector) : document.body;
            const text = scope ? (scope.innerText || "") : "";
            const compact = text.replaceAll(" ", "").replaceAll("\n", "")
                .replaceAll("\r", "").replaceAll("\t", "");
            const marker = `${String(issue)}期`;
            const normalizedTerms = terms.map(term => String(term).replaceAll(" ", ""));
            let issueIndex = compact.indexOf(marker);
            while (issueIndex >= 0) {
                const previous = compact[issueIndex - 1] || "";
                if (!(previous >= "0" && previous <= "9")) {
                    const start = Math.max(0, issueIndex - 4000);
                    const nearby = compact.slice(start, issueIndex + 4000);
                    if (normalizedTerms.every(term => nearby.includes(term))
                        && /[0-4]头(?:单|双)/.test(nearby)) return true;
                }
                issueIndex = compact.indexOf(marker, issueIndex + marker.length);
            }
            return false;
        }
        """,
        arg={"issue": int(issue), "terms": list(terms), "selector": selector},
        timeout=max(1, int(float(timeout) * 1000)),
    )


def _browser_main(connection):
    if os.name != "nt":
        os.setsid()
    playwright = browser = None
    try:
        connection.send(("ready", None))
        while True:
            task = connection.recv()
            if task is None:
                return
            url, timeout, verify_ssl, html, wait_until, interaction, anti_bot, *ready = task
            ready_issue = ready[0] if ready else None
            ready_terms = tuple(ready[1] or ()) if len(ready) > 1 else ()
            ready_selector = ready[2] if len(ready) > 2 else None
            context = None
            page = None
            try:
                connection.send(("stage", "浏览器初始化"))
                from playwright.sync_api import sync_playwright
                from .transport import _click_interactive_card, same_origin
                if playwright is None:
                    playwright = sync_playwright().start()
                    browser = playwright.chromium.launch(
                        headless=True,
                        args=["--disable-blink-features=AutomationControlled"],
                    )
                context = browser.new_context(
                    ignore_https_errors=not verify_ssl,
                    service_workers="block",
                    user_agent=ANTI_BOT_USER_AGENT if anti_bot else None,
                )
                if anti_bot:
                    parsed = urlsplit(url)
                    context.grant_permissions(
                        ["notifications"],
                        origin=f"{parsed.scheme}://{parsed.netloc}",
                    )
                    context.add_init_script(ANTI_BOT_INIT_SCRIPT)
                page = context.new_page()
                page.set_default_timeout(timeout * 1000)
                # A top-level cross-origin redirect must not be followed. Normal
                # page resources are unchanged; business provenance is checked later.
                def route_navigation(route):
                    request = route.request
                    if (request.is_navigation_request() and request.frame == page.main_frame
                            and not same_origin(url, request.url)):
                        route.abort()
                    else:
                        route.continue_()
                page.route("**/*", route_navigation)
                connection.send(("stage", f"页面导航/{wait_until}"))
                response = page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                if response is not None and response.status >= 400:
                    raise ValueError(f"浏览器HTTP {response.status}")
                if not same_origin(url, page.url):
                    raise ValueError("浏览器最终来源与请求来源不一致")
                if ready_issue is not None and ready_terms:
                    connection.send(("stage", "目标内容等待"))
                    _wait_for_ready(page, ready_issue, ready_terms, ready_selector, timeout)
                elif wait_until == "load":
                    connection.send(("stage", "页面加载后等待"))
                    # ponytail: fixed settle for post-load feeds; replace with a DOM marker if pages diverge.
                    page.wait_for_timeout(3000)
                interactive_html = None
                if interaction is not None:
                    connection.send(("stage", "目标卡片交互"))
                    _click_interactive_card(page, *interaction, timeout=timeout)
                connection.send(("stage", "读取正文"))
                text = page.content() if html else page.inner_text("body", timeout=timeout * 1000)
                connection.send(("ok", (text, page.url)))
            except Exception as exc:
                connection.send(("error", f"{type(exc).__name__}: {exc}"))
            finally:
                if page is not None:
                    page.close()
                if context is not None:
                    context.close()
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()
        connection.close()


class ProcessBrowserWorker:
    def __init__(self, *, target=_browser_main):
        self._context = mp.get_context("spawn")
        self._target = target
        self._process = None
        self._connection = None
        self._lock = threading.Lock()
        self._stage = "浏览器进程启动"

    @staticmethod
    def _remaining(deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("单站总超时：浏览器任务超时")
        return remaining

    def _receive(self, deadline):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self._connection.poll(remaining):
                raise TimeoutError(f"单站总超时：浏览器任务超时（阶段：{self._stage}）")
            status, payload = self._connection.recv()
            if status != "stage":
                return status, payload
            self._stage = str(payload)

    def _stop(self):
        process, connection = self._process, self._connection
        self._process = self._connection = None
        try:
            if process is not None and process.is_alive():
                if os.name == "nt":
                    try:
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       timeout=5, check=False)
                    except (OSError, subprocess.TimeoutExpired):
                        process.terminate()
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        process.terminate()
                process.join(timeout=2)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=2)
            if process is not None and not process.is_alive():
                process.close()
        finally:
            if connection is not None:
                connection.close()

    def kill_now(self):
        self._stop()

    def render(
        self,
        url,
        timeout,
        verify_ssl,
        html,
        wait_until,
        interaction=None,
        anti_bot=False,
        ready_issue=None,
        ready_terms=(),
        ready_selector=None,
    ):
        deadline = time.monotonic() + timeout
        if not self._lock.acquire(timeout=max(0, timeout)):
            raise TimeoutError("单站总超时：等待浏览器工作槽超时")
        try:
            self._stage = "浏览器进程启动"
            if self._process is None or not self._process.is_alive():
                self._stop()
                parent, child = self._context.Pipe()
                self._connection = parent
                self._process = self._context.Process(target=self._target, args=(child,), daemon=True)
                self._process.start()
                child.close()
                status, _payload = self._receive(deadline)
                if status != "ready":
                    raise RuntimeError("浏览器工作进程初始化失败")
            self._connection.send(
                (
                    url,
                    self._remaining(deadline),
                    verify_ssl,
                    html,
                    wait_until,
                    interaction,
                    anti_bot,
                    ready_issue,
                    tuple(ready_terms),
                    ready_selector,
                )
            )
            status, payload = self._receive(deadline)
            if status != "ok":
                raise RuntimeError(f"浏览器渲染失败：{payload}")
            from .transport import FetchedText
            text, final_url = payload
            return FetchedText(text, url, final_url)
        except Exception:
            self._stop()
            raise
        finally:
            self._lock.release()

    def close(self):
        if not self._lock.acquire(timeout=2):
            self._stop()
            return
        try:
            if self._connection is not None:
                try:
                    self._connection.send(None)
                    self._process.join(timeout=2)
                except (OSError, EOFError):
                    pass
            self._stop()
        finally:
            self._lock.release()

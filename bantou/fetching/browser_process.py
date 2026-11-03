"""Reusable browser processes with a killable per-request time budget."""
from __future__ import annotations

import multiprocessing as mp
import os
import signal
import subprocess
import threading
import time
from urllib.parse import urlsplit, urlunsplit


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

# 站方轮换域名时先落一个「安全检测」中转页，需要点按钮才放行到真实站点。
GATE_BUTTON_TEXTS = ("立即进入", "点击进入", "进入")
GATE_SETTLE_MS = 4000


def _relocated_identity_ok(requested: str, landed: str) -> bool:
    """换址后文章标识必须不变：非根路径逐字一致，根路径仍须落在根路径。"""
    requested_path = urlsplit(requested).path
    landed_path = urlsplit(landed).path
    if requested_path in {"", "/"}:
        # 根路径站也要求落回根路径，不能被换址带到任意深层页面冒充。
        return landed_path in {"", "/"}
    return requested_path == landed_path


def _follow_relocated_origin(page, requested, landed, wait_until, timeout):
    """跟随站方换址：点过安全检测页，再在新域名上重建原文章路径。"""
    for text in GATE_BUTTON_TEXTS:
        try:
            locator = page.get_by_text(text, exact=False).first
            if locator.count() and locator.is_visible():
                locator.click(timeout=min(5000, int(timeout * 1000)))
                break
        except Exception:
            continue
    page.wait_for_timeout(GATE_SETTLE_MS)
    parsed_requested = urlsplit(requested)
    current = urlsplit(page.url)
    if parsed_requested.path not in {"", "/"}:
        rebuilt = urlunsplit(
            (
                current.scheme,
                current.netloc,
                parsed_requested.path,
                parsed_requested.query,
                "",
            )
        )
        if page.url != rebuilt:
            try:
                page.goto(rebuilt, wait_until=wait_until, timeout=timeout * 1000)
            except Exception:
                pass
    return page.url


def _wait_for_ready(page, issue, terms, selector, timeout):
    if not terms:
        return
    page.wait_for_function(
        r"""
        ({issue, terms, selector}) => {
            const scope = selector ? document.querySelector(selector) : document.body;
            const text = scope ? (scope.innerText || "") : "";
            const pageText = document.body ? (document.body.innerText || "") : text;
            const compact = text.replaceAll(" ", "").replaceAll("\n", "")
                .replaceAll("\r", "").replaceAll("\t", "");
            const pageCompact = pageText.replaceAll(" ", "").replaceAll("\n", "")
                .replaceAll("\r", "").replaceAll("\t", "");
            const marker = `${String(issue)}期`;
            const normalizedTerms = terms.map(term => String(term).replaceAll(" ", ""));
            if (issue == null) {
                return normalizedTerms.every(term => compact.includes(term) || pageCompact.includes(term))
                    && /[0-4]头(?:单|双)/.test(compact);
            }
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
        arg={
            "issue": int(issue) if issue is not None else None,
            "terms": list(terms),
            "selector": selector,
        },
        timeout=max(1, int(float(timeout) * 1000)),
    )


def _browser_main(connection):
    if os.name != "nt":
        os.setsid()
    playwright = browser = None
    headless_mode = None
    try:
        connection.send(("ready", None))
        while True:
            task = connection.recv()
            if task is None:
                return
            url, timeout, verify_ssl, html, wait_until, interaction, anti_bot, headful, *ready = task
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
                # 少数站的站方脚本在无头模式下直接返回空白；按需重建浏览器。
                if browser is None or headless_mode != (not headful):
                    if browser is not None:
                        browser.close()
                    browser = playwright.chromium.launch(
                        headless=not headful,
                        args=["--disable-blink-features=AutomationControlled"],
                    )
                    headless_mode = not headful
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
                # 站方轮换域名时顶层跳转会换 origin。这里只放行「文章路径不变」
                # 的换址，路径变了仍按跨来源拒绝；业务身份由解析与统一校验裁决。
                def route_navigation(route):
                    request = route.request
                    if (
                        request.is_navigation_request()
                        and request.frame == page.main_frame
                        and not same_origin(url, request.url)
                        and not _relocated_identity_ok(url, request.url)
                    ):
                        route.abort()
                    else:
                        route.continue_()
                page.route("**/*", route_navigation)
                connection.send(("stage", f"页面导航/{wait_until}"))
                response = page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                if response is not None and response.status >= 400:
                    raise ValueError(f"浏览器HTTP {response.status}")
                if not same_origin(url, page.url):
                    # 站方换址：只在「文章路径逐字不变」时跟随，否则按跨来源拒绝。
                    connection.send(("stage", "站方换址跟随"))
                    page.unroute("**/*", route_navigation)
                    landed = _follow_relocated_origin(page, url, page.url, wait_until, timeout)
                    if not _relocated_identity_ok(url, landed):
                        raise ValueError("浏览器最终来源与请求来源不一致")
                if ready_terms:
                    connection.send(("stage", "目标内容等待"))
                    _wait_for_ready(page, ready_issue, ready_terms, ready_selector, timeout)
                elif wait_until == "load":
                    connection.send(("stage", "页面加载后等待"))
                    # ponytail: fixed settle for post-load feeds; replace with a DOM marker if pages diverge.
                    page.wait_for_timeout(3000)
                interactive_html = None
                if interaction is not None:
                    connection.send(("stage", "目标卡片交互"))
                    interactive_html = _click_interactive_card(page, *interaction, timeout=timeout)
                connection.send(("stage", "读取正文"))
                text = (
                    interactive_html
                    if interactive_html is not None
                    else page.content() if html else page.inner_text("body", timeout=timeout * 1000)
                )
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
        headful=False,
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
                    headful,
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

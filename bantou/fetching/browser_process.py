"""Reusable browser processes with a killable per-request time budget."""
from __future__ import annotations

import multiprocessing as mp
import os
import signal
import subprocess
import threading
import time


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
            url, timeout, verify_ssl, html, wait_until, interaction = task
            context = None
            page = None
            try:
                from playwright.sync_api import sync_playwright
                from .transport import _click_interactive_card, same_origin
                if playwright is None:
                    playwright = sync_playwright().start()
                    browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    ignore_https_errors=not verify_ssl,
                    service_workers="block",
                )
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
                response = page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                if response is not None and response.status >= 400:
                    raise ValueError(f"浏览器HTTP {response.status}")
                if not same_origin(url, page.url):
                    raise ValueError("浏览器最终来源与请求来源不一致")
                if interaction is not None:
                    _click_interactive_card(page, *interaction, timeout=timeout)
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

    @staticmethod
    def _remaining(deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("单站总超时：浏览器任务超时")
        return remaining

    def _receive(self, deadline):
        if not self._connection.poll(self._remaining(deadline)):
            raise TimeoutError("单站总超时：浏览器任务超时")
        return self._connection.recv()

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

    def render(self, url, timeout, verify_ssl, html, wait_until, interaction=None):
        deadline = time.monotonic() + timeout
        if not self._lock.acquire(timeout=max(0, timeout)):
            raise TimeoutError("单站总超时：等待浏览器工作槽超时")
        try:
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
            self._connection.send((url, self._remaining(deadline), verify_ssl, html, wait_until, interaction))
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
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.send(None)
                    self._process.join(timeout=2)
                except (OSError, EOFError):
                    pass
            self._stop()

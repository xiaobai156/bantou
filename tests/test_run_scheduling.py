"""Offline regression tests for the HTTP/browser lane scheduler."""

from __future__ import annotations

import threading
from types import SimpleNamespace

from bantou.application import single_period
from bantou.domain.models import Site, SiteResult
from bantou.site_profiles import registry


def _args(**overrides):
    values = dict(
        workers=10,
        timeout=1,
        site_timeout=1,
        retries=0,
        delay=0,
        verify_ssl=True,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _site(index: int, *, browser: bool) -> Site:
    url = (
        registry.WUZHUANXINGYI_URL
        if browser
        else f"https://example.test/http-{index}"
    )
    return Site(str(index), url, "top", index, "strict_half_head", ("半头",))


def test_browser_lane_is_limited_to_two_without_sliding_queue(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    third_seen = threading.Event()
    third_gate = threading.Event()
    lock = threading.Lock()
    active = 0
    maximum = 0

    def fake_crawl(index, site, *args, **kwargs):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            if active == 2:
                started.set()
        if index <= 2:
            assert started.wait(2)
            assert release.wait(2)
        else:
            third_seen.set()
            assert third_gate.wait(2)
            assert release.wait(2)
        with lock:
            active -= 1
        return SiteResult(index, site, [object()], None)

    monkeypatch.setattr(single_period, "crawl_site", fake_crawl)
    sites = [_site(index, browser=True) for index in range(1, 5)]

    def run():
        return single_period._run_sites(_args(), sites, {264}, None)

    result_box = []
    thread = threading.Thread(target=lambda: result_box.append(run()))
    thread.start()
    assert started.wait(2)
    assert not third_seen.wait(0.1)
    release.set()
    third_gate.set()
    thread.join(3)

    assert not thread.is_alive()
    results, abandoned = result_box[0]
    assert abandoned == 0
    assert len(results) == 4
    assert maximum <= 2


def test_http_lane_keeps_worker_concurrency(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    active_http = 0
    active_browser = 0
    maximum_http = 0
    maximum_browser = 0

    def fake_crawl(index, site, *args, **kwargs):
        nonlocal active_http, active_browser, maximum_http, maximum_browser
        is_browser = site.url == registry.WUZHUANXINGYI_URL
        with lock:
            if is_browser:
                active_browser += 1
                maximum_browser = max(maximum_browser, active_browser)
            else:
                active_http += 1
                maximum_http = max(maximum_http, active_http)
            if active_http >= 3 and active_browser >= 2:
                started.set()
        assert started.wait(2)
        assert release.wait(2)
        with lock:
            if is_browser:
                active_browser -= 1
            else:
                active_http -= 1
        return SiteResult(index, site, [object()], None)

    monkeypatch.setattr(single_period, "crawl_site", fake_crawl)
    sites = [_site(index, browser=False) for index in range(1, 4)]
    sites += [_site(index, browser=True) for index in range(4, 7)]

    result_box = []
    thread = threading.Thread(
        target=lambda: result_box.append(
            single_period._run_sites(_args(), sites, {264}, None)
        )
    )
    thread.start()
    assert started.wait(2)
    release.set()
    thread.join(3)

    assert not thread.is_alive()
    results, abandoned = result_box[0]
    assert abandoned == 0
    assert len(results) == 6
    assert maximum_http >= 3
    assert maximum_browser <= 2


def test_hung_browser_does_not_create_unbounded_queued_futures(monkeypatch):
    release = threading.Event()
    started = threading.Event()
    calls = []
    lock = threading.Lock()

    def fake_crawl(index, site, *args, **kwargs):
        with lock:
            calls.append(index)
        if index <= 2:
            started.set()
            release.wait(2)
        return SiteResult(index, site, [object()], None)

    monkeypatch.setattr(single_period, "crawl_site", fake_crawl)
    monkeypatch.setattr(single_period, "HARD_TIMEOUT_BUFFER_SECONDS", 0)
    monkeypatch.setattr(single_period, "WATCHDOG_POLL_SECONDS", 0.01)
    sites = [_site(index, browser=True) for index in range(1, 5)]
    args = _args(site_timeout=0.05)

    results, abandoned = single_period._run_sites(args, sites, {264}, None)
    release.set()

    assert started.is_set()
    assert abandoned == 2
    assert len(results) == 4
    assert all("未发起请求" in result.error for result in results if result.index > 2)
    assert len(calls) == 2

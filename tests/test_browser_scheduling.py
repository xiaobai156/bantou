"""No network: an idle browser must not be stranded behind a busy one."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from bantou.application import site_crawl
from bantou.documents import collection
from bantou.domain.models import Site
from bantou.fetching import transport
from bantou.site_profiles import registry


def test_browser_uses_idle_worker_instead_of_round_robin(monkeypatch):
    started, release = threading.Event(), threading.Event()

    class Worker:
        def __init__(self):
            self.lock = threading.Lock()

        def render(self, url, timeout, *args, **kwargs):
            if not self.lock.acquire(timeout=timeout):
                raise TimeoutError("busy worker selected")
            try:
                if url.endswith('/slow'):
                    started.set()
                    assert release.wait(5)
                return transport.FetchedText(url, url, url)
            finally:
                self.lock.release()

        def close(self):
            pass

    monkeypatch.setattr(transport, '_BrowserWorker', Worker)
    client = transport.RunTransport()
    with ThreadPoolExecutor(max_workers=1) as executor:
        slow = executor.submit(client._render_once, 'https://example.test/slow', 4, True, True)
        try:
            assert started.wait(2)
            assert client._render_once('https://example.test/fast1', .2, True, True).endswith('/fast1')
            assert client._render_once('https://example.test/fast2', .2, True, True).endswith('/fast2')
        finally:
            release.set()
            slow.result(timeout=2)
            client.close()


def test_browser_queue_timeout_and_failed_workers_leave_pool_usable(monkeypatch):
    started = threading.Barrier(3)
    release = threading.Event()

    class Worker:
        def render(self, url, timeout, *args, **kwargs):
            if url.endswith('/slow'):
                started.wait(timeout=2)
                assert release.wait(3)
            if url.endswith('/error'):
                raise RuntimeError('render failed')
            return transport.FetchedText(url, url, url)

        def close(self):
            pass

    monkeypatch.setattr(transport, '_BrowserWorker', Worker)
    client = transport.RunTransport()
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            busy = [executor.submit(client._render_once, 'https://example.test/slow', 2, True, True)
                    for _ in range(2)]
            try:
                started.wait(timeout=2)
                before = time.monotonic()
                with pytest.raises(TimeoutError, match='等待浏览器工作槽超时'):
                    client._render_once('https://example.test/fast', .03, True, True)
                assert time.monotonic() - before < 1
            finally:
                release.set()
                for task in busy:
                    task.result(timeout=2)
        for _ in range(2):
            with pytest.raises(RuntimeError, match='render failed'):
                client._render_once('https://example.test/error', .2, True, True)
        assert client._render_once('https://example.test/fast', .2, True, True).endswith('/fast')
    finally:
        client.close()


@pytest.mark.parametrize('name,url,parser', [
    ('彩运通', registry.CAIYUNTONG_URL, 'caiyuntong_macau'),
    ('广东八二', registry.GUANGDONG_BAER_URL, 'guangdong_baer_left_half_head'),
])
def test_required_browser_failure_is_retried_not_reported_as_empty(monkeypatch, name, url, parser):
    calls = []
    monkeypatch.setattr(collection, 'fetch_text', lambda *a, **k: '<html>空壳</html>')
    def timeout(*args, **kwargs):
        calls.append(1)
        raise TimeoutError('等待浏览器工作槽超时')
    monkeypatch.setattr(collection, 'fetch_rendered_html', timeout)
    site = Site(name, url, 'top', 1, parser, ('半头',))
    result = site_crawl.crawl_site(1, site, {264}, None, 1, True, 1, site_timeout=5)
    assert len(calls) == 2
    assert '等待浏览器工作槽超时' in result.error
    assert result.miss_reason is None

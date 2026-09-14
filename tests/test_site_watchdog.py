"""Offline regression for the per-site hard watchdog; never crawls real sites."""
import threading
import time
from types import SimpleNamespace

from bantou.application import single_period
from bantou.domain.models import Site, SiteResult


def site(name="A", url="https://example.test/a"):
    return Site(name, url, "top", 1, "strict_half_head", ("半头",))


def args(**overrides):
    fields = dict(workers=3, timeout=5, site_timeout=1, retries=0, delay=0, verify_ssl=True)
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_hung_site_is_abandoned_and_run_completes(monkeypatch):
    release = threading.Event()

    def fake_crawl(index, target_site, wanted_issues, target, timeout, verify_ssl, retries, delay, *, site_timeout=None):
        if target_site.name == "HANG":
            release.wait(30)
            return SiteResult(index, target_site, [], "不应被采纳")
        return SiteResult(index, target_site, [object()], None)

    monkeypatch.setattr(single_period, "crawl_site", fake_crawl)
    monkeypatch.setattr(single_period, "HARD_TIMEOUT_BUFFER_SECONDS", 0)
    sites = [site("A"), site("HANG", "https://example.test/hang"), site("B", "https://example.test/b")]
    began = time.monotonic()
    try:
        results, abandoned = single_period._run_sites(args(), sites, {251}, None)
        elapsed = time.monotonic() - began
    finally:
        release.set()

    assert abandoned == 1
    assert elapsed < 15
    by_name = {result.site.name: result for result in results}
    assert set(by_name) == {"A", "HANG", "B"}
    assert "硬超时" in (by_name["HANG"].error or "")
    assert by_name["A"].matches and by_name["B"].matches


def test_normal_sites_report_no_abandonment(monkeypatch):
    def fake_crawl(index, target_site, wanted_issues, target, timeout, verify_ssl, retries, delay, *, site_timeout=None):
        return SiteResult(index, target_site, [object()], None)

    monkeypatch.setattr(single_period, "crawl_site", fake_crawl)
    results, abandoned = single_period._run_sites(
        args(), [site("A"), site("B", "https://example.test/b")], {251}, None
    )
    assert abandoned == 0
    assert len(results) == 2


def test_force_exit_kills_browser_children_before_exit(monkeypatch):
    calls = []
    monkeypatch.setattr(
        single_period, "force_kill_browser_children", lambda: calls.append("kill")
    )
    monkeypatch.setattr(single_period.os, "_exit", lambda code: calls.append(("exit", code)))
    single_period._force_exit(2)
    assert calls == ["kill", ("exit", 2)]

from types import SimpleNamespace

from bantou.application import single_period
from bantou.domain import Match, Site, SiteResult


class _Future:
    def __init__(self, result):
        self._result = result

    def result(self):
        return self._result


class _FailingExecutor:
    def __init__(self, *args, **kwargs):
        self.submitted = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def submit(self, function, index, site, *args, **kwargs):
        self.submitted += 1
        if self.submitted == 5:
            raise RuntimeError("线程池提交失败")
        match = Match(
            issue=213,
            issue_text="213期",
            value="2头双",
            snippet="213期 杀半头 2头双",
            order=index,
        )
        return _Future(SiteResult(index, site, [match]))


def test_run_sites_records_submission_failure_and_finishes(monkeypatch):
    monkeypatch.setattr(
        single_period.concurrent.futures,
        "ThreadPoolExecutor",
        _FailingExecutor,
    )
    monkeypatch.setattr(
        single_period.concurrent.futures,
        "as_completed",
        lambda futures: list(futures),
    )

    sites = [
        Site(name=f"站点{i}", url=f"https://example.test/{i}", pick="top", line_no=i)
        for i in range(1, 7)
    ]
    args = SimpleNamespace(
        workers=10,
        timeout=20,
        verify_ssl=True,
        retries=1,
        delay=0,
        site_timeout=60,
    )

    results = single_period._run_sites(
        args,
        sites,
        {213},
        None,
        (),
    )

    assert len(results) == len(sites)
    by_index = {result.index: result for result in results}
    assert by_index[5].error is not None
    assert "任务提交失败" in by_index[5].error
    assert by_index[6].error is None
    assert by_index[6].matches

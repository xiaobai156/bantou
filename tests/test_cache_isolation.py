import json
from types import SimpleNamespace

from bantou.application import single_period
from bantou.cache import CacheValidationError, build_bootstrap_cache_payload
from bantou.domain import Match, Site, SiteResult


def _site_match(value: str, *, issue: int = 214) -> tuple[Site, Match]:
    site = Site(
        name="测试站",
        url="https://example.test/half-head",
        pick="top",
        line_no=1,
        parser_id="strict_half_head",
        anchors=("杀半头",),
    )
    match = Match(
        issue=issue,
        issue_text=f"{issue}期",
        value=value,
        snippet=f"{issue}期 杀半头 {value}",
        order=0,
        position=1,
        source_url=site.url,
        source_kind="page",
        anchor_text="杀半头",
        anchor_position=2,
        block_id="block-1",
        block_start=1,
        block_end=4,
        container_id="container-1",
        document_authority="page",
        rule_id="strict_half_head",
    )
    return site, match


def _cache_args() -> SimpleNamespace:
    return SimpleNamespace(
        rebuild_cache=False,
        write_backup=True,
        diagnose=False,
        multi_mode=False,
        retry_fail=False,
    )


def test_cache_conflict_does_not_reclassify_single_period_success(monkeypatch, tmp_path):
    cache_path = tmp_path / "recent_10_cache.json"
    site, cached_match = _site_match("2头双")
    cache_path.write_text(
        json.dumps(
            build_bootstrap_cache_payload(
                214,
                [214],
                {site.name: (site, {214: cached_match})},
                [],
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(single_period, "DUPLICATE_BACKUP_FILE", cache_path)

    _site, current_match = _site_match("4头单")
    rank_rows = [(site.name, "214期", current_match.value, site.url)]
    cache_rows = {site.name: (site, {214: current_match})}
    fail_lines = ["网站名称\t分类\t原因\t网址"]

    updated_rank_rows, _rows, updated_fail_lines, payload = single_period._prepare_cache_update(
        _cache_args(),
        [214],
        [site],
        rank_rows,
        cache_rows,
        fail_lines,
    )

    assert updated_rank_rows == rank_rows
    assert updated_fail_lines == fail_lines
    assert payload is not None


def test_single_period_does_not_read_cache_before_crawl(monkeypatch, tmp_path):
    site, match = _site_match("2头双", issue=215)
    success_path = tmp_path / "215期-半头.txt"
    failure_path = tmp_path / "215期-半头-失败.txt"

    def fail_if_cache_is_read(*_args, **_kwargs):
        raise AssertionError("单期抓取前不应读取 JSON 缓存")

    monkeypatch.setattr(single_period, "read_cache_for_update", fail_if_cache_is_read)
    monkeypatch.setattr(single_period, "read_sites", lambda _path: [site])
    monkeypatch.setattr(
        single_period,
        "_run_sites",
        lambda *_args, **_kwargs: [SiteResult(1, site, [match])],
    )
    monkeypatch.setattr(single_period, "_prepare_cache_payload", lambda *_args: (None, {}))
    monkeypatch.setattr(single_period, "default_success_name_path", lambda _name: success_path)
    monkeypatch.setattr(single_period, "default_failure_name_path", lambda _name: failure_path)

    assert single_period.main(["215"]) == 0
    assert success_path.exists()
    assert "测试站" in success_path.read_text(encoding="utf-8-sig")


def test_cache_update_error_keeps_live_result_output(monkeypatch, tmp_path):
    site, match = _site_match("2头双", issue=215)
    success_path = tmp_path / "215期-半头.txt"
    failure_path = tmp_path / "215期-半头-失败.txt"

    monkeypatch.setattr(single_period, "read_cache_for_update", lambda *_args, **_kwargs: {"state": "reset"})
    monkeypatch.setattr(single_period, "read_sites", lambda _path: [site])
    monkeypatch.setattr(
        single_period,
        "_run_sites",
        lambda *_args, **_kwargs: [SiteResult(1, site, [match])],
    )
    monkeypatch.setattr(
        single_period,
        "_prepare_cache_payload",
        lambda *_args: (_ for _ in ()).throw(CacheValidationError("缓存更新测试失败")),
    )
    monkeypatch.setattr(single_period, "default_success_name_path", lambda _name: success_path)
    monkeypatch.setattr(single_period, "default_failure_name_path", lambda _name: failure_path)

    assert single_period.main(["215"]) == 2
    assert success_path.exists()
    assert "测试站" in success_path.read_text(encoding="utf-8-sig")

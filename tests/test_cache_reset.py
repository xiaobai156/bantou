import json
from types import SimpleNamespace

from bantou.application import single_period
from bantou.cache import CACHE_KIND, CACHE_SCHEMA, CACHE_STATE_RESET, read_cache_for_update
from bantou.domain import Match, Site


def _reset_payload():
    return {
        "schema": CACHE_SCHEMA,
        "kind": CACHE_KIND,
        "state": CACHE_STATE_RESET,
        "period": None,
        "window": 10,
        "issues": [],
        "updated_at": "2026-08-01T00:00:00",
        "sites": [],
        "failures": [],
    }


def _site_and_match():
    site = Site(
        name="测试站",
        url="https://example.test/214",
        pick="top",
        line_no=1,
        parser_id="strict_half_head",
        anchors=("杀半头",),
    )
    match = Match(
        issue=214,
        issue_text="214期",
        value="2头双",
        snippet="214期 杀半头 2头双",
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


def test_reset_cache_payload_is_accepted_for_update(tmp_path):
    path = tmp_path / "recent_10_cache.json"
    path.write_text(json.dumps(_reset_payload()), encoding="utf-8")

    payload = read_cache_for_update(path, allow_legacy_bootstrap=True)

    assert payload["state"] == CACHE_STATE_RESET
    assert payload["period"] is None
    assert payload["issues"] == []
    assert payload["sites"] == []


def test_first_single_period_after_reset_builds_new_bootstrap(monkeypatch, tmp_path):
    cache_path = tmp_path / "recent_10_cache.json"
    cache_path.write_text(json.dumps(_reset_payload()), encoding="utf-8")
    monkeypatch.setattr(single_period, "DUPLICATE_BACKUP_FILE", cache_path)

    site, match = _site_and_match()
    args = SimpleNamespace(
        rebuild_cache=False,
        write_backup=True,
        diagnose=False,
        multi_mode=False,
        retry_fail=False,
    )

    payload, conflicts = single_period._prepare_cache_payload(
        args,
        [214],
        [site],
        {site.name: (site, {214: match})},
        [],
    )

    assert conflicts == {}
    assert payload is not None
    assert payload["state"] == "bootstrap"
    assert payload["period"] == 214
    assert payload["issues"] == [214]
    assert len(payload["sites"]) == 1

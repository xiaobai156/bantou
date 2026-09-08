# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime as dt

from ..domain.models import Match, Site
from .validation import (
    CACHE_KIND,
    CACHE_SCHEMA,
    CACHE_STATE_READY,
    LEGACY_CONFIRMED_SOURCE_KIND,
    CacheValidationError,
    cache_entry_from_match,
    validate_cache_for_update,
    validate_legacy_cache_payload,
)


def _legacy_confirmed_match(site: Site, issue: int, value: str) -> Match:
    anchor = site.anchors[0] if site.anchors else "用户确认历史"
    return Match(
        issue=issue,
        issue_text=str(issue),
        value=value,
        snippet=f"{issue}期 {anchor} {value}（用户确认的可信历史缓存；无原始页面快照）",
        order=-1,
        position=-1,
        source_url=site.url,
        source_kind=LEGACY_CONFIRMED_SOURCE_KIND,
        anchor_text=anchor,
        anchor_position=-1,
        block_id=f"legacy-cache:{site.name}:{issue}",
        block_start=-1,
        block_end=-1,
        container_id="legacy-cache",
        document_authority="user-confirmed-legacy",
        rule_id="legacy-cache-confirmed",
    )


def migrate_legacy_cache_roll_payload(
    payload: dict[str, object],
    period: int,
    all_sites: list[Site],
    incoming: dict[str, tuple[Site, dict[int, Match]]],
    failures: list[tuple[str, str, str]],
) -> tuple[dict[str, object], dict[str, str]]:
    """Migrate a user-confirmed schema-1 baseline during one current-period run."""
    original = validate_legacy_cache_payload(payload)
    old_period = int(original["period"])
    if period != old_period + 1:
        raise CacheValidationError(
            f"可信旧缓存最后一期是 {old_period}，只允许接续下一期，当前期是 {period}"
        )
    old_issues = [int(issue) for issue in original["issues"]]
    retained_issues = old_issues[1:]
    new_issues = retained_issues + [period]
    old_items = {str(item["name"]): item for item in original["sites"]}
    failure_names = {name for name, _reason, _url in failures}
    conflicts: dict[str, str] = {}
    new_items: list[dict[str, object]] = []

    for name, (site, by_issue) in incoming.items():
        if name in failure_names:
            continue
        if set(by_issue) != {period}:
            conflicts[name] = "单期缓存滚动必须只包含当前指定期数"
            continue
        old_item = old_items.get(name)
        if old_item is None:
            conflicts[name] = "可信旧缓存中没有该站完整历史，拒绝混合历史"
            continue
        legacy_identity = (
            str(old_item.get("name") or ""),
            str(old_item.get("url") or ""),
            str(old_item.get("pick") or ""),
        )
        if legacy_identity != (site.name, site.url, site.pick):
            conflicts[name] = "旧缓存站点身份与正式配置不一致，拒绝混合历史"
            continue
        old_data = old_item.get("data")
        if not isinstance(old_data, dict):
            conflicts[name] = "旧缓存 data 缺失"
            continue
        missing = [issue for issue in retained_issues if str(issue) not in old_data]
        if missing:
            conflicts[name] = "旧缓存缺少 " + ",".join(f"{issue}期" for issue in missing)
            continue
        records = {
            str(issue): cache_entry_from_match(
                _legacy_confirmed_match(site, issue, str(old_data[str(issue)]))
            )
            for issue in retained_issues
        }
        records[str(period)] = cache_entry_from_match(by_issue[period])
        new_items.append(
            {
                "name": site.name,
                "url": site.url,
                "pick": site.pick,
                "parser": site.parser_id,
                "anchors": list(site.anchors),
                "records": records,
            }
        )

    accepted_names = {str(item["name"]) for item in new_items}
    updated: dict[str, object] = {
        "schema": CACHE_SCHEMA,
        "kind": CACHE_KIND,
        "state": CACHE_STATE_READY,
        "period": period,
        "window": 10,
        "issues": new_issues,
        "updated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "migration": {
            "from_schema": 1,
            "authorization": "user-confirmed-real-history",
            "legacy_sites": sorted(accepted_names),
        },
        "sites": new_items,
        "failures": [
            {"name": name, "error": reason, "url": url}
            for name, reason, url in failures
        ],
    }
    return validate_cache_for_update(updated), conflicts

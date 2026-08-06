# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime as dt

from ..domain import Match, Site
from .validation import (
    CACHE_KIND,
    CACHE_SCHEMA,
    CACHE_STATE_BOOTSTRAP,
    CACHE_STATE_READY,
    CacheValidationError,
    cache_entry_from_match,
    validate_cache_for_update,
    validate_cache_payload,
    validate_legacy_cache_payload,
)

def _site_cache_item_for_issues(
    site: Site, matches: dict[int, Match], issues: list[int]
) -> dict[str, object]:
    if set(matches) != set(issues):
        raise CacheValidationError(f"{site.name} 缓存数据与当前连续期数不一致，拒绝写入")
    return {
        "name": site.name,
        "url": site.url,
        "pick": site.pick,
        "parser": site.parser_id,
        "anchors": list(site.anchors),
        "records": {str(issue): cache_entry_from_match(matches[issue]) for issue in issues},
    }


def site_cache_item(site: Site, matches: dict[int, Match], issues: list[int]) -> dict[str, object]:
    if len(issues) != 10:
        raise CacheValidationError(f"{site.name} 缓存数据不是完整10期，拒绝写入")
    return _site_cache_item_for_issues(site, matches, issues)


def _build_cache_payload(
    period: int,
    issues: list[int],
    rows: dict[str, tuple[Site, dict[int, Match]]],
    failures: list[tuple[str, str, str]],
    state: str,
) -> dict[str, object]:
    if state == CACHE_STATE_BOOTSTRAP and not rows:
        raise CacheValidationError("启动缓存没有任何通过站点来源证据，拒绝覆盖旧缓存")
    payload: dict[str, object] = {
        "schema": CACHE_SCHEMA,
        "kind": CACHE_KIND,
        "state": state,
        "period": period,
        "window": 10,
        "issues": list(issues),
        "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "sites": [],
        "failures": [
            {"name": name, "error": reason, "url": url}
            for name, reason, url in failures
        ],
    }
    payload["sites"] = [
        _site_cache_item_for_issues(site, by_issue, issues)
        for _name, (site, by_issue) in sorted(rows.items())
    ]
    return validate_cache_for_update(payload)


def build_cache_payload(
    period: int,
    issues: list[int],
    rows: dict[str, tuple[Site, dict[int, Match]]],
    failures: list[tuple[str, str, str]],
) -> dict[str, object]:
    if len(issues) != 10 or issues != list(range(issues[0], issues[0] + 10)) or issues[-1] != period:
        raise CacheValidationError("重建缓存必须提供连续完整10期，且最后一期等于 period")
    payload = _build_cache_payload(
        period, issues, rows, failures, CACHE_STATE_READY
    )
    return validate_cache_payload(payload)


def build_bootstrap_cache_payload(
    period: int,
    issues: list[int],
    rows: dict[str, tuple[Site, dict[int, Match]]],
    failures: list[tuple[str, str, str]],
) -> dict[str, object]:
    if (
        not 1 <= len(issues) < 10
        or issues != list(range(issues[0], issues[0] + len(issues)))
        or issues[-1] != period
    ):
        raise CacheValidationError("启动缓存必须提供连续1到9期，且最后一期等于 period")
    return _build_cache_payload(
        period, issues, rows, failures, CACHE_STATE_BOOTSTRAP
    )


def build_legacy_cache_payload(
    period: int,
    issues: list[int],
    rows: dict[str, tuple[Site, dict[int, Match]]],
    failures: list[tuple[str, str, str]],
) -> dict[str, object]:
    if (
        len(issues) != 10
        or issues != list(range(issues[0], issues[0] + 10))
        or issues[-1] != period
    ):
        raise CacheValidationError("旧缓存重建必须提供连续完整10期，且最后一期等于 period")
    sites: list[dict[str, object]] = []
    for name, (site, by_issue) in sorted(rows.items()):
        if set(by_issue) != set(issues):
            raise CacheValidationError(f"{name} 缓存数据不是完整连续10期")
        sites.append(
            {
                "name": site.name,
                "url": site.url,
                "pick": site.pick,
                "data": {str(issue): by_issue[issue].value for issue in issues},
            }
        )
    payload: dict[str, object] = {
        "schema": 1,
        "kind": CACHE_KIND,
        "period": period,
        "window": 10,
        "issues": list(issues),
        "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "sites": sites,
        "failures": [
            {"name": name, "error": reason, "url": url}
            for name, reason, url in failures
        ],
    }
    return validate_legacy_cache_payload(payload)


def _site_identity_from_item(item: dict[str, object]) -> tuple[str, str, str, str, tuple[str, ...]]:
    return (
        *(str(item[field]) for field in ("name", "url", "pick", "parser")),
        tuple(str(anchor) for anchor in item["anchors"]),
    )


def _site_identity_from_site(site: Site) -> tuple[str, str, str, str, tuple[str, ...]]:
    return site.name, site.url, site.pick, site.parser_id, tuple(site.anchors)

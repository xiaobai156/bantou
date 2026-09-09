# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime as dt

from ..domain.models import Match, Site
from .validation import (
    CACHE_KIND,
    CACHE_SCHEMA,
    CACHE_STATE_BOOTSTRAP,
    CacheValidationError,
    cache_entry_from_match,
    validate_cache_for_update,
)


def _site_cache_item_for_issues(
    site: Site,
    matches: dict[int, Match],
    issues: list[int],
    period_failures: dict[int, str] | None = None,
) -> dict[str, object]:
    issue_set = set(issues)
    if any(type(issue) is not int or match.issue != issue for issue, match in matches.items()):
        raise CacheValidationError("缓存键与实际抓取期数不一致")
    if not matches or not set(matches) <= issue_set:
        raise CacheValidationError(f"{site.name} 缓存数据不在当前连续期数内，拒绝写入")
    failures = dict(period_failures or {})
    missing = issue_set - set(matches)
    if not period_failures:
        failures = {issue: "该期没有可信来源数据" for issue in missing}
    if set(failures) != missing or any(not str(reason).strip() for reason in failures.values()):
        raise CacheValidationError(f"{site.name} 缺失期失败标记不完整，拒绝写入")
    item: dict[str, object] = {
        "name": site.name,
        "url": site.url,
        "pick": site.pick,
        "parser": site.parser_id,
        "anchors": list(site.anchors),
        "fetch_url": site.fetch_url,
        "entry_mode": site.entry_mode,
        "records": {
            str(issue): cache_entry_from_match(matches[issue])
            for issue in issues
            if issue in matches
        },
    }
    if failures:
        item["failures"] = {
            str(issue): failures[issue] for issue in issues if issue in failures
        }
    return item


def _build_cache_payload(
    period: int,
    issues: list[int],
    rows: dict[str, tuple[Site, dict[int, Match]]],
    failures: list[tuple[str, str, str]],
    state: str,
) -> dict[str, object]:
    failure_names = {name for name, _reason, _url in failures}
    cache_rows = {name: row for name, row in rows.items() if name not in failure_names}
    if state == CACHE_STATE_BOOTSTRAP and not cache_rows:
        raise CacheValidationError("启动缓存没有任何通过站点来源证据，拒绝覆盖旧缓存")
    payload: dict[str, object] = {
        "schema": CACHE_SCHEMA,
        "kind": CACHE_KIND,
        "state": state,
        "period": period,
        "window": 10,
        "issues": list(issues),
        "updated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "sites": [],
        "failures": [
            {"name": name, "error": reason, "url": url}
            for name, reason, url in failures
        ],
    }
    payload["sites"] = [
        _site_cache_item_for_issues(site, by_issue, issues)
        for _name, (site, by_issue) in sorted(cache_rows.items())
    ]
    return validate_cache_for_update(payload)


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


def _site_identity_from_item(item: dict[str, object]) -> tuple[str, str, str, str, tuple[str, ...], str, str]:
    return (
        *(str(item[field]) for field in ("name", "url", "pick", "parser")),
        tuple(str(anchor) for anchor in item["anchors"]),
        str(item.get("fetch_url") or ""),
        str(item.get("entry_mode") or "direct"),
    )


def _site_identity_from_site(site: Site) -> tuple[str, str, str, str, tuple[str, ...], str, str]:
    return site.name, site.url, site.pick, site.parser_id, tuple(site.anchors), site.fetch_url, site.entry_mode

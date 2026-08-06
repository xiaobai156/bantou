# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime as dt
import json

from ..domain import Match, Site
from .builders import (
    _site_cache_item_for_issues,
    _site_identity_from_item,
    _site_identity_from_site,
)
from .validation import (
    CACHE_KIND,
    CACHE_SCHEMA,
    CACHE_STATE_BOOTSTRAP,
    CACHE_STATE_READY,
    CacheValidationError,
    _entry_source,
    _validate_entry,
    cache_entry_from_match,
    compare_cached_match,
    validate_cache_for_update,
)

def merge_cache_updates(
    payload: dict[str, object],
    incoming: dict[str, tuple[Site, dict[int, Match]]],
    failures: list[tuple[str, str, str]],
) -> tuple[dict[str, object], dict[str, str]]:
    """Merge verified in-window cache updates without overwriting conflicts.

    The returned payload is a deep copy.  Conflicts describe cache-only update
    diagnostics; callers must not use them to reclassify the live crawl result.
    """
    original = validate_cache_for_update(payload)
    updated = json.loads(json.dumps(original, ensure_ascii=False))
    issues = {int(issue) for issue in updated["issues"]}
    items = {str(item["name"]): item for item in updated["sites"]}
    bootstrap = updated.get("state") == CACHE_STATE_BOOTSTRAP
    conflicts: dict[str, str] = {}

    for name, (site, by_issue) in incoming.items():
        item = items.get(name)
        if item is None:
            if bootstrap and set(by_issue) == issues:
                try:
                    item = _site_cache_item_for_issues(
                        site, by_issue, [int(issue) for issue in updated["issues"]]
                    )
                except CacheValidationError as exc:
                    conflicts[name] = str(exc)
                    continue
                updated["sites"].append(item)
                items[name] = item
                continue
            conflicts[name] = "缓存中没有该站完整10期来源证据，拒绝补写"
            continue
        if _site_identity_from_item(item) != _site_identity_from_site(site):
            conflicts[name] = "缓存站点身份与正式配置不一致，拒绝混合历史"
            continue
        if not set(by_issue) <= issues:
            conflicts[name] = "重跑期数不在最近10期缓存窗口，拒绝写入"
            continue
        records = item["records"]
        assert isinstance(records, dict)
        conflict_reason = None
        for issue, match in sorted(by_issue.items()):
            cached = records.get(str(issue))
            if not isinstance(cached, dict):
                conflict_reason = f"{issue}期缓存来源证据缺失"
                break
            reason = compare_cached_match(cached, match)
            if reason is not None:
                conflict_reason = f"{issue}期{reason}"
                break
        if conflict_reason is not None:
            conflicts[name] = conflict_reason
            continue
        for issue, match in by_issue.items():
            records[str(issue)] = cache_entry_from_match(match)

    accepted_names = set(incoming) - set(conflicts)
    existing_failures = [
        item for item in updated.get("failures", [])
        if str(item.get("name") or "") not in accepted_names
    ]
    failure_names = {name for name, _reason, _url in failures}
    existing_failures = [
        item for item in existing_failures
        if str(item.get("name") or "") not in failure_names
    ]
    existing_failures.extend(
        {"name": name, "error": reason, "url": url}
        for name, reason, url in failures
    )
    updated["failures"] = existing_failures
    return validate_cache_for_update(updated), conflicts

def roll_cache_payload(
    payload: dict[str, object],
    period: int,
    all_sites: list[Site],
    incoming: dict[str, tuple[Site, dict[int, Match]]],
    failures: list[tuple[str, str, str]],
) -> tuple[dict[str, object], dict[str, str]]:
    """Advance a schema-2 cache by one period after live results are finalized.

    Cache continuity and identity conflicts remain cache diagnostics and never
    decide whether a live single-period result is successful.
    """
    original = validate_cache_for_update(payload)
    old_period = int(original["period"])
    if period == old_period:
        return merge_cache_updates(original, incoming, failures)
    if period != old_period + 1:
        raise CacheValidationError(
            f"缓存最后一期是 {old_period}，当前期是 {period}，不能跨期滚动；请真实抓取连续10期并使用 --rebuild-cache"
        )

    old_issues = [int(issue) for issue in original["issues"]]
    retained_issues = old_issues if len(old_issues) < 10 else old_issues[1:]
    new_issues = retained_issues + [period]
    old_items = {str(item["name"]): item for item in original["sites"]}
    current_by_name = {site.name: site for site in all_sites}
    conflicts: dict[str, str] = {}
    new_items: list[dict[str, object]] = []
    failure_names = {name for name, _reason, _url in failures}

    for name, site in current_by_name.items():
        current = incoming.get(name)
        if current is None:
            continue
        incoming_site, by_issue = current
        if set(by_issue) != {period}:
            conflicts[name] = "单期缓存滚动必须只包含当前指定期数"
            continue
        old_item = old_items.get(name)
        if old_item is None:
            conflicts[name] = "缓存中没有该站完整10期来源证据，拒绝跨期混合"
            continue
        if _site_identity_from_item(old_item) != _site_identity_from_site(incoming_site):
            conflicts[name] = "缓存站点身份与正式配置不一致，拒绝混合历史"
            continue
        old_records = old_item.get("records")
        if not isinstance(old_records, dict):
            conflicts[name] = "缓存 records 缺失"
            continue
        try:
            records = {str(issue): old_records[str(issue)] for issue in retained_issues}
            records[str(period)] = cache_entry_from_match(by_issue[period])
            new_items.append(_site_cache_item_for_issues(
                incoming_site,
                {
                    issue: by_issue[period] if issue == period else _match_from_cache(issue, records[str(issue)])
                    for issue in new_issues
                },
                new_issues,
            ))
        except CacheValidationError as exc:
            conflicts[name] = str(exc)

    accepted_names = {str(item["name"]) for item in new_items}
    cached_failures = [
        item for item in original.get("failures", [])
        if str(item.get("name") or "") in current_by_name
        and str(item.get("name") or "") not in accepted_names
        and str(item.get("name") or "") not in failure_names
    ]
    cached_failures.extend(
        {"name": name, "error": reason, "url": url}
        for name, reason, url in failures
    )
    state = (
        CACHE_STATE_READY
        if len(new_issues) == 10
        else CACHE_STATE_BOOTSTRAP
    )
    rebuilt: dict[str, object] = {
        "schema": CACHE_SCHEMA,
        "kind": CACHE_KIND,
        "state": state,
        "period": period,
        "window": 10,
        "issues": new_issues,
        "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "sites": new_items,
        "failures": cached_failures,
    }
    return validate_cache_for_update(rebuilt), conflicts


def _match_from_cache(issue: int, entry: object) -> Match:
    if not isinstance(entry, dict):
        raise CacheValidationError(f"{issue}期缓存记录不存在")
    _validate_entry(entry, issue, allow_confirmed_legacy=True)
    source = _entry_source(entry)
    return Match(
        issue=issue,
        issue_text=str(issue),
        value=str(entry["value"]),
        snippet=str(source["snippet"]),
        order=int(entry["order"]),
        position=int(entry["position"]),
        source_url=str(source["url"]),
        source_kind=str(source["kind"]),
        record_id=str(source["record_id"]),
        record_path=str(source["record_path"]),
        route_type=str(source["route_type"]),
        url_record_id=str(source["url_record_id"]),
        api_url=str(source["api_url"]),
        title=str(source["title"]),
        author=str(source["author"]),
        anchor_text=str(entry["anchor_text"]),
        anchor_position=int(entry["anchor_position"]),
        block_id=str(entry["block_id"]),
        block_start=int(entry["block_start"]),
        block_end=int(entry["block_end"]),
        container_id=str(source["container_id"]),
        table_column=str(source["table_column"]),
        document_authority=str(source["document_authority"]),
        rule_id=str(source["rule_id"]),
    )

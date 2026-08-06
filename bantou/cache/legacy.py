# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime as dt
import json

from ..domain import Match, Site
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
    conflicts: dict[str, str] = {}
    new_items: list[dict[str, object]] = []

    for name, (site, by_issue) in incoming.items():
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
        "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
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

def merge_legacy_complete_updates(
    payload: dict[str, object],
    incoming: dict[str, tuple[Site, dict[int, Match]]],
    failures: list[tuple[str, str, str]],
) -> tuple[dict[str, object], dict[str, str]]:
    original = validate_legacy_cache_payload(payload)
    updated = json.loads(json.dumps(original, ensure_ascii=False))
    issues = [int(issue) for issue in updated["issues"]]
    issue_set = set(issues)
    items = {str(item["name"]): item for item in updated["sites"]}
    conflicts: dict[str, str] = {}

    for name, (site, by_issue) in incoming.items():
        if set(by_issue) != issue_set:
            conflicts[name] = "完整10期修复必须真实抓到缓存窗口全部期数"
            continue
        existing = items.get(name)
        if existing is not None:
            identity = (
                str(existing.get("name") or ""),
                str(existing.get("url") or ""),
                str(existing.get("pick") or ""),
            )
            if identity != (site.name, site.url, site.pick):
                conflicts[name] = "旧缓存站点身份与正式配置不一致，拒绝混合历史"
                continue
            old_data = existing.get("data")
            if not isinstance(old_data, dict):
                conflicts[name] = "旧缓存 data 缺失"
                continue
            differences = [
                issue for issue in issues
                if str(old_data.get(str(issue), "")) != by_issue[issue].value
            ]
            if differences:
                conflicts[name] = (
                    "完整10期与旧缓存冲突："
                    + ",".join(f"{issue}期" for issue in differences)
                )
                continue
        else:
            item = {
                "name": site.name,
                "url": site.url,
                "pick": site.pick,
                "data": {str(issue): by_issue[issue].value for issue in issues},
            }
            updated["sites"].append(item)
            items[name] = item

    accepted_names = set(incoming) - set(conflicts)
    pending = updated.get("pending_recovery", [])
    if isinstance(pending, list):
        updated["pending_recovery"] = [
            item
            for item in pending
            if str(item.get("name") or "") not in accepted_names
        ]
        if not updated["pending_recovery"]:
            updated.pop("pending_recovery", None)
    complete_names = {str(item.get("name") or "") for item in updated["sites"]}
    failure_names = {name for name, _reason, _url in failures}
    existing_failures = [
        item for item in updated.get("failures", [])
        if str(item.get("name") or "") not in accepted_names
        and str(item.get("name") or "") not in complete_names
        and str(item.get("name") or "") not in failure_names
    ]
    existing_failures.extend(
        {"name": name, "error": reason, "url": url}
        for name, reason, url in failures
    )
    updated["failures"] = existing_failures
    updated["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    return validate_legacy_cache_payload(updated), conflicts


def roll_legacy_cache_payload(
    payload: dict[str, object],
    period: int,
    all_sites: list[Site],
    incoming: dict[str, tuple[Site, dict[int, Match]]],
    failures: list[tuple[str, str, str]],
) -> tuple[dict[str, object], dict[str, str]]:
    """Advance the current production schema-1 cache while preserving its shape."""
    original = validate_legacy_cache_payload(payload)
    old_period = int(original["period"])
    if period not in {old_period, old_period + 1}:
        raise CacheValidationError(
            f"缓存最后一期是 {old_period}，当前期是 {period}，不能跨期滚动"
        )
    old_issues = [int(issue) for issue in original["issues"]]
    retained_issues = old_issues if period == old_period else old_issues[1:]
    new_issues = retained_issues if period == old_period else retained_issues + [period]
    old_items = {str(item["name"]): item for item in original["sites"]}
    old_failure_reasons = {
        str(item.get("name") or ""): str(item.get("error") or "")
        for item in original.get("failures", [])
        if isinstance(item, dict)
    }
    pending_items = {
        str(item["name"]): item
        for item in original.get("pending_recovery", [])
        if isinstance(item, dict) and item.get("name")
    }
    conflicts: dict[str, str] = {}

    def legacy_identity(item: dict[str, object], site: Site) -> bool:
        return (
            str(item.get("name") or ""),
            str(item.get("url") or ""),
            str(item.get("pick") or ""),
        ) == (site.name, site.url, site.pick)

    if period == old_period:
        new_items = [
            json.loads(json.dumps(item, ensure_ascii=False))
            for item in original["sites"]
        ]
        items_by_name = {str(item["name"]): item for item in new_items}
        pending_by_name = {
            name: json.loads(json.dumps(item, ensure_ascii=False))
            for name, item in pending_items.items()
        }
    else:
        new_items = []
        items_by_name = {}
        pending_by_name = {
            name: json.loads(json.dumps(item, ensure_ascii=False))
            for name, item in pending_items.items()
        }

    for name, (site, by_issue) in incoming.items():
        if set(by_issue) != {period}:
            conflicts[name] = "单期缓存滚动必须只包含当前指定期数"
            continue
        old_item = old_items.get(name) or pending_items.get(name)
        if old_item is None:
            conflicts[name] = "旧缓存中没有该站完整10期，拒绝混合历史"
            prior_reason = old_failure_reasons.get(name)
            if prior_reason and not prior_reason.startswith("旧缓存中没有该站完整10期"):
                conflicts[name] += f"；缺失根因：{prior_reason}"
            continue
        if not legacy_identity(old_item, site):
            conflicts[name] = "旧缓存站点身份与正式配置不一致，拒绝混合历史"
            continue
        old_data = old_item.get("data")
        if not isinstance(old_data, dict):
            conflicts[name] = "旧缓存 data 缺失"
            continue
        missing = [
            issue
            for issue in retained_issues
            if issue != period and str(issue) not in old_data
        ]
        if missing:
            conflicts[name] = (
                "旧缓存缺少 " + ",".join(f"{issue}期" for issue in missing)
            )
            continue
        current_value = by_issue[period].value
        if period == old_period or name in pending_items:
            cached_value = str(old_data.get(str(period), ""))
            if cached_value and cached_value != current_value:
                conflicts[name] = (
                    f"{period}期本次值 {current_value} 与旧缓存值 {cached_value} 冲突"
                )
                continue
            item = items_by_name.get(name)
            if item is None:
                item = {
                    "name": site.name,
                    "url": site.url,
                    "pick": site.pick,
                    "data": {
                        str(issue): str(old_data[str(issue)])
                        for issue in new_issues
                        if issue != period and str(issue) in old_data
                    },
                }
                new_items.append(item)
                items_by_name[name] = item
            item["data"][str(period)] = current_value
            pending_by_name.pop(name, None)
            continue
        new_items.append(
            {
                "name": site.name,
                "url": site.url,
                "pick": site.pick,
                "data": {
                    **{str(issue): str(old_data[str(issue)]) for issue in retained_issues},
                    str(period): current_value,
                },
            }
        )
        pending_by_name.pop(name, None)

    accepted_names = {name for name in incoming if name not in conflicts}
    if period != old_period:
        for name, item in old_items.items():
            if name not in accepted_names:
                pending_by_name.setdefault(
                    name, json.loads(json.dumps(item, ensure_ascii=False))
                )
    complete_names = {str(item.get("name") or "") for item in new_items}
    failure_names = {name for name, _reason, _url in failures}
    existing_failures = [
        item for item in original.get("failures", [])
        if isinstance(item, dict)
        and str(item.get("name") or "") not in accepted_names
        and str(item.get("name") or "") not in complete_names
        and str(item.get("name") or "") not in failure_names
    ]
    existing_failures.extend(
        {"name": name, "error": reason, "url": url}
        for name, reason, url in failures
    )
    updated = {
        "schema": 1,
        "kind": original.get("kind", CACHE_KIND),
        "period": period,
        "window": 10,
        "issues": new_issues,
        "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "sites": new_items,
        "failures": existing_failures,
    }
    if pending_by_name:
        updated["pending_recovery"] = list(pending_by_name.values())
    return validate_legacy_cache_payload(updated), conflicts

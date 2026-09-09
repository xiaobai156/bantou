# -*- coding: utf-8 -*-
"""Evidence-bearing recent-ten-period cache validation and construction."""

from __future__ import annotations

import json
from pathlib import Path

from ..domain.models import Match
from ..text import VALUE_RE, normalize_half_head_value, normalize_text

CACHE_SCHEMA = 2
CACHE_KIND = "bantou_recent_duplicate_backup"
CACHE_STATE_BOOTSTRAP = "bootstrap"
CACHE_STATE_READY = "ready"
CACHE_STATE_RESET = "reset"
LEGACY_CONFIRMED_SOURCE_KIND = "user-confirmed-legacy-cache"
LEGACY_CONFIRMED_STATUS = "user-confirmed-legacy"


class CacheValidationError(ValueError):
    pass


def _validate_half_head_value(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise CacheValidationError(f"{label}无效")
    normalized = normalize_text(value)
    match = VALUE_RE.fullmatch(normalized)
    if match is None or normalize_half_head_value(match.group(1), match.group(2)) != normalized:
        raise CacheValidationError(f"{label}无效")


def _validate_match_evidence(match: Match) -> None:
    _validate_half_head_value(match.value, "证据数据值")
    required = {
        "来源URL": match.source_url,
        "来源类型": match.source_kind,
        "原始片段": match.snippet,
        "方向权威": match.document_authority,
        "栏目锚点": match.anchor_text,
        "区块ID": match.block_id,
        "容器ID": match.container_id,
        "解析规则": match.rule_id,
    }
    missing = [label for label, value in required.items() if not str(value or "").strip()]
    if missing:
        raise CacheValidationError("证据不完整：缺少" + "、".join(missing))
    if match.source_kind == LEGACY_CONFIRMED_SOURCE_KIND:
        return
    if not isinstance(match.order, int) or match.order < 0:
        raise CacheValidationError("证据不完整：原始顺序无效")
    if not isinstance(match.position, int) or match.position < 0:
        raise CacheValidationError("证据不完整：原始位置无效")
    if not isinstance(match.anchor_position, int) or match.anchor_position < 0:
        raise CacheValidationError("证据不完整：栏目锚点位置无效")
    if not isinstance(match.block_start, int) or match.block_start < 0:
        raise CacheValidationError("证据不完整：区块起点无效")
    if not isinstance(match.block_end, int) or match.block_end <= match.block_start:
        raise CacheValidationError("证据不完整：区块终点无效")
    if match.source_kind in {"dynamic-record", "dynamic-record-browser"}:
        dynamic_required = {
            "记录ID": match.record_id,
            "记录路径": match.record_path,
            "路由类型": match.route_type,
            "URL记录ID": match.url_record_id,
            "接口URL": match.api_url,
            "标题": match.title,
            "作者": match.author,
        }
        if match.source_kind == "dynamic-record-browser":
            dynamic_required.pop("接口URL")
        missing_dynamic = [
            label for label, value in dynamic_required.items() if not str(value or "").strip()
        ]
        if missing_dynamic:
            raise CacheValidationError("证据不完整：动态记录缺少" + "、".join(missing_dynamic))


def cache_entry_from_match(match: Match) -> dict[str, object]:
    _validate_match_evidence(match)
    entry = {
        "value": match.value,
        "order": match.order,
        "position": match.position,
        "anchor_text": match.anchor_text,
        "anchor_position": match.anchor_position,
        "block_id": match.block_id,
        "block_start": match.block_start,
        "block_end": match.block_end,
        "source": {
            "url": match.source_url,
            "kind": match.source_kind,
            "record_id": match.record_id,
            "record_path": match.record_path,
            "route_type": match.route_type,
            "url_record_id": match.url_record_id,
            "api_url": match.api_url,
            "title": match.title,
            "author": match.author,
            "snippet": match.snippet,
            "container_id": match.container_id,
            "table_column": match.table_column,
            "document_authority": match.document_authority,
            "rule_id": match.rule_id,
        },
    }
    if match.source_kind == LEGACY_CONFIRMED_SOURCE_KIND:
        entry["evidence_status"] = LEGACY_CONFIRMED_STATUS
    return entry


def _entry_value(entry: dict[str, object], field: str) -> object:
    if field not in entry:
        raise CacheValidationError(f"缓存记录缺少 {field}")
    return entry[field]


def _entry_source(entry: dict[str, object]) -> dict[str, object]:
    source = _entry_value(entry, "source")
    if not isinstance(source, dict):
        raise CacheValidationError("缓存记录 source 必须是对象")
    for field in (
        "url", "kind", "record_id", "record_path", "route_type",
        "url_record_id", "api_url", "title", "author", "snippet",
        "container_id", "table_column", "document_authority", "rule_id",
    ):
        if field not in source:
            raise CacheValidationError(f"缓存来源证据缺少 {field}")
    return source


def compare_cached_match(cached: dict[str, object], current: Match) -> str | None:
    """Return a precise conflict reason instead of choosing either version."""
    try:
        expected = cache_entry_from_match(current)
    except CacheValidationError as exc:
        return f"本次{exc}"
    try:
        cached_value = str(_entry_value(cached, "value"))
        cached_order = int(_entry_value(cached, "order"))
        cached_position = int(_entry_value(cached, "position"))
        cached_anchor_text = str(_entry_value(cached, "anchor_text"))
        cached_anchor_position = int(_entry_value(cached, "anchor_position"))
        cached_block_id = str(_entry_value(cached, "block_id"))
        cached_block_start = int(_entry_value(cached, "block_start"))
        cached_block_end = int(_entry_value(cached, "block_end"))
        cached_source = _entry_source(cached)
    except (TypeError, ValueError) as exc:
        return f"缓存证据无效：{exc}"

    if cached_value != expected["value"]:
        return f"缓存数据冲突：缓存为{cached_value}，本次为{expected['value']}"
    if cached_order != expected["order"]:
        return f"缓存数据冲突：原始顺序缓存为{cached_order}，本次为{expected['order']}"
    if cached_position != expected["position"]:
        return f"缓存数据冲突：原始位置缓存为{cached_position}，本次为{expected['position']}"
    for label, cached_value, current_value in (
        ("栏目锚点", cached_anchor_text, expected["anchor_text"]),
        ("栏目锚点位置", cached_anchor_position, expected["anchor_position"]),
        ("区块ID", cached_block_id, expected["block_id"]),
        ("区块起点", cached_block_start, expected["block_start"]),
        ("区块终点", cached_block_end, expected["block_end"]),
    ):
        if cached_value != current_value:
            return f"缓存数据冲突：{label}缓存为{cached_value}，本次为{current_value}"

    current_source = expected["source"]
    if not isinstance(current_source, dict):
        return "本次来源证据无效"
    for label, field in (
        ("来源URL", "url"),
        ("来源类型", "kind"),
        ("路由类型", "route_type"),
        ("URL记录ID", "url_record_id"),
        ("记录ID", "record_id"),
        ("记录路径", "record_path"),
        ("接口URL", "api_url"),
        ("标题", "title"),
        ("作者", "author"),
        ("原始片段", "snippet"),
        ("容器ID", "container_id"),
        ("表格列", "table_column"),
        ("方向权威", "document_authority"),
        ("解析规则", "rule_id"),
    ):
        if str(cached_source[field]) != str(current_source[field]):
            return (
                f"缓存数据冲突：{label}缓存为{cached_source[field] or '空'}，"
                f"本次为{current_source[field] or '空'}"
            )
    return None


def _validate_entry(
    entry: object, issue: int, *, allow_confirmed_legacy: bool = False
) -> None:
    if not isinstance(entry, dict):
        raise CacheValidationError(f"{issue}期缓存记录必须是对象")
    legacy_confirmed = entry.get("evidence_status") == LEGACY_CONFIRMED_STATUS
    if legacy_confirmed and not allow_confirmed_legacy:
        raise CacheValidationError(
            f"{issue}期缓存只有用户确认历史，没有原始来源证据，不能用于正式判重"
        )
    _validate_half_head_value(_entry_value(entry, "value"), f"{issue}期缓存 value ")
    for field in (
        "order", "position", "anchor_position", "block_start", "block_end"
    ):
        value = _entry_value(entry, field)
        if not isinstance(value, int) or (not legacy_confirmed and value < 0):
            raise CacheValidationError(f"{issue}期缓存 {field} 无效")
    for field in ("anchor_text", "block_id"):
        value = _entry_value(entry, field)
        if not isinstance(value, str) or not value:
            raise CacheValidationError(f"{issue}期缓存 {field} 无效")
    if not legacy_confirmed and int(entry["block_end"]) <= int(entry["block_start"]):
        raise CacheValidationError(f"{issue}期缓存区块边界无效")
    source = _entry_source(entry)
    required_source = ("url", "kind", "snippet", "container_id", "document_authority", "rule_id")
    for field in required_source:
        if not isinstance(source[field], str) or not source[field].strip():
            raise CacheValidationError(f"{issue}期缓存来源证据 {field} 为空")
    if source["kind"] in {"dynamic-record", "dynamic-record-browser"}:
        fields = ("record_id", "record_path", "route_type", "url_record_id", "title", "author")
        if source["kind"] == "dynamic-record":
            fields += ("api_url",)
        if any(not isinstance(source[field], str) or not source[field].strip() for field in fields):
            raise CacheValidationError(f"{issue}期动态来源证据不完整")
        if source["record_id"] != source["url_record_id"]:
            raise CacheValidationError(f"{issue}期动态来源记录ID冲突")


def _validate_cache_payload(
    payload: object, *, allow_bootstrap: bool, allow_confirmed_legacy: bool
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise CacheValidationError("缓存顶层必须是对象")
    if payload.get("schema") != CACHE_SCHEMA:
        raise CacheValidationError(
            f"缓存 schema 必须是 {CACHE_SCHEMA}；旧 schema 缺少原始位置和来源证据，禁止自动覆盖"
        )
    if payload.get("kind") != CACHE_KIND:
        raise CacheValidationError("缓存 kind 不匹配")
    state = payload.get("state", CACHE_STATE_READY)
    if state not in {CACHE_STATE_BOOTSTRAP, CACHE_STATE_READY}:
        raise CacheValidationError("缓存 state 无效")
    if state == CACHE_STATE_BOOTSTRAP and not allow_bootstrap:
        raise CacheValidationError("启动缓存尚未积累满10期，禁止重复检测或新增站点判重")
    period = payload.get("period")
    window = payload.get("window")
    issues = payload.get("issues")
    if not isinstance(period, int) or not isinstance(window, int) or window != 10:
        raise CacheValidationError("缓存 period/window 无效，window 必须为10")
    if not isinstance(issues, list) or not all(isinstance(issue, int) for issue in issues):
        if state == CACHE_STATE_READY:
            raise CacheValidationError("缓存 issues 必须是完整连续10期")
        raise CacheValidationError("启动缓存 issues 必须是连续1到9期")
    if state == CACHE_STATE_READY:
        if len(issues) != 10:
            raise CacheValidationError("缓存 issues 必须是完整连续10期")
    elif not 1 <= len(issues) < 10:
        raise CacheValidationError("启动缓存 issues 必须是连续1到9期")
    if issues != list(range(issues[0], issues[0] + len(issues))) or issues[-1] != period:
        raise CacheValidationError("缓存 issues 必须连续且最后一期等于 period")

    sites = payload.get("sites")
    if not isinstance(sites, list):
        raise CacheValidationError("缓存 sites 必须是数组")
    identities: set[tuple[str, str, str, str]] = set()
    site_names: set[str] = set()
    issue_keys = {str(issue) for issue in issues}
    for item in sites:
        if not isinstance(item, dict):
            raise CacheValidationError("缓存站点必须是对象")
        fields = ("name", "url", "pick", "parser", "anchors", "records")
        if any(field not in item for field in fields):
            raise CacheValidationError("缓存站点缺少身份或 records 字段")
        identity = tuple(str(item[field]) for field in ("name", "url", "pick", "parser"))
        if not all(identity):
            raise CacheValidationError("缓存站点身份不能为空")
        if identity in identities:
            raise CacheValidationError(f"缓存站点身份重复：{identity[0]}")
        identities.add(identity)
        if identity[0] in site_names:
            raise CacheValidationError(f"缓存站点名称重复：{identity[0]}")
        site_names.add(identity[0])
        if identity[2] not in {"top", "bottom"}:
            raise CacheValidationError(f"缓存站点方向无效：{identity[0]}")
        anchors = item["anchors"]
        if (
            not isinstance(anchors, list)
            or not anchors
            or any(not isinstance(anchor, str) or not anchor.strip() for anchor in anchors)
            or len(set(anchors)) != len(anchors)
        ):
            raise CacheValidationError(f"缓存站点 anchors 无效：{identity[0]}")
        records = item["records"]
        record_keys = set(records) if isinstance(records, dict) else set()
        if not isinstance(records, dict) or not records or not record_keys <= issue_keys:
            raise CacheValidationError(f"缓存站点 records 无效：{identity[0]}")
        site_failures = item.get("failures", {})
        if not isinstance(site_failures, dict):
            raise CacheValidationError(f"缓存站点 failures 无效：{identity[0]}")
        failure_keys = set(site_failures)
        if (
            not failure_keys <= issue_keys
            or record_keys & failure_keys
            or record_keys | failure_keys != issue_keys
            or any(not isinstance(reason, str) or not reason.strip() for reason in site_failures.values())
        ):
            raise CacheValidationError(f"缓存站点逐期成功/失败状态不完整：{identity[0]}")
        for issue_text, entry in records.items():
            issue = int(issue_text)
            _validate_entry(
                entry,
                issue,
                allow_confirmed_legacy=allow_confirmed_legacy,
            )
    failures = payload.get("failures", [])
    if not isinstance(failures, list):
        raise CacheValidationError("缓存 failures 必须是数组")
    failure_names: set[str] = set()
    for failure in failures:
        if not isinstance(failure, dict):
            raise CacheValidationError("缓存 failure 必须是对象")
        values = tuple(failure.get(field) for field in ("name", "error", "url"))
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise CacheValidationError("缓存 failure 缺少 name/error/url")
        name = str(values[0])
        if name in failure_names:
            raise CacheValidationError(f"缓存失败站点重复：{name}")
        if name in site_names:
            raise CacheValidationError(f"缓存站点同时成功和失败：{name}")
        failure_names.add(name)
    return payload


def validate_cache_payload(payload: object) -> dict[str, object]:
    """Validate a ready ten-period cache used for duplicate decisions."""
    return _validate_cache_payload(
        payload,
        allow_bootstrap=False,
        allow_confirmed_legacy=False,
    )


def validate_cache_for_update(payload: object) -> dict[str, object]:
    """Validate either a ready cache or a not-yet-complete evidence bootstrap."""
    return _validate_cache_payload(
        payload,
        allow_bootstrap=True,
        allow_confirmed_legacy=True,
    )


def validate_reset_cache_payload(payload: object) -> dict[str, object]:
    """Validate the explicit empty-cache marker used before a new crawl."""
    if not isinstance(payload, dict):
        raise CacheValidationError("重置缓存顶层必须是对象")
    if payload.get("schema") != CACHE_SCHEMA:
        raise CacheValidationError(f"重置缓存 schema 必须是 {CACHE_SCHEMA}")
    if payload.get("kind") != CACHE_KIND:
        raise CacheValidationError("重置缓存 kind 不匹配")
    if payload.get("state") != CACHE_STATE_RESET:
        raise CacheValidationError("重置缓存 state 无效")
    if payload.get("period") is not None:
        raise CacheValidationError("重置缓存 period 必须为空")
    if payload.get("window") != 10:
        raise CacheValidationError("重置缓存 window 必须为10")
    if payload.get("issues") != []:
        raise CacheValidationError("重置缓存 issues 必须为空数组")
    if payload.get("sites") != []:
        raise CacheValidationError("重置缓存 sites 必须为空数组")
    if payload.get("failures") != []:
        raise CacheValidationError("重置缓存 failures 必须为空数组")
    return payload


def _read_cache_raw(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CacheValidationError(f"缓存无法读取：{exc}") from exc
    if not isinstance(payload, dict):
        raise CacheValidationError("缓存顶层必须是对象")
    return payload


def read_cache(path: Path) -> dict[str, object]:
    return validate_cache_payload(_read_cache_raw(path))


def validate_legacy_cache_payload(payload: object) -> dict[str, object]:
    """Validate the current production schema-1 cache without adding evidence."""
    if not isinstance(payload, dict):
        raise CacheValidationError("旧缓存顶层必须是对象")
    if payload.get("schema") != 1:
        raise CacheValidationError("旧缓存 schema 必须是 1")
    period = payload.get("period")
    window = payload.get("window")
    issues = payload.get("issues")
    sites = payload.get("sites")
    if not isinstance(period, int) or window != 10:
        raise CacheValidationError("旧缓存缺少有效 period/window")
    if (
        not isinstance(issues, list)
        or len(issues) != 10
        or any(not isinstance(issue, int) for issue in issues)
        or issues != list(range(issues[0], issues[0] + 10))
        or issues[-1] != period
    ):
        raise CacheValidationError("旧缓存 issues 必须是连续10期且最后一期等于 period")
    if not isinstance(sites, list):
        raise CacheValidationError("旧缓存 sites 必须是数组")
    issue_keys = {str(issue) for issue in issues}
    for item in sites:
        if not isinstance(item, dict):
            raise CacheValidationError("旧缓存站点必须是对象")
        for field in ("name", "url", "pick", "data"):
            if field not in item:
                raise CacheValidationError(f"旧缓存站点缺少 {field}")
        data = item["data"]
        if not isinstance(data, dict):
            raise CacheValidationError("旧缓存站点 data 必须是对象")
        missing = issue_keys - set(data)
        if missing:
            raise CacheValidationError(
                f"{item.get('name', '未知站点')} 旧缓存缺少 {','.join(sorted(missing))}期"
            )
        for issue_text in issue_keys:
            value = data.get(issue_text)
            _validate_half_head_value(
                value, f"{item.get('name', '未知站点')} {issue_text}期旧缓存值"
            )
    failures = payload.get("failures", [])
    if failures is not None and not isinstance(failures, list):
        raise CacheValidationError("旧缓存 failures 必须是数组")
    pending = payload.get("pending_recovery", [])
    if pending is not None and not isinstance(pending, list):
        raise CacheValidationError("旧缓存 pending_recovery 必须是数组")
    for item in pending or []:
        if not isinstance(item, dict):
            raise CacheValidationError("旧缓存待恢复站点必须是对象")
        for field in ("name", "url", "pick", "data"):
            if field not in item:
                raise CacheValidationError(f"旧缓存待恢复站点缺少 {field}")
        data = item["data"]
        if not isinstance(data, dict) or not data:
            raise CacheValidationError("旧缓存待恢复站点 data 无效")
        for value in data.values():
            _validate_half_head_value(value, "旧缓存待恢复站点 data 值")
    return payload


def read_cache_for_update(
    path: Path, *, allow_legacy_bootstrap: bool = False
) -> dict[str, object]:
    """Read cache data for an authorized update path.

    A caller may explicitly allow a user-confirmed schema-1 history baseline
    for single-period rolling. That baseline remains ineligible for duplicate
    detection and is never treated as source evidence.
    """
    payload = _read_cache_raw(path)
    if payload.get("state") == CACHE_STATE_RESET:
        return validate_reset_cache_payload(payload)
    if payload.get("schema") == 1 and allow_legacy_bootstrap:
        return validate_legacy_cache_payload(payload)
    if payload.get("schema") == 1:
        raise CacheValidationError(
            "正式缓存只接受 schema=2；schema=1 缺少来源证据，禁止自动迁移、滚动或判重"
        )
    return validate_cache_for_update(payload)

# -*- coding: utf-8 -*-
import re
from dataclasses import replace

from ..documents.content import author_context_matches_site, iter_search_texts
from ..domain.models import Match, Site
from ..site_profiles.registry import (
    DEDICATED_RENDERED_AUTHOR_CONTEXT_URLS,
    DEDICATED_RENDERED_PAGE_IDENTITIES,
    DEDICATED_RENDERED_SITE_RULES,
    DEFAULT_KEYWORDS,
    SITE_BROWSER_HTML_URLS,
    SITE_CURRENT_SERIES_PLACEHOLDER_URLS,
    SITE_IFRAME_PAGE_AUTHORITY_URLS,
    SITE_RENDERED_PAGE_AUTHORITY_URLS,
    SITE_SPECIAL_VALUE_PATTERNS,
    SITE_TARGET_PLACEHOLDER_URLS,
)
from ..text import (
    ISSUE_RE,
    compact_line,
    normalize_half_head_value,
    normalize_text,
    original_issue_position,
    source_issue_token_positions,
    source_text_without_hidden_html,
)
from .dedicated import special_matches_in_documents
from .segments import (
    focused_half_head_block,
    iter_issue_segments,
    segment_has_body_locator,
    half_head_values_in_segment,
    segment_quantity_valid,
    strict_segment_has_keyword,
    strict_values_in_segment,
    values_in_segment,
)


def special_matches_in_text(
    text: str,
    wanted_issues: set[int],
    site: Site | None,
    *,
    placeholder_issues: set[int] | None = None,
) -> list[tuple[int, str, str, int]]:
    if site is None:
        return []

    patterns = SITE_SPECIAL_VALUE_PATTERNS.get(site.url, ())
    if not patterns:
        return []

    normalized = normalize_text(text)
    found: list[tuple[int, str, str, int]] = []
    seen: set[tuple[int, str, int]] = set()
    for pattern in patterns:
        for match in pattern.finditer(normalized):
            issue = int(match.group(1))
            if issue not in wanted_issues:
                continue
            value = normalize_half_head_value(match.group(2), match.group(3))
            if value is None:
                continue
            key = (issue, value, match.start())
            if key in seen:
                continue
            matched_text = match.group(0)
            is_placeholder = re.search(r"[?？]{2,}", matched_text) is not None
            placeholder_allowed = (
                is_placeholder
                and placeholder_issues is not None
                and issue in placeholder_issues
            )
            if is_placeholder and not placeholder_allowed:
                continue
            if not placeholder_allowed and not segment_has_body_locator(matched_text):
                continue
            issues = {int(item.group(1)) for item in ISSUE_RE.finditer(normalize_text(matched_text))}
            if issues != {issue}:
                continue
            seen.add(key)
            snippet = compact_line(matched_text)
            record = next((segment for number, _token, segment, position
                           in iter_issue_segments(normalized, {issue})
                           if number == issue and position == match.start()), matched_text)
            record_values = half_head_values_in_segment(record)
            if value not in record_values:
                record_values.insert(0, value)
            for record_value in record_values:
                found.append((issue, record_value, compact_line(record), match.start()))
    return found


def _source_block_bounds(
    document: str,
    searched_text: str,
    issue_text: str,
    searched_position: int,
    value: str,
) -> tuple[int, int] | None:
    if hasattr(searched_text, "source_position"):
        return searched_text.source_position, searched_text.source_row_end
    start = original_issue_position(
        document, searched_text, issue_text, searched_position, value
    )
    if start is None:
        return None
    positions = source_issue_token_positions(
        str(document), browser_text=getattr(document, "source_kind", "") == "browser-text"
    )
    next_positions = [position for position in positions if position > start]
    end = next_positions[0] if next_positions else len(document)
    if end <= start:
        return None
    return start, end


def _anchor_evidence(
    document: str,
    block_start: int,
    block_end: int,
    anchors: tuple[str, ...],
) -> tuple[str, int]:
    raw_block = source_text_without_hidden_html(
        str(document)[block_start:block_end]
    )
    reverse_brackets = str.maketrans({"[": "【", "]": "】", "(": "（", ")": "）", ":": "："})
    for anchor in anchors:
        variants = (anchor, anchor.translate(reverse_brackets))
        for variant in variants:
            position = raw_block.find(variant)
            if position >= 0:
                return anchor, block_start + position
    return "", -1


def find_matches(
    documents: list[str],
    wanted_issues: set[int],
    site: Site | None = None,
    target: str | None = None,
    *,
    placeholder_issues: set[int] | None = None,
) -> list[Match]:
    if site is not None and site.parser_id in {
        "caiyuntong_macau",
        "guangdong_baer_left_half_head",
        "sewai_taoyuan",
        "shenzhen_futan_half_head",
        "wuzhuanxingyi_embedded",
    }:
        document_special_matches = special_matches_in_documents(documents, wanted_issues, site)
        if target is not None:
            document_special_matches = [
                match for match in document_special_matches if match.value == target
            ]
        return sorted(document_special_matches, key=lambda item: item.order)

    document_special_matches = special_matches_in_documents(documents, wanted_issues, site)
    if document_special_matches:
        if target is not None:
            document_special_matches = [
                match for match in document_special_matches if match.value == target
            ]
        return sorted(document_special_matches, key=lambda item: item.order)

    matches: list[Match] = []
    seen: set[tuple[int, int, str, int]] = set()
    order = 0

    for document_order, document in enumerate(documents):
        for text in iter_search_texts(document):
            normalized_search_text = text if hasattr(text, "source_position") else normalize_text(text)
            for issue, value, snippet, parsed_position in special_matches_in_text(
                text,
                wanted_issues,
                site,
                placeholder_issues=placeholder_issues,
            ):
                if target is not None and value != target:
                    continue
                order += 1
                bounds = _source_block_bounds(
                    document, normalized_search_text, str(issue), parsed_position, value
                )
                if bounds is None:
                    continue
                local_start, local_end = bounds
                offset = int(getattr(document, "position_offset", 0) or 0)
                position = local_start + offset
                block_start = local_start + offset
                block_end = local_end + offset
                anchor_text, anchor_position = _anchor_evidence(
                    document, local_start, local_end, tuple(site.anchors)
                )
                if hasattr(text, "source_header_start"):
                    anchor_text, anchor_position = _anchor_evidence(
                        document, text.source_header_start, text.source_header_end, tuple(site.anchors)
                    )
                if anchor_position >= 0:
                    anchor_position += offset
                key = (document_order, issue, value, position)
                if key in seen:
                    continue
                seen.add(key)
                matches.append(
                    Match(
                        issue,
                        str(issue),
                        value,
                        snippet,
                        order,
                        document_order,
                        position,
                        getattr(document, "source_url", ""),
                        getattr(document, "source_kind", "page"),
                        getattr(document, "record_id", ""),
                        getattr(document, "record_path", ""),
                        getattr(document, "route_type", ""),
                        getattr(document, "url_record_id", ""),
                        getattr(document, "api_url", ""),
                        getattr(document, "title", ""),
                        getattr(document, "author", ""),
                        anchor_text=anchor_text,
                        anchor_position=anchor_position,
                        block_id=f"{document_order}:{block_start}:{block_end}",
                        block_start=block_start,
                        block_end=block_end,
                        container_id=getattr(document, "container_id", ""),
                        table_column=getattr(document, "table_column", ""),
                        document_authority=getattr(document, "document_authority", ""),
                        rule_id="declared_special",
                    )
                )

            for issue, issue_text, segment, parsed_position in iter_issue_segments(text, wanted_issues):
                order += 1
                segment = focused_half_head_block(segment)
                if not strict_segment_has_keyword(segment, DEFAULT_KEYWORDS):
                    continue
                if not segment_has_body_locator(segment):
                    continue
                if {int(token.group(1)) for token in ISSUE_RE.finditer(segment)} != {issue}:
                    continue
                # Preserve all same-record values for the boundary conflict gate.
                values = half_head_values_in_segment(segment)
                if not values:
                    continue
                if target is not None and target not in values:
                    continue
                snippet = compact_line(segment)
                for value in values:
                    bounds = _source_block_bounds(
                        document, normalized_search_text, issue_text, parsed_position, value
                    )
                    if bounds is None:
                        continue
                    local_start, local_end = bounds
                    offset = int(getattr(document, "position_offset", 0) or 0)
                    position = local_start + offset
                    block_start = local_start + offset
                    block_end = local_end + offset
                    anchor_text, anchor_position = _anchor_evidence(
                        document, local_start, local_end, tuple(site.anchors)
                    )
                    if hasattr(text, "source_header_start"):
                        anchor_text, anchor_position = _anchor_evidence(
                            document, text.source_header_start, text.source_header_end, tuple(site.anchors)
                        )
                    if anchor_position >= 0:
                        anchor_position += offset
                    key = (document_order, issue, value, position)
                    if key in seen:
                        continue
                    seen.add(key)
                    matches.append(
                        Match(
                            issue,
                            issue_text,
                            value,
                            snippet,
                            order,
                            document_order,
                            position,
                            getattr(document, "source_url", ""),
                            getattr(document, "source_kind", "page"),
                            getattr(document, "record_id", ""),
                            getattr(document, "record_path", ""),
                            getattr(document, "route_type", ""),
                            getattr(document, "url_record_id", ""),
                            getattr(document, "api_url", ""),
                            getattr(document, "title", ""),
                            getattr(document, "author", ""),
                            anchor_text=anchor_text,
                            anchor_position=anchor_position,
                            block_id=f"{document_order}:{block_start}:{block_end}",
                            block_start=block_start,
                            block_end=block_end,
                            container_id=getattr(document, "container_id", ""),
                            table_column=getattr(document, "table_column", ""),
                            document_authority=getattr(document, "document_authority", ""),
                            rule_id="structural",
                        )
                    )
    return sorted(
        matches,
        key=lambda item: (item.document_order, item.position, item.order, item.snippet),
    )


def site_scoped_raw_matches(
    documents: list[str],
    wanted_issues: set[int],
    site: Site,
    *,
    region_issues: set[int] | None = None,
) -> list[Match]:
    raw_matches = find_matches(
        documents,
        wanted_issues,
        site=site,
        placeholder_issues=(
            region_issues if site.url in SITE_TARGET_PLACEHOLDER_URLS else None
        ),
    )
    return raw_matches


def apply_secondary_site_scope(
    matches: list[Match], site: Site, wanted_issues: set[int]
) -> tuple[list[Match], str | None, tuple[str, ...]]:
    """Apply site-specific checks only after the direction gate has run."""
    scoped = list(matches)
    rejected: list[str] = []

    def retain(predicate, reason: str) -> None:
        nonlocal scoped
        kept: list[Match] = []
        for match in scoped:
            if predicate(match):
                kept.append(match)
                continue
            rejected.append(
                f"{match.issue}期 {match.value}@文档{match.document_order}/位置{match.position}：{reason}"
            )
        scoped = kept

    if site.url in DEDICATED_RENDERED_AUTHOR_CONTEXT_URLS:
        retain(
            lambda match: author_context_matches_site(match.author, site.name),
            "作者不匹配",
        )
    elif site.url in DEDICATED_RENDERED_SITE_RULES:
        expected_identity = DEDICATED_RENDERED_PAGE_IDENTITIES.get(site.url, site.name)
        retain(lambda match: match.title == expected_identity, "页面或区块身份不匹配")
    if (
        site.url in SITE_SPECIAL_VALUE_PATTERNS
        and site.parser_id != "wuzhuanxingyi_embedded"
    ):
        retain(lambda match: match.rule_id == "declared_special", "专属解析规则未命中")
    if site.parser_id not in {
        "caiyuntong_macau",
        "guangdong_baer_left_half_head",
        "shenzhen_futan_half_head",
    }:
        anchors = tuple(site.anchors)
        if anchors:
            annotated: list[Match] = []
            for match in scoped:
                normalized = normalize_text(match.snippet)
                anchor = next((item for item in anchors if item in normalized), "")
                if not anchor:
                    rejected.append(
                        f"{match.issue}期 {match.value}@文档{match.document_order}/位置{match.position}：栏目锚点未命中"
                    )
                    continue
                annotated.append(
                    replace(
                        match,
                        anchor_text=anchor,
                        anchor_position=match.anchor_position,
                    )
                )
            scoped = annotated
    if site.name == "周公神算":
        retain(
            lambda match: "稳杀半头" in match.snippet and "秒杀半头" not in match.snippet,
            "周公神算栏目不匹配",
        )
    elif site.name == "跑狗论坛":
        retain(
            lambda match: "绝杀半头" in match.snippet and "必杀半头" not in match.snippet,
            "跑狗论坛栏目不匹配",
        )
    if site.url in SITE_CURRENT_SERIES_PLACEHOLDER_URLS:
        placeholder_re = re.compile(r"(?:】|\])\s*[?？][?？0０]{1,3}(?![0-9０-９])")
        retain(lambda match: bool(placeholder_re.search(match.snippet)), "当前期占位符未命中")
    normalized_anchors = tuple(
        re.sub(r"\s+", "", normalize_text(anchor))
        for anchor in site.anchors
        if re.sub(r"\s+", "", normalize_text(anchor))
    )
    evidenced: list[Match] = []
    for match in scoped:
        if match.anchor_text:
            evidenced.append(match)
            continue
        compact_snippet = re.sub(r"\s+", "", normalize_text(match.snippet))
        anchor = next(
            (anchor for anchor in normalized_anchors if anchor in compact_snippet),
            "",
        )
        if not anchor and normalized_anchors:
            rejected.append(
                f"{match.issue}期 {match.value}@文档{match.document_order}/位置{match.position}：栏目锚点未命中真实页面内容"
            )
            continue
        evidenced.append(
            replace(
                match,
                anchor_text=anchor,
                anchor_position=match.anchor_position,
                block_id=match.block_id
                or f"{match.container_id or 'document'}:{match.block_start}:{match.block_end}",
            )
        )
    scoped = evidenced
    if not scoped:
        reason = f"{site.pick}方向候选经次级规则校验后无有效结果"
        if rejected:
            reason += "；" + "；".join(rejected)
        return [], reason, tuple(rejected)
    return scoped, None, tuple(rejected)


def apply_direction_source_scope(
    matches: list[Match],
    site: Site,
    documents: list[str] | None = None,
) -> tuple[list[Match], str | None]:
    """Choose exactly one declared authoritative document before direction."""
    is_rendered_container_page = site.url in DEDICATED_RENDERED_SITE_RULES
    if not matches:
        return [], None

    available_orders = sorted({match.document_order for match in matches})
    if is_rendered_container_page:
        if len(available_orders) != 1:
            details = "、".join(str(order) for order in available_orders)
            return [], f"专属权威容器未唯一确定：文档{details}"
        selected_order = available_orders[0]
        return [
            replace(match, document_authority="declared-rendered-container")
            for match in matches
            if match.document_order == selected_order
        ], None

    preferred_kinds: set[str] | None = None
    authority = "primary-page"
    if site.url in SITE_IFRAME_PAGE_AUTHORITY_URLS:
        preferred_kinds = {"iframe", "iframe-decoded"}
        authority = "declared-iframe"
    elif site.parser_id == "wuzhuanxingyi_embedded":
        preferred_kinds = {
            "browser-interactive",
            "script",
            "script-decoded",
            "iframe",
            "iframe-decoded",
        }
        authority = "declared-embedded-parser"
    elif (
        site.url in SITE_BROWSER_HTML_URLS
        or site.url in SITE_RENDERED_PAGE_AUTHORITY_URLS
    ):
        preferred_kinds = {"browser", "browser-text"}
        authority = (
            "declared-rendered-page"
            if site.url in SITE_RENDERED_PAGE_AUTHORITY_URLS
            else "declared-browser"
        )
    elif any(match.source_kind in {"dynamic-record", "dynamic-record-browser"} for match in matches):
        preferred_kinds = {"dynamic-record", "dynamic-record-browser"}
        authority = "exact-dynamic-record"

    if preferred_kinds is not None:
        eligible_orders = sorted(
            {
                match.document_order
                for match in matches
                if match.source_kind in preferred_kinds
            }
        )
    else:
        if documents:
            primary = documents[0]
            primary_url = getattr(primary, "source_url", "")
            primary_kind = getattr(primary, "source_kind", "page")
            eligible_orders = sorted(
                {
                    match.document_order
                    for match in matches
                    if match.document_order < len(documents)
                    and getattr(documents[match.document_order], "source_url", "") == primary_url
                    and getattr(documents[match.document_order], "source_kind", "page") == primary_kind
                    and getattr(documents[match.document_order], "document_authority", "primary")
                    != "attached"
                }
            )
        else:
            eligible_orders = [min(available_orders)]

    if not eligible_orders:
        return [], "主页面无高可信半头候选；附属文档不具备权威资格"
    if len(eligible_orders) > 1:
        first_order = eligible_orders[0]
        if first_order == 0:
            eligible_orders = [first_order]
        else:
            details = "、".join(str(order) for order in eligible_orders)
            return [], f"权威文档未唯一确定：文档{details}"
    selected_order = eligible_orders[0]
    return [
        replace(match, document_authority=authority)
        for match in matches
        if match.document_order == selected_order
    ], None

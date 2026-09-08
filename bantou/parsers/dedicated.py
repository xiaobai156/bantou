# -*- coding: utf-8 -*-
import re
from dataclasses import replace

from ..domain.models import Match, Site
from ..site_profiles.registry import (
    CAIYUNTONG_URL,
    GUANGDONG_BAER_URL,
    SEWAI_TAOYUAN_URL,
    SHENZHEN_FUTAN_URL,
    WUZHUANXINGYI_CARD_LABELS,
    WUZHUANXINGYI_URL,
)
from ..text import (
    ISSUE_RE,
    TABLE_CELL_RE,
    TABLE_ROW_RE,
    VALUE_RE,
    compact_line,
    html_to_text,
    issue_token_positions,
    normalize_half_head_value,
    normalize_text,
)

SEWAI_TAOYUAN_ROW_RE = re.compile(
    r"(?:【|\[)\s*(?P<head>[0-4０-４])\s*头\s*"
    r"(?P<parity>单|双)\s*(?:】|\])\s*"
    r"(?P<issue>[0-9０-９]{1,4})\s*期\s*[:：]?\s*"
    r"(?:🌹\s*)?绝杀半头(?:\s*🌹)?[^\n]*",
    re.I,
)
WUZHUANXINGYI_CARD_RE = re.compile(
    r'<div\b[^>]*class=["\'][^"\']*\btitle_container\b[^"\']*["\'][^>]*>'
    r"(?P<header>.*?)"
    r'<div\b[^>]*class=["\'][^"\']*\btextriow\b[^"\']*["\'][^>]*>'
    r"(?P<body>.*?)(?:</div>|$)",
    re.I | re.S,
)
WUZHUANXINGYI_ROW_RE = re.compile(
    r"(?<!\d)(?P<issue>\d{1,4})\s*期\s*[:：]?\s*"
    r"(?:【|\[)\s*绝杀半头\s*(?:】|\])\s*"
    r"(?:【|\[)\s*(?P<head>[0-4])\s*头\s*(?P<parity>单|双)\s*(?:】|\])\s*"
    r"开[^\n]*",
    re.I,
)
SHENZHEN_FUTAN_TITLE = "深圳福坛【绝杀半头】"
SHENZHEN_FUTAN_TITLE_RE = re.compile(
    r'<div\b[^>]*class=["\'][^"\']*\bpb-tit\b[^"\']*["\'][^>]*>'
    r"(?P<title>.*?)</div\s*>",
    re.I | re.S,
)
HTML_TABLE_RE = re.compile(r"<table\b[^>]*>.*?</table\s*>", re.I | re.S)


def _html_issue_positions(text: str, issue_text: str) -> list[int]:
    digits = "".join(
        f"[{digit}{digit.translate(str.maketrans('0123456789', '０１２３４５６７８９'))}]"
        for digit in str(issue_text)
    )
    pattern = re.compile(
        rf"(?<![0-9０-９]){digits}(?:\s|&nbsp;|&#160;|<[^>]*>)*期"
    )
    return [match.start() for match in pattern.finditer(text)]


def wuzhuanxingyi_matches(
    documents: list[str],
    wanted_issues: set[int],
) -> list[Match]:
    matches: list[Match] = []
    allowed_source_kinds = {
        "page",
        "browser",
        "browser-text",
        "browser-interactive",
        "script",
        "script-decoded",
        "iframe",
        "iframe-decoded",
    }
    for document_order, document in enumerate(documents):
        if getattr(document, "source_kind", "page") not in allowed_source_kinds:
            continue
        text = str(document)
        for card_match in WUZHUANXINGYI_CARD_RE.finditer(text):
            header_text = normalize_text(html_to_text(card_match.group("header")))
            header_compact = re.sub(r"\s+", "", header_text)
            if "绝杀半头" not in header_compact:
                continue
            if not any(label in header_compact for label in WUZHUANXINGYI_CARD_LABELS):
                continue
            body_html = card_match.group("body")
            body_text = normalize_text(html_to_text(body_html))
            row_matches = list(WUZHUANXINGYI_ROW_RE.finditer(body_text))
            row_occurrences: dict[int, int] = {}
            seen_rows: set[tuple[int, str, str]] = set()
            for row_match in row_matches:
                issue = int(row_match.group("issue"))
                if issue not in wanted_issues:
                    continue
                value = normalize_half_head_value(
                    row_match.group("head"), row_match.group("parity")
                )
                if value is None:
                    continue
                raw_positions = _html_issue_positions(body_html, row_match.group("issue"))
                occurrence = row_occurrences.get(issue, 0)
                row_occurrences[issue] = occurrence + 1
                if occurrence >= len(raw_positions):
                    continue
                row_key = (issue, value, compact_line(row_match.group(0)))
                if row_key in seen_rows:
                    continue
                seen_rows.add(row_key)
                offset = int(getattr(document, "position_offset", 0) or 0)
                body_start = card_match.start("body")
                block_start = card_match.start() + offset
                block_end = card_match.end() + offset
                position = body_start + raw_positions[occurrence] + offset
                anchor_local = body_html.find("绝杀半头")
                if anchor_local < 0:
                    continue
                matches.append(
                    Match(
                        issue,
                        row_match.group("issue"),
                        value,
                        compact_line(row_match.group(0)),
                        len(matches) + 1,
                        document_order=document_order,
                        position=position,
                        source_url=getattr(document, "source_url", ""),
                        source_kind=getattr(document, "source_kind", "page"),
                        record_id=getattr(document, "record_id", ""),
                        record_path=getattr(document, "record_path", ""),
                        route_type=getattr(document, "route_type", ""),
                        url_record_id=getattr(document, "url_record_id", ""),
                        api_url=getattr(document, "api_url", ""),
                        title=getattr(document, "title", ""),
                        author=getattr(document, "author", ""),
                        anchor_text="半头",
                        anchor_position=body_start + anchor_local + offset,
                        block_id=f"wuzhuanxingyi:{block_start}:{block_end}",
                        block_start=block_start,
                        block_end=block_end,
                        container_id=(
                            getattr(document, "container_id", "")
                            or f"wuzhuanxingyi:{document_order}:{card_match.start()}"
                        ),
                        document_authority=getattr(document, "document_authority", ""),
                        rule_id="wuzhuanxingyi_embedded",
                    )
                )
    return matches


def sewai_taoyuan_matches(
    documents: list[str],
    wanted_issues: set[int],
) -> list[Match]:
    matches: list[Match] = []
    for document_order, document in enumerate(documents):
        text = str(document)
        if "世外桃源" not in text or "绝杀半头" not in text:
            continue
        row_matches = list(SEWAI_TAOYUAN_ROW_RE.finditer(text))
        for row_index, row_match in enumerate(row_matches):
            issue = int(normalize_text(row_match.group("issue")))
            if issue not in wanted_issues:
                continue
            value = normalize_half_head_value(
                normalize_text(row_match.group("head")),
                row_match.group("parity"),
            )
            if value is None:
                continue
            positions = [
                position
                for position in issue_token_positions(text, row_match.group("issue"))
                if row_match.start() <= position < row_match.end()
            ]
            if len(positions) != 1:
                continue
            offset = int(getattr(document, "position_offset", 0) or 0)
            row_start = row_match.start() + offset
            row_end = (
                row_matches[row_index + 1].start() + offset
                if row_index + 1 < len(row_matches)
                else len(text) + offset
            )
            anchor_position = text.find("世外桃源") + offset
            half_head_position = text.find("半头", row_match.start(), row_match.end())
            if anchor_position < offset or half_head_position < 0:
                continue
            matches.append(
                Match(
                    issue,
                    row_match.group("issue"),
                    value,
                    compact_line(row_match.group(0)),
                    len(matches) + 1,
                    document_order=document_order,
                    position=positions[0] + offset,
                    source_url=getattr(document, "source_url", ""),
                    source_kind=getattr(document, "source_kind", "page"),
                    record_id=getattr(document, "record_id", ""),
                    record_path=getattr(document, "record_path", ""),
                    route_type=getattr(document, "route_type", ""),
                    url_record_id=getattr(document, "url_record_id", ""),
                    api_url=getattr(document, "api_url", ""),
                    title=getattr(document, "title", ""),
                    author=getattr(document, "author", ""),
                    anchor_text="半头",
                    anchor_position=half_head_position + offset,
                    block_id=f"sewai:{row_start}:{row_end}",
                    block_start=row_start,
                    block_end=row_end,
                    container_id=(
                        getattr(document, "container_id", "")
                        or f"sewai-taoyuan:{document_order}"
                    ),
                    document_authority=getattr(document, "document_authority", ""),
                    rule_id="sewai_taoyuan",
                )
            )
    return matches


def caiyuntong_macau_matches(
    documents: list[str],
    wanted_issues: set[int],
) -> list[Match]:
    matches: list[Match] = []
    for document_order, document in enumerate(documents):
        local_matches = caiyuntong_macau_matches_from_joined(document, wanted_issues)
        for local_match in local_matches:
            offset = int(getattr(document, "position_offset", 0) or 0)
            matches.append(
                replace(
                    local_match,
                    order=len(matches) + 1,
                    document_order=document_order,
                    position=local_match.position + offset,
                    source_url=getattr(document, "source_url", ""),
                    source_kind=getattr(document, "source_kind", "page"),
                    record_id=getattr(document, "record_id", ""),
                    record_path=getattr(document, "record_path", ""),
                    route_type=getattr(document, "route_type", ""),
                    url_record_id=getattr(document, "url_record_id", ""),
                    api_url=getattr(document, "api_url", ""),
                    title=getattr(document, "title", ""),
                    author=getattr(document, "author", ""),
                    anchor_position=local_match.anchor_position + offset,
                    block_id=f"{document_order}:{local_match.block_id}",
                    block_start=local_match.block_start + offset,
                    block_end=local_match.block_end + offset,
                    container_id=(
                        getattr(document, "container_id", "")
                        or f"caiyuntong:{document_order}"
                    ),
                    document_authority=getattr(document, "document_authority", ""),
                )
            )
    return matches


def caiyuntong_macau_matches_from_joined(
    joined: str,
    wanted_issues: set[int],
) -> list[Match]:
    starts = [
        match.start()
        for match in re.finditer(r"id=[\"']con_jihuadanshuang50000aloa_1[\"']", joined)
    ]
    blocks: list[tuple[int, int, int, str]] = []
    for start in starts:
        prefix_start = max(0, start - 2500)
        prefix = joined[prefix_start:start]
        if "彩运通" not in prefix or "澳门综合杀" not in prefix:
            continue
        anchor_position = joined.rfind("澳门综合杀", prefix_start, start)
        if anchor_position < 0:
            continue
        end_match = re.search(r"id=[\"']con_jihuadanshuang50000aloa_2[\"']", joined[start:])
        if end_match is None:
            continue
        end = start + end_match.start()
        candidate = joined[start:end]
        if any(f"{issue}期" in candidate for issue in wanted_issues):
            blocks.append((anchor_position, start, end, candidate))
    if not blocks:
        return []

    matches: list[Match] = []
    order = 0
    for anchor_position, table_start, block_end, macau_block in blocks:
        for row_match in TABLE_ROW_RE.finditer(macau_block):
            cells = [
                normalize_text(html_to_text(cell))
                for cell in TABLE_CELL_RE.findall(row_match.group(1))
            ]
            if len(cells) < 4:
                continue
            issue_match = ISSUE_RE.search(cells[0])
            if not issue_match:
                continue
            issue = int(issue_match.group(1))
            if issue not in wanted_issues:
                continue
            value_match = VALUE_RE.search(cells[3])
            if not value_match:
                continue
            value = normalize_half_head_value(value_match.group(1), value_match.group(2))
            if value is None:
                continue
            row_start = table_start + row_match.start()
            row_end = table_start + row_match.end()
            positions = [
                position
                for position in issue_token_positions(joined, issue_match.group(1))
                if row_start <= position < row_end
            ]
            if len(positions) != 1:
                continue
            position = positions[0]
            order += 1
            snippet = compact_line(" ".join(cells))
            matches.append(
                Match(
                    issue,
                    issue_match.group(1),
                    value,
                    snippet,
                    order,
                    position=position,
                    anchor_text="澳门综合杀",
                    anchor_position=anchor_position,
                    block_id=f"macau:{anchor_position}:{block_end}:{row_start}:{row_end}",
                    block_start=anchor_position,
                    block_end=block_end,
                    table_column="macau-half-head",
                    rule_id="caiyuntong_macau",
                )
            )
    return matches


def guangdong_baer_left_half_head_matches(
    documents: list[str],
    wanted_issues: set[int],
) -> list[Match]:
    matches: list[Match] = []
    for document_order, document in enumerate(documents):
        local_matches = guangdong_baer_left_half_head_matches_from_joined(
            document, wanted_issues
        )
        for local_match in local_matches:
            offset = int(getattr(document, "position_offset", 0) or 0)
            matches.append(
                replace(
                    local_match,
                    order=len(matches) + 1,
                    document_order=document_order,
                    position=local_match.position + offset,
                    source_url=getattr(document, "source_url", ""),
                    source_kind=getattr(document, "source_kind", "page"),
                    record_id=getattr(document, "record_id", ""),
                    record_path=getattr(document, "record_path", ""),
                    route_type=getattr(document, "route_type", ""),
                    url_record_id=getattr(document, "url_record_id", ""),
                    api_url=getattr(document, "api_url", ""),
                    title=getattr(document, "title", ""),
                    author=getattr(document, "author", ""),
                    anchor_position=local_match.anchor_position + offset,
                    block_id=f"{document_order}:{local_match.block_id}",
                    block_start=local_match.block_start + offset,
                    block_end=local_match.block_end + offset,
                    container_id=(
                        getattr(document, "container_id", "")
                        or f"guangdong:{document_order}"
                    ),
                    document_authority=getattr(document, "document_authority", ""),
                )
            )
    return matches


def guangdong_baer_left_half_head_matches_from_joined(
    joined: str,
    wanted_issues: set[int],
) -> list[Match]:
    found: list[Match] = []
    order = 0
    title_positions = [match.start() for match in re.finditer("『半波半头』", joined)]
    pattern = re.compile(
        r"(?<!\d)(\d{1,4})期\s*杀\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*"
        r"(?:】|\])[\s\S]{0,20}?开[^\n]{0,12}",
        re.I,
    )
    for title_pos in title_positions:
        title_end = title_pos + len("『半波半头』")
        next_title = re.search("『", joined[title_end:])
        section_end = title_end + next_title.start() if next_title else min(len(joined), title_pos + 20000)
        section = joined[title_pos:section_end]
        table_match = re.search(
            r"<div\b[^>]*class=[\"'][^\"']*dz_content08[^\"']*[\"'][^>]*>",
            section,
            re.I,
        )
        if not table_match:
            continue
        table_section = section[table_match.end() :]
        first_row = TABLE_ROW_RE.search(table_section)
        if not first_row or len(TABLE_CELL_RE.findall(first_row.group(1))) < 2:
            continue
        first_td = re.search(r"<td\b[^>]*>", table_section, re.I)
        if not first_td:
            continue
        left_start = first_td.end()
        left_end_match = re.search(r"</td\s*>", table_section[left_start:], re.I)
        if not left_end_match:
            continue
        left_end = left_start + left_end_match.start()
        left_text = normalize_text(html_to_text(table_section[left_start:left_end]))
        for match in pattern.finditer(left_text):
            issue = int(match.group(1))
            if issue not in wanted_issues:
                continue
            value = normalize_half_head_value(match.group(2), match.group(3))
            if value is None:
                continue
            global_left_start = title_pos + table_match.end() + left_start
            global_left_end = title_pos + table_match.end() + left_end
            anchor_position = joined.find("半波半头", title_pos, title_end)
            if anchor_position < 0:
                continue
            positions = [
                position
                for position in issue_token_positions(joined, match.group(1))
                if global_left_start <= position < global_left_end
            ]
            if len(positions) != 1:
                continue
            position = positions[0]
            order += 1
            found.append(
                Match(
                    issue,
                    match.group(1),
                    value,
                    compact_line(match.group(0)),
                    order,
                    position=position,
                    anchor_text="半波半头",
                    anchor_position=anchor_position,
                    block_id=f"guangdong-section:{title_pos}:{section_end}:{global_left_start}:{global_left_end}",
                    block_start=title_pos,
                    block_end=section_end,
                    table_column="left:0",
                    rule_id="guangdong_baer_left_half_head",
                )
            )
    return found


def shenzhen_futan_matches(
    documents: list[str],
    wanted_issues: set[int],
) -> list[Match]:
    matches: list[Match] = []
    for document_order, document in enumerate(documents):
        text = str(document)
        target_titles = [
            title_match
            for title_match in SHENZHEN_FUTAN_TITLE_RE.finditer(text)
            if re.sub(r"\s+", "", normalize_text(html_to_text(title_match.group("title"))))
            == normalize_text(SHENZHEN_FUTAN_TITLE)
        ]
        target_tables: list[tuple[re.Match[str], re.Match[str]]] = []
        for title_match in target_titles:
            next_title = SHENZHEN_FUTAN_TITLE_RE.search(text, title_match.end())
            section_end = next_title.start() if next_title is not None else len(text)
            section_tables = list(
                HTML_TABLE_RE.finditer(text, title_match.end(), section_end)
            )
            if len(section_tables) != 1:
                continue
            target_tables.append((title_match, section_tables[0]))
        if len(target_tables) != 1:
            continue

        title_match, table_match = target_tables[0]
        block_start = title_match.start()
        block_end = table_match.end()
        offset = int(getattr(document, "position_offset", 0) or 0)
        block_id = f"shenzhen-futan:{block_start + offset}:{block_end + offset}"
        row_order = 0
        for row_match in TABLE_ROW_RE.finditer(table_match.group(0)):
            row_html = row_match.group(0)
            row_text = normalize_text(html_to_text(row_html))
            issue_matches = list(ISSUE_RE.finditer(row_text))
            value_matches = list(VALUE_RE.finditer(row_text))
            if len(issue_matches) != 1 or len(value_matches) != 1:
                continue
            if "绝杀半头" not in re.sub(r"\s+", "", row_text):
                continue
            issue_match = issue_matches[0]
            issue = int(issue_match.group(1))
            value_match = value_matches[0]
            value = normalize_half_head_value(
                value_match.group(1), value_match.group(2)
            )
            if value is None:
                continue
            row_start = table_match.start() + row_match.start()
            row_end = table_match.start() + row_match.end()
            positions = [
                position
                for position in issue_token_positions(text, issue_match.group(1))
                if row_start <= position < row_end
            ]
            if len(positions) != 1:
                continue
            row_order += 1
            if issue not in wanted_issues:
                continue
            matches.append(
                Match(
                    issue=issue,
                    issue_text=issue_match.group(1),
                    value=value,
                    snippet=compact_line(row_text),
                    order=row_order,
                    document_order=document_order,
                    position=positions[0] + offset,
                    source_url=getattr(document, "source_url", ""),
                    source_kind=getattr(document, "source_kind", "page"),
                    record_id=getattr(document, "record_id", ""),
                    record_path=getattr(document, "record_path", ""),
                    route_type=getattr(document, "route_type", ""),
                    url_record_id=getattr(document, "url_record_id", ""),
                    api_url=getattr(document, "api_url", ""),
                    title=getattr(document, "title", ""),
                    author=getattr(document, "author", ""),
                    anchor_text=SHENZHEN_FUTAN_TITLE,
                    anchor_position=title_match.start("title") + offset,
                    block_id=block_id,
                    block_start=block_start + offset,
                    block_end=block_end + offset,
                    container_id=(
                        getattr(document, "container_id", "")
                        or f"shenzhen-futan:{document_order}"
                    ),
                    table_column="target-table:0",
                    document_authority=getattr(document, "document_authority", ""),
                    rule_id="shenzhen_futan_half_head",
                )
            )
    return matches


def special_matches_in_documents(
    documents: list[str],
    wanted_issues: set[int],
    site: Site | None,
) -> list[Match]:
    if site is None:
        return []
    if site.url == CAIYUNTONG_URL:
        return caiyuntong_macau_matches(documents, wanted_issues)
    if site.url == GUANGDONG_BAER_URL:
        return guangdong_baer_left_half_head_matches(documents, wanted_issues)
    if site.url == SEWAI_TAOYUAN_URL:
        return sewai_taoyuan_matches(documents, wanted_issues)
    if site.url == WUZHUANXINGYI_URL:
        return wuzhuanxingyi_matches(documents, wanted_issues)
    if (
        site.url == SHENZHEN_FUTAN_URL
        and site.parser_id == "shenzhen_futan_half_head"
    ):
        return shenzhen_futan_matches(documents, wanted_issues)
    return []



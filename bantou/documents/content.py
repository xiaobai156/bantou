# -*- coding: utf-8 -*-
import base64
import binascii
import re
from urllib.parse import urlparse

from ..domain.models import Site, SourceDocument
from ..site_profiles.registry import (
    DEDICATED_RENDERED_ALTERNATE_DATA_ANCHORS,
    DEDICATED_RENDERED_AUTHOR_CONTEXT_URLS,
    DEDICATED_RENDERED_CURRENT_SERIES_URLS,
    DEDICATED_RENDERED_PAGE_IDENTITIES,
    DEDICATED_RENDERED_SITE_RULES,
    HALF_HEAD_KEYWORD_RE,
    STRDECODE_RE,
)
from ..text import (
    ISSUE_RE,
    VALUE_RE,
    RenderedContainerParser,
    extract_half_head_table_texts,
    html_to_text,
    normalize_text,
)


def decode_strdecode_blocks_with_positions(text: str) -> list[tuple[str, int]]:
    decoded: list[tuple[str, int]] = []
    for match in STRDECODE_RE.finditer(text):
        payload = match.group(2)
        try:
            padded = payload + ("=" * (-len(payload) % 4))
            raw = base64.b64decode(padded)
        except (binascii.Error, ValueError):
            continue
        for encoding in ("utf-8", "gb18030", "big5"):
            try:
                decoded.append((raw.decode(encoding), match.start()))
                break
            except UnicodeDecodeError:
                continue
    return decoded


def add_document_with_decoded(
    text: str,
    documents: list[SourceDocument],
    seen: set[tuple[str, str, str, int]],
    *,
    source_url: str,
    source_kind: str,
) -> None:
    queue = [(text, 0, 0)]
    index = 0
    while index < len(queue):
        current, depth, absolute_position = queue[index]
        index += 1
        effective_kind = source_kind if depth == 0 else f"{source_kind}-decoded"
        key = (source_url, effective_kind, current, absolute_position)
        if not current or key in seen:
            continue
        seen.add(key)
        authority = "primary" if source_kind == "page" and depth == 0 else "attached"
        documents.append(
            SourceDocument(
                current,
                source_url=source_url,
                source_kind=effective_kind,
                position_offset=absolute_position,
                container_id=f"{source_kind}:{source_url}:decoded:{depth}:{absolute_position}",
                document_authority=authority,
                block_start=absolute_position,
                block_end=absolute_position + len(current),
            )
        )
        if depth < 6:
            decoded_blocks = decode_strdecode_blocks_with_positions(current)
            queue.extend(
                (decoded, depth + 1, absolute_position + position)
                for decoded, position in decoded_blocks
            )


def should_fetch_script(script_url: str) -> bool:
    path = urlparse(script_url).path.lower()
    return (
        "/upload/script/" in path
        or path.endswith("/script.js")
        or (path.startswith("/htm/bbs/") and path.endswith(".js"))
    )


def should_fetch_iframe(frame_url: str) -> bool:
    path = urlparse(frame_url).path.lower()
    return path.startswith(("/main/bbs/", "/htm/bbs/"))


def should_fetch_half_head_link(link_url: str) -> bool:
    path = urlparse(link_url).path.lower()
    return (
        "/topic/" in path
        or "/bbs/read.php" in path
        or "/gengxin/" in path
        or "/gsb/" in path
        or "/6dgsb/" in path
        or "/tie" in path
    )


def rendered_container_has_half_head(
    text: str,
    wanted_issues: set[int] | None,
    alternate_data_anchors: tuple[str, ...] = (),
) -> bool:
    normalized = normalize_text(text)
    has_half_head_keyword = (
        bool(HALF_HEAD_KEYWORD_RE.search(normalized))
        or "半波半头" in normalized
        or any(anchor in normalized for anchor in alternate_data_anchors)
    )
    issues = wanted_issues or {int(match.group(1)) for match in ISSUE_RE.finditer(normalized)}
    for issue in issues:
        if (
            re.search(rf"(?<!\d){issue}\s*期", normalized)
            and has_half_head_keyword
            and VALUE_RE.search(normalized)
        ):
            return True
    return False


def bound_dedicated_rendered_container(text: str, class_name: str) -> str:
    normalized = normalize_text(text)
    if class_name not in {"topic-content", "detail_info_forum2_item"}:
        return normalized

    issue_matches = list(ISSUE_RE.finditer(normalized))
    issue_numbers = [int(match.group(1)) for match in issue_matches]
    if class_name == "topic-content" and len(issue_numbers) >= 3:
        if issue_numbers[1] > issue_numbers[0]:
            direction = 1
        elif issue_numbers[1] < issue_numbers[0]:
            direction = -1
        else:
            direction = 0
        if direction:
            for index in range(2, len(issue_numbers)):
                moved_back = direction > 0 and issue_numbers[index] <= issue_numbers[index - 1]
                moved_forward = direction < 0 and issue_numbers[index] >= issue_numbers[index - 1]
                if moved_back or moved_forward:
                    return normalize_text(normalized[: issue_matches[index].start()])

    first_issue = ISSUE_RE.search(normalized)
    if first_issue is None:
        return normalized
    issue = int(first_issue.group(1))
    positions = [match.start() for match in re.finditer(rf"(?<!\d){issue}\s*期", normalized)]
    keep_count = 1 if class_name == "topic-content" else 2
    if len(positions) > keep_count:
        return normalize_text(normalized[: positions[keep_count]])
    return normalized


CURRENT_SERIES_PLACEHOLDER_RE = re.compile(
    r"开\s*[:：]?\s*(?:[?？0０]{2,4})(?![0-9０-９])"
)


def bound_current_rendered_series(
    text: str, wanted_issues: set[int] | None
) -> tuple[str, int]:
    """Keep one current sequence anchored by its unique next-issue placeholder."""
    if not wanted_issues:
        raise ValueError("当前期段锚点需要指定期数")

    normalized = normalize_text(text)
    issue_matches = list(ISSUE_RE.finditer(normalized))
    records: list[tuple[int, int, int, str]] = []
    for index, match in enumerate(issue_matches):
        end = issue_matches[index + 1].start() if index + 1 < len(issue_matches) else len(normalized)
        records.append((int(match.group(1)), match.start(), end, normalized[match.start() : end]))

    target_issue = max(wanted_issues)
    target_placeholder_indexes = [
        index
        for index, (issue, _start, _end, segment) in enumerate(records)
        if issue == target_issue and CURRENT_SERIES_PLACEHOLDER_RE.search(segment)
    ]
    if target_placeholder_indexes:
        if len(target_placeholder_indexes) != 1:
            raise ValueError(
                f"当前期段锚点未唯一匹配：候选数={len(target_placeholder_indexes)}"
            )
        anchor = target_placeholder_indexes[0]
        first = anchor
        while first > 0 and records[first - 1][0] == records[first][0] - 1:
            first -= 1
        series_issues = {record[0] for record in records[first : anchor + 1]}
        if wanted_issues <= series_issues:
            return normalized[records[first][1] : records[anchor][2]], records[first][1]

    next_issue = target_issue + 1
    candidates: list[tuple[int, int]] = []
    for index, (issue, _start, _end, segment) in enumerate(records):
        if issue != next_issue or not CURRENT_SERIES_PLACEHOLDER_RE.search(segment):
            continue

        if index > 0 and records[index - 1][0] == issue - 1:
            first = index
            while first > 0 and records[first - 1][0] == records[first][0] - 1:
                first -= 1
            last = index
        elif index + 1 < len(records) and records[index + 1][0] == issue - 1:
            first = index
            last = index
            while last + 1 < len(records) and records[last + 1][0] == records[last][0] - 1:
                last += 1
        else:
            continue

        series_issues = {record[0] for record in records[first : last + 1]}
        if wanted_issues <= series_issues:
            candidates.append((records[first][1], records[last][2]))

    target_indexes = [
        index for index, (issue, _start, _end, _segment) in enumerate(records)
        if issue == target_issue
    ]
    if not candidates and target_indexes and target_indexes[0] == 0:
        last = 0
        while last + 1 < len(records) and records[last + 1][0] == records[last][0] - 1:
            last += 1
        series_issues = {record[0] for record in records[: last + 1]}
        if wanted_issues <= series_issues:
            candidates.append((records[0][1], records[last][2]))

    if len(candidates) != 1:
        raise ValueError(f"当前期段锚点未唯一匹配：候选数={len(candidates)}")
    start, end = candidates[0]
    return normalized[start:end], start


def author_context_matches_site(author_context: str, site_name: str) -> bool:
    """Match one rendered author label exactly, never a body-text mention."""
    compact_author = re.sub(r"\s+", "", normalize_text(author_context))
    if not compact_author:
        return False
    escaped_name = re.escape(site_name)
    return bool(
        re.fullmatch(rf"(?:作者[:：])?{escaped_name}(?:发表于.*)?", compact_author)
    )


def extract_dedicated_rendered_documents(
    rendered_html: str,
    site: Site,
    wanted_issues: set[int] | None,
    *,
    direction_first: bool = False,
) -> list[SourceDocument]:
    parser = RenderedContainerParser()
    parser.feed(rendered_html)
    preferred = DEDICATED_RENDERED_SITE_RULES.get(site.url)
    if not preferred:
        raise ValueError(f"专属渲染站未声明唯一容器：{site.url}")

    raw_page_text = parser.page_text()
    root_text = normalize_text(raw_page_text)
    page_identity = DEDICATED_RENDERED_PAGE_IDENTITIES.get(site.url, "")
    alternate_data_anchors = DEDICATED_RENDERED_ALTERNATE_DATA_ANCHORS.get(site.url, ())
    blocks: list[tuple[str, int, int, str, str]] = []
    if preferred == "page":
        if not direction_first and (not page_identity or page_identity not in root_text):
            raise ValueError(f"专属页面身份未匹配：{page_identity or site.url}")
        source_blocks = [(raw_page_text, "", 0, len(raw_page_text))]
    else:
        author_contexts = parser.block_author_contexts.get(preferred, [])
        raw_blocks = parser.blocks.get(preferred, [])
        block_spans = parser.block_spans.get(preferred, [])
        if len(raw_blocks) != len(block_spans):
            raise ValueError(f"专属容器位置证据不完整：class={preferred}")
        source_blocks = [
            (
                block,
                normalize_text(author_contexts[index] if index < len(author_contexts) else ""),
                block_spans[index][0],
                block_spans[index][1],
            )
            for index, block in enumerate(raw_blocks)
        ]
    for raw_source_block, author_context, page_start, page_end in source_blocks:
        raw_block = raw_source_block
        body_text = normalize_text(raw_source_block)
        requires_author_context = site.url in DEDICATED_RENDERED_AUTHOR_CONTEXT_URLS
        author_matches = author_context_matches_site(author_context, site.name)
        page_matches = bool(page_identity and page_identity in root_text)
        if not direction_first and requires_author_context and not author_matches:
            continue
        if not direction_first and not requires_author_context and site.name not in body_text and not page_matches:
            continue
        if direction_first:
            normalized_block = raw_block
            position_offset = 0
        elif site.url in DEDICATED_RENDERED_CURRENT_SERIES_URLS:
            normalized_block, position_offset = bound_current_rendered_series(
                raw_block, wanted_issues
            )
        else:
            normalized_block = bound_dedicated_rendered_container(raw_block, preferred)
            position_offset = 0
        compact = re.sub(r"\s+", "", normalize_text(normalized_block))
        if not direction_first and site.anchors and not any(anchor in compact for anchor in site.anchors):
            continue
        if rendered_container_has_half_head(
            normalized_block,
            None if direction_first else wanted_issues,
            alternate_data_anchors,
        ):
            identity = site.name if site.name in body_text else page_identity if page_matches else ""
            blocks.append(
                (
                    normalized_block,
                    page_start + position_offset,
                    page_end if direction_first else page_start + position_offset + len(normalized_block),
                    author_context,
                    identity,
                )
            )
    if not direction_first and len(blocks) != 1:
        raise ValueError(
            f"专属解析容器未唯一匹配：class={preferred}，候选数={len(blocks)}"
        )
    if direction_first and not blocks:
        raise ValueError(f"专属方向候选容器为空：class={preferred}")
    documents: list[SourceDocument] = []
    for index, (block, block_page_offset, block_page_end, author_context, identity) in enumerate(blocks):
        documents.append(
            SourceDocument(
                block,
                source_url=site.url,
                source_kind="browser-text" if preferred == "page" else "browser",
                title=identity,
                author=author_context,
                position_offset=block_page_offset,
                container_id=f"{preferred}:{index}:{block_page_offset}:{block_page_end}",
                document_authority="declared-rendered-container",
                block_start=block_page_offset,
                block_end=block_page_end,
            )
        )
    return documents

def iter_search_texts(document: str):
    if getattr(document, "source_kind", "") == "browser-text":
        yield normalize_text(document)
        return
    looks_like_html = "<" in document and ">" in document
    text = html_to_text(document)
    if text:
        yield text
    if looks_like_html:
        yield from extract_half_head_table_texts(document)
    if not looks_like_html:
        yield normalize_text(document)

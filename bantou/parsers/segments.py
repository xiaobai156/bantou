# -*- coding: utf-8 -*-
import re

from ..documents.content import iter_search_texts
from ..site_profiles.registry import (
    DEFAULT_KEYWORDS,
    HALF_HEAD_KEYWORD_RE,
    NON_HALF_HEAD_COLUMN_RE,
    OPEN_INFO_RE,
    STRICT_HALF_HEAD_RE,
)
from ..text import (
    ISSUE_RE,
    VALUE_RE,
    compact_line,
    normalize_text,
)


def values_in_segment(segment: str) -> list[str]:
    values: list[str] = []
    for match in VALUE_RE.finditer(normalize_text(segment)):
        value = f"{int(match.group(1))}头{match.group(2)}"
        if value not in values:
            values.append(value)
    return values


def strict_segment_has_keyword(segment: str, keywords: tuple[str, ...]) -> bool:
    compact = re.sub(r"\s+", "", normalize_text(segment))
    if HALF_HEAD_KEYWORD_RE.search(compact) or "半头" in compact:
        return True
    return any(keyword in compact for keyword in keywords)


def contains_non_half_head_column(segment: str) -> bool:
    compact = re.sub(r"\s+", "", normalize_text(segment))
    if not compact:
        return False
    # 真正写着“半头”的候选块优先保留；其它栏目词只用于拦截无半头栏目的误抓。
    if HALF_HEAD_KEYWORD_RE.search(compact) or "半头" in compact:
        return False
    return bool(NON_HALF_HEAD_COLUMN_RE.search(compact))


def segment_has_body_locator(segment: str) -> bool:
    normalized = normalize_text(segment)
    compact = re.sub(r"\s+", "", normalized)
    if OPEN_INFO_RE.search(normalized):
        return True
    return any(marker in compact for marker in ("对", "错", "准", "中", "赢", "√", "×"))


def focused_half_head_block(segment: str) -> str:
    normalized = normalize_text(segment)
    keyword_match = HALF_HEAD_KEYWORD_RE.search(re.sub(r"\s+", "", normalized))
    if not keyword_match:
        return normalized

    raw_keyword_match = re.search(r"(?:秒杀|必杀|绝杀|稳杀|杀)[\s\S]{0,12}?半头", normalized, re.I)
    if not raw_keyword_match:
        return normalized

    issue_matches = [match for match in ISSUE_RE.finditer(normalized) if match.start() <= raw_keyword_match.start()]
    start = issue_matches[-1].start() if issue_matches else max(0, raw_keyword_match.start() - 20)
    next_issue = ISSUE_RE.search(normalized, raw_keyword_match.end())
    end = next_issue.start() if next_issue else len(normalized)
    return normalized[start:end]


def segment_quantity_valid(segment: str, issue: int | None = None, expected_value: str | None = None) -> bool:
    normalized = normalize_text(segment)
    issues = {int(match.group(1)) for match in ISSUE_RE.finditer(normalized)}
    if issue is not None:
        if issues != {issue}:
            return False
    elif len(issues) != 1:
        return False

    values = {
        f"{int(match.group(1))}头{match.group(2)}"
        for match in VALUE_RE.finditer(normalized)
    }
    return len(values) == 1


def strict_values_in_segment(segment: str) -> list[str]:
    normalized = normalize_text(segment)
    if contains_non_half_head_column(normalized):
        return []
    if not segment_has_body_locator(normalized):
        return []
    values: list[str] = []

    for match in STRICT_HALF_HEAD_RE.finditer(normalized):
        value = f"{int(match.group(1))}头{match.group(2)}"
        if value not in values:
            values.append(value)
    if values:
        return values

    compact = re.sub(r"\s+", "", normalized)
    generic_values: list[str] = []
    for match in VALUE_RE.finditer(normalized):
        value = f"{int(match.group(1))}头{match.group(2)}"
        if value not in generic_values:
            generic_values.append(value)

    if HALF_HEAD_KEYWORD_RE.search(compact) or any(keyword in compact for keyword in DEFAULT_KEYWORDS):
        if len(generic_values) == 1:
            return generic_values
        return []

    return generic_values

def iter_issue_segments(text: str, wanted_issues: set[int]):
    normalized = normalize_text(text)
    lines = []
    for line_match in re.finditer(r"[^\n]+", normalized):
        raw = line_match.group(0)
        lines.append((raw.strip(), line_match.start() + len(raw) - len(raw.lstrip())))
    for index, (line, line_start) in enumerate(lines):
        tokens = list(ISSUE_RE.finditer(line))
        for token_index, token in enumerate(tokens):
            issue = int(token.group(1))
            if issue not in wanted_issues:
                continue
            end = tokens[token_index + 1].start() if token_index + 1 < len(tokens) else len(line)
            start = 0 if token_index == 0 else token.start()
            segment_lines = [line[start:end].strip()]
            # Only the final record on this line may own following lines.
            if token_index == len(tokens) - 1:
                for next_line, _offset in lines[index + 1:]:
                    if ISSUE_RE.search(next_line):
                        break
                    if contains_non_half_head_column(next_line) and "半头" not in next_line:
                        break
                    if re.match(r"^\s*(?:作者|网站|站点|栏目)\s*[:：]", next_line):
                        break
                    keyword = HALF_HEAD_KEYWORD_RE.search(next_line)
                    if keyword is not None:
                        prefix = next_line[:keyword.start()].strip(" \t:：-—|【】[]（）()◆◇★☆✿ღ")
                        if prefix:
                            break
                    segment_lines.append(next_line)
            yield issue, token.group(1), " ".join(segment_lines), line_start + token.start()

def candidate_issue_set(documents: list[str]) -> set[int]:
    issues: set[int] = set()
    for document in documents:
        for text in iter_search_texts(document):
            for match in ISSUE_RE.finditer(normalize_text(text)):
                try:
                    issues.add(int(match.group(1)))
                except ValueError:
                    continue
    return issues


def format_issue_list(issues: set[int] | list[int], width: int = 0) -> str:
    ordered = sorted({int(issue) for issue in issues})
    if not ordered:
        return ""
    if width <= 0:
        width = max(3, max(len(str(issue)) for issue in ordered))
    return ",".join(f"{issue:0{width}d}期" for issue in ordered)

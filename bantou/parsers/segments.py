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
    end = next_issue.start() if next_issue else min(len(normalized), raw_keyword_match.end() + 100)
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
    lines: list[tuple[str, int]] = []
    for line_match in re.finditer(r"[^\n]+", normalized):
        raw_line = line_match.group(0)
        line = raw_line.strip()
        leading = len(raw_line) - len(raw_line.lstrip())
        lines.append((line, line_match.start() + leading))
    seen: set[tuple[int, str, int]] = set()

    for index, (line, line_start) in enumerate(lines):
        issue_matches = list(ISSUE_RE.finditer(line))
        for match_index, match in enumerate(issue_matches):
            issue = int(match.group(1))
            if issue not in wanted_issues:
                continue
            segment_start = 0 if match_index == 0 else match.start()
            segment_end = (
                issue_matches[match_index + 1].start()
                if match_index + 1 < len(issue_matches)
                else len(line)
            )
            base_line = line[segment_start:segment_end].strip()
            segment_lines = [base_line]
            if not (
                strict_segment_has_keyword(base_line, DEFAULT_KEYWORDS)
                and values_in_segment(base_line)
                and segment_has_body_locator(base_line)
            ):
                for next_line, _next_line_start in lines[index + 1 : index + 5]:
                    if ISSUE_RE.search(next_line):
                        break
                    if contains_non_half_head_column(next_line) and "半头" not in next_line:
                        break
                    keyword_match = HALF_HEAD_KEYWORD_RE.search(next_line)
                    if keyword_match is not None:
                        prefix = next_line[: keyword_match.start()].strip(
                            " \t:：-—|【】[]（）()◆◇★☆✿ღ"
                        )
                        if prefix:
                            break
                    if re.match(r"^\s*(?:作者|网站|站点|栏目)\s*[:：]", next_line):
                        break
                    segment_lines.append(next_line)
                    combined = " ".join(segment_lines)
                    if (
                        strict_segment_has_keyword(combined, DEFAULT_KEYWORDS)
                        and values_in_segment(combined)
                        and segment_has_body_locator(combined)
                    ):
                        break
            segment = " ".join(segment_lines)
            position = line_start + match.start()
            key = (issue, compact_line(segment), position)
            if key in seen:
                continue
            seen.add(key)
            yield issue, match.group(1), segment, position

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

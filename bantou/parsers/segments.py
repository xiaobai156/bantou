# -*- coding: utf-8 -*-
import re

from ..documents import iter_search_texts
from ..domain import Match, PreviousInfo, Site
from ..site_profiles import (
    DEFAULT_KEYWORDS,
    HALF_HEAD_KEYWORD_RE,
    NON_HALF_HEAD_COLUMN_RE,
    OPEN_INFO_RE,
    SITE_EXTRA_KEYWORDS,
    STRICT_HALF_HEAD_RE,
)
from ..text import (
    ANY_VALUE_RE,
    ISSUE_RE,
    VALUE_RE,
    compact_line,
    html_to_text,
    normalize_half_head_value,
    normalize_text,
    valid_half_head_no,
)

def values_in_segment(segment: str) -> list[str]:
    values: list[str] = []
    for match in VALUE_RE.finditer(normalize_text(segment)):
        value = f"{int(match.group(1))}头{match.group(2)}"
        if value not in values:
            values.append(value)
    return values


def previous_rank_status(segment: str) -> tuple[str, str]:
    text = normalize_text(segment)
    open_match = re.search(
        r"开\s*[:：?？]?\s*([鼠牛虎兔龙蛇马羊猴鸡狗猪]?\s*\d{2,4})",
        text,
    )
    open_info = ""
    if open_match:
        open_info = re.sub(r"\s+", "", open_match.group(1))
        digits_match = re.search(r"\d+", open_info)
        digits = digits_match.group(0) if digits_match else ""
        if not digits or set(digits) <= {"0"}:
            open_info = ""

    markers = list(re.finditer(r"[对准中√错×xX]", text))
    marker = markers[-1].group(0) if markers else ""

    if not open_info:
        return "前一期没开奖号", ""
    if not marker:
        return "前一期没对错", open_info
    if marker in {"错", "×", "x", "X"}:
        return "前一期错", f"{open_info}{marker}"
    return "前一期对", f"{open_info}{marker}"


def previous_info_for(issue: int, match: Match | None) -> PreviousInfo:
    previous_issue = issue - 1
    if match is None:
        return PreviousInfo(previous_issue, "", "", "", False, "前一期没找到")

    reason, open_info = previous_rank_status(match.snippet)
    rank_ok = reason == "前一期对"
    return PreviousInfo(
        previous_issue,
        match.value,
        open_info or "未找到",
        reason,
        rank_ok,
        reason,
    )


def site_keywords(site: Site, keywords: tuple[str, ...]) -> tuple[str, ...]:
    if site.anchors:
        return site.anchors
    extras = SITE_EXTRA_KEYWORDS.get(site.url, ())
    if not extras:
        return keywords
    return keywords + tuple(keyword for keyword in extras if keyword not in keywords)


def strict_segment_has_keyword(segment: str, keywords: tuple[str, ...]) -> bool:
    compact = re.sub(r"\s+", "", normalize_text(segment))
    if HALF_HEAD_KEYWORD_RE.search(compact) or "半头" in compact:
        return True
    if any(keyword in compact for keyword in keywords):
        return True
    return False


def segment_matches_site_rule(
    segment: str,
    site: Site | None,
    fallback_keywords: tuple[str, ...],
) -> bool:
    compact = re.sub(r"\s+", "", normalize_text(segment))
    if site is not None and site.anchors:
        return any(anchor in compact for anchor in site.anchors)
    return strict_segment_has_keyword(compact, fallback_keywords)


def loose_segment_has_site_keyword(segment: str, site: Site | None) -> bool:
    if site is None:
        return False
    extras = SITE_EXTRA_KEYWORDS.get(site.url, ())
    if not extras:
        return False
    compact = re.sub(r"\s+", "", normalize_text(segment))
    return any(keyword in compact for keyword in extras)


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

def parse_keywords(value: str | None) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_KEYWORDS
    normalized = normalize_text(value)
    if not normalized:
        return ()
    return tuple(part.strip() for part in re.split(r"[,，、\s]+", normalized) if part.strip())


def segment_has_keyword(segment: str, keywords: tuple[str, ...]) -> bool:
    if not keywords:
        return True
    compact = re.sub(r"\s+", "", normalize_text(segment))
    return any(keyword in compact for keyword in keywords)


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


def explain_missing_reason(
    documents: list[str],
    wanted_issues: set[int],
    site: Site,
    target: str | None,
    keywords: tuple[str, ...],
    issue_width: int,
) -> str:
    texts = [normalize_text(html_to_text(document)) for document in documents]
    whole_text = "\n".join(text for text in texts if text)
    all_issues = {int(match.group(1)) for match in ISSUE_RE.finditer(whole_text)}

    present_issues = sorted(issue for issue in wanted_issues if issue in all_issues)
    missing_issues = sorted(issue for issue in wanted_issues if issue not in all_issues)
    if not present_issues:
        return f"页面打开成功，但没找到目标期数：{format_issue_list(wanted_issues, issue_width)}"
    if missing_issues:
        return (
            f"只找到部分期数；已找到：{format_issue_list(present_issues, issue_width)}；"
            f"缺少：{format_issue_list(missing_issues, issue_width)}"
        )

    site_level_keywords = site_keywords(site, keywords)
    issue_segments: list[str] = []
    keyword_segments: list[str] = []
    value_segments: list[tuple[str, list[str]]] = []
    for text in texts:
        for _, _, segment, _position in iter_issue_segments(text, wanted_issues):
            segment = focused_half_head_block(segment)
            issue_segments.append(segment)
            if strict_segment_has_keyword(segment, site_level_keywords):
                keyword_segments.append(segment)
                values = strict_values_in_segment(segment)
                if values:
                    value_segments.append((segment, values))

    if not issue_segments:
        return "找到了目标期数，但没有拿到对应期数的正文内容"
    if not keyword_segments:
        return "找到了目标期数，但没找到半头栏目词"
    if not value_segments:
        invalid_values: list[str] = []
        for segment in keyword_segments:
            for match in ANY_VALUE_RE.finditer(segment):
                if valid_half_head_no(match.group(1)):
                    continue
                value = f"{int(match.group(1))}头{match.group(2)}"
                if value not in invalid_values:
                    invalid_values.append(value)
        if invalid_values:
            return f"找到了半头栏目词，但半头数字超出 0-4 范围：{','.join(invalid_values)}"
        return "找到了半头栏目词，但没提取到头单双结果"

    if target is not None:
        found_values: list[str] = []
        for _, values in value_segments:
            for value in values:
                if value not in found_values:
                    found_values.append(value)
        if target not in found_values:
            return f"找到了半头栏目词，但没找到目标内容：{target}"

    return "页面结构变化，当前规则未匹配到有效结果"

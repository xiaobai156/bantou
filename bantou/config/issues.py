import re

from ..text import normalize_text


def parse_issue_range(value: str) -> tuple[list[int], int, str]:
    raw = normalize_text(value).replace("，", ",")
    raw = raw.replace("~", "-").replace("至", "-").replace("到", "-")
    pieces = [piece.strip() for piece in re.split(r"[,、\s]+", raw) if piece.strip()]
    issues: set[int] = set()
    width = 3

    for piece in pieces:
        range_match = re.fullmatch(r"(\d{1,4})-(\d{1,4})", piece)
        if range_match:
            left, right = range_match.groups()
            start, end = int(left), int(right)
            if start <= 0 or end <= 0:
                raise ValueError(f"期数必须大于 0：{piece}")
            width = max(width, len(left), len(right))
            step = 1 if start <= end else -1
            expanded = list(range(start, end + step, step))
            duplicate = next((issue for issue in expanded if issue in issues), None)
            if duplicate is not None:
                raise ValueError(f"期数重复：{duplicate}")
            issues.update(expanded)
            continue

        single_match = re.fullmatch(r"\d{1,4}", piece)
        if single_match:
            width = max(width, len(piece))
            issue = int(piece)
            if issue <= 0:
                raise ValueError(f"期数必须大于 0：{piece}")
            if issue in issues:
                raise ValueError(f"期数重复：{issue}")
            issues.add(issue)
            continue

        raise ValueError(f"期数格式不对：{piece}，例子：120 或 094-120")

    if not issues:
        raise ValueError("期数不能为空")

    ordered = sorted(issues)
    label = format_issue_label(ordered, width)
    return ordered, width, label


def format_issue_label(issues: list[int], width: int = 3) -> str:
    ordered = sorted(set(issues))
    if not ordered or any(type(issue) is not int or issue <= 0 for issue in ordered):
        raise ValueError("期数必须为正整数")
    if len(ordered) == 1:
        return f"{ordered[0]:0{width}d}"
    if ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"{ordered[0]:0{width}d}-{ordered[-1]:0{width}d}"
    return "_".join(f"{issue:0{width}d}" for issue in ordered)

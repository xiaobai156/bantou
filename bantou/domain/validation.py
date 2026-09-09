"""Pure final-result validation. It never reads historical caches."""
from collections import Counter
from .models import Match
from ..text import VALUE_RE

def validate_exact_matches(matches: list[Match], wanted_issues: set[int]) -> str | None:
    if not wanted_issues:
        return "指定期数不能为空"
    counts = Counter(match.issue for match in matches)
    if set(counts) != wanted_issues:
        return "返回期数与指定期数不一致"
    if any(count != 1 for count in counts.values()):
        return "指定期返回数量异常：" + ",".join(f"{issue}期={count}条" for issue, count in sorted(counts.items()))
    if any(VALUE_RE.fullmatch(match.value) is None for match in matches):
        return "返回半头值无效"
    return None

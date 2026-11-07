# -*- coding: utf-8 -*-
"""单站连续同值告警。

只读取正式近 10 期缓存里该站已有的记录（外加本次已抓到的当期结果做内存叠加），
按连续期号找「同一站连续若干期半头值相同」的段落，只打印提示，**不参与**任何
成功/失败判定，也不改写值或结果文件。

阈值口径对齐 AGENTS.md 的重复检测表述：连续 5 期为「疑似连续同值」，
6 期及以上措辞升级，但仍然只是告警。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

SINGLE_SITE_RUN_MINIMUM = 5
SINGLE_SITE_SEVERE_MINIMUM = 6


@dataclass(frozen=True)
class RepeatedValueRun:
    name: str
    start: int
    end: int
    value: str

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def find_repeated_value_runs(
    records: Mapping[int, str], *, minimum: int = SINGLE_SITE_RUN_MINIMUM
) -> list[tuple[int, int, str]]:
    """Return (start, end, value) runs of consecutive issues sharing one value.

    A missing issue breaks the run: only ``issue == previous + 1`` continues it.
    """
    runs: list[tuple[int, int, str]] = []
    start: int | None = None
    previous: int | None = None
    value = ""
    for issue in sorted(records):
        current = records[issue]
        if (
            start is not None
            and previous is not None
            and current == value
            and issue == previous + 1
        ):
            previous = issue
            continue
        if (
            start is not None
            and previous is not None
            and previous - start + 1 >= minimum
        ):
            runs.append((start, previous, value))
        start = previous = issue
        value = current
    if start is not None and previous is not None and previous - start + 1 >= minimum:
        runs.append((start, previous, value))
    return runs


def collect_repeated_value_runs(
    records_by_site: Mapping[str, Mapping[int, str]],
    *,
    minimum: int = SINGLE_SITE_RUN_MINIMUM,
) -> list[RepeatedValueRun]:
    runs: list[RepeatedValueRun] = []
    for name, records in records_by_site.items():
        for start, end, value in find_repeated_value_runs(records, minimum=minimum):
            runs.append(RepeatedValueRun(str(name), start, end, value))
    return sorted(runs, key=lambda run: (-run.length, run.name, run.start))


def format_run(run: RepeatedValueRun) -> str:
    if run.length >= SINGLE_SITE_SEVERE_MINIMUM:
        level = f"{SINGLE_SITE_SEVERE_MINIMUM}期及以上，按判重口径属拒收级，仍只告警"
    else:
        level = "疑似连续同值"
    return (
        f"{run.name} {run.start}期~{run.end}期 连续{run.length}期均为{run.value}"
        f"（{level}；不影响本期结果，请人工复核）"
    )


def records_by_site_from_payload(
    payload: Mapping[str, object] | None,
) -> dict[str, dict[int, str]]:
    """Read value-only records per site from a schema=2 cache payload."""
    view: dict[str, dict[int, str]] = {}
    if not isinstance(payload, Mapping):
        return view
    items = payload.get("sites")
    if not isinstance(items, list):
        return view
    for item in items:
        if not isinstance(item, Mapping):
            continue
        records = item.get("records")
        if not isinstance(records, Mapping):
            continue
        parsed: dict[int, str] = {}
        for issue_text, entry in records.items():
            if not isinstance(entry, Mapping):
                continue
            try:
                issue = int(str(issue_text))
            except (TypeError, ValueError):
                continue
            value = entry.get("value")
            if isinstance(value, str) and value:
                parsed[issue] = value
        view[str(item.get("name"))] = parsed
    return view


def overlay_current_results(
    view: dict[str, dict[int, str]], success_rows: Mapping[str, object]
) -> dict[str, dict[int, str]]:
    """Fold this run's verified results into the cache view (memory only)."""
    for name, row in success_rows.items():
        if not isinstance(row, tuple) or len(row) < 2:
            continue
        by_issue = row[1]
        if not isinstance(by_issue, Mapping):
            continue
        target = view.setdefault(str(name), {})
        for issue, match in by_issue.items():
            value = getattr(match, "value", None)
            if isinstance(value, str) and value:
                target[int(issue)] = value
    return view


def print_warnings(runs: list[RepeatedValueRun]) -> None:
    if not runs:
        return
    print("单站连续同值告警（只提示，不改变成功/失败判定）：")
    for run in runs:
        print("  " + format_run(run))

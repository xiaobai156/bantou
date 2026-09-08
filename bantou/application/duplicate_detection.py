# -*- coding: utf-8 -*-
"""Cache-only duplicate detector for the half-head project.

The detector never fetches a page and never mutates ``recent_10_cache.json``.
Its only authority is the recent-ten cache produced by the formal crawler.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from bantou.cache.validation import (
    CacheValidationError,
    validate_cache_payload,
)
from bantou.config.sites import read_sites
from bantou.domain.models import Site
from bantou.outputs.transaction import write_transaction
from bantou.paths import DEFAULT_SITES_FILE, DUPLICATE_BACKUP_FILE, RESULT_DIR

SEPARATE_DUPLICATE_STAT_NAMES = {"山高水厂", "跑狗论坛"}


def read_cache(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CacheValidationError(f"缓存无法读取：{exc}") from exc
    if not isinstance(payload, dict):
        raise CacheValidationError("缓存顶层必须是对象")
    return payload


@dataclass(frozen=True)
class DuplicateRun:
    left_name: str
    right_name: str
    start: int
    end: int
    values: tuple[tuple[int, str, int, int], ...]

    @property
    def length(self) -> int:
        return self.end - self.start + 1


@dataclass(frozen=True)
class DuplicateReport:
    cache_schema: int
    period: int
    issues: tuple[int, ...]
    cached_sites: int
    missing_sites: tuple[str, ...]
    identity_errors: tuple[str, ...]
    suspect_pairs: tuple[DuplicateRun, ...]
    duplicate_pairs: tuple[DuplicateRun, ...]
    separate_pairs: tuple[DuplicateRun, ...]


def cache_record_signature(record: dict[str, object]) -> tuple[str, int, int]:
    """Require value and source evidence even though only value defines duplication."""
    try:
        return str(record["value"]), int(record["order"]), int(record["position"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CacheValidationError(f"重复检测缓存记录缺少值、原始顺序或原始位置：{exc}") from exc


def _site_identity(site: Site) -> tuple[str, str, str, str, tuple[str, ...]]:
    return site.name, site.url, site.pick, site.parser_id, tuple(site.anchors)


def _cache_identity(item: dict[str, object]) -> tuple[str, str, str, str, tuple[str, ...]]:
    anchors = item.get("anchors")
    if not isinstance(anchors, list):
        raise CacheValidationError("重复检测缓存站点 anchors 无效")
    return (
        str(item.get("name") or ""),
        str(item.get("url") or ""),
        str(item.get("pick") or ""),
        str(item.get("parser") or ""),
        tuple(str(anchor) for anchor in anchors),
    )


def _records(item: dict[str, object]) -> dict[int, dict[str, object]]:
    raw_records = item.get("records")
    if not isinstance(raw_records, dict):
        raise CacheValidationError("重复检测缓存站点 records 无效")
    records: dict[int, dict[str, object]] = {}
    for issue_text, entry in raw_records.items():
        if not isinstance(entry, dict):
            raise CacheValidationError(f"{issue_text}期缓存记录无效")
        try:
            issue = int(issue_text)
        except (TypeError, ValueError) as exc:
            raise CacheValidationError(f"缓存期号无效：{issue_text}") from exc
        cache_record_signature(entry)
        records[issue] = entry
    return records


def find_consecutive_matches(
    left: dict[int, dict[str, object]],
    right: dict[int, dict[str, object]],
    issues: tuple[int, ...],
    *,
    minimum: int = 3,
) -> list[tuple[int, int, tuple[tuple[int, str, int, int], ...]]]:
    """Find continuous aligned runs without filling missing issue numbers."""
    runs: list[tuple[int, int, tuple[tuple[int, str, int, int], ...]]] = []
    start: int | None = None
    previous: int | None = None
    values: list[tuple[int, str, int, int]] = []

    def close_run() -> None:
        nonlocal start, previous, values
        if start is not None and previous is not None and len(values) >= minimum:
            runs.append((start, previous, tuple(values)))
        start = None
        previous = None
        values = []

    for issue in issues:
        left_entry = left.get(issue)
        right_entry = right.get(issue)
        same = (
            left_entry is not None
            and right_entry is not None
            and str(left_entry.get("value") or "") == str(right_entry.get("value") or "")
        )
        if not same:
            close_run()
            continue

        signature = cache_record_signature(left_entry)
        if start is None or previous is None or issue != previous + 1:
            close_run()
            start = issue
        values.append((issue, *signature))
        previous = issue

    close_run()
    return runs


def evaluate_cache(
    payload: dict[str, object], sites: list[Site], *, window: int = 10
) -> DuplicateReport:
    """Compare configured sites solely from a validated recent-ten cache."""
    cache_schema = int(payload.get("schema") or 0)
    validated = validate_cache_payload(payload)
    if not 1 <= window <= 10:
        raise ValueError("检测窗口只能是 1 到 10 期")

    all_issues = tuple(int(issue) for issue in validated["issues"])
    issues = all_issues[-window:]
    cached_items = validated["sites"]
    if not isinstance(cached_items, list):
        raise CacheValidationError("缓存 sites 必须是数组")
    by_name = {str(item["name"]): item for item in cached_items}
    configured_names = {site.name for site in sites}
    missing_sites: list[str] = []
    identity_errors: list[str] = []
    eligible: dict[str, dict[int, dict[str, object]]] = {}

    for site in sites:
        item = by_name.get(site.name)
        if item is None:
            missing_sites.append(f"{site.name}：缓存中没有完整近10期来源证据")
            continue
        identity_ok = _cache_identity(item) == _site_identity(site)
        if not identity_ok:
            identity_errors.append(f"{site.name}：正式配置与缓存业务身份不一致")
            continue
        records = _records(item)
        absent = [issue for issue in issues if issue not in records]
        if absent:
            missing_sites.append(
                f"{site.name}：缓存缺少 {','.join(f'{issue}期' for issue in absent)}"
            )
        eligible[site.name] = records

    for cached_name in sorted(set(by_name) - configured_names):
        identity_errors.append(f"{cached_name}：缓存存在已不在正式配置中的站点")

    suspect_pairs: list[DuplicateRun] = []
    duplicate_pairs: list[DuplicateRun] = []
    separate_pairs: list[DuplicateRun] = []
    names = sorted(eligible)
    for left_index, left_name in enumerate(names):
        for right_name in names[left_index + 1 :]:
            for start, end, values in find_consecutive_matches(
                eligible[left_name], eligible[right_name], issues
            ):
                run = DuplicateRun(left_name, right_name, start, end, values)
                if left_name in SEPARATE_DUPLICATE_STAT_NAMES or right_name in SEPARATE_DUPLICATE_STAT_NAMES:
                    separate_pairs.append(run)
                elif run.length >= 6:
                    duplicate_pairs.append(run)
                else:
                    suspect_pairs.append(run)

    return DuplicateReport(
        cache_schema=cache_schema,
        period=int(validated["period"]),
        issues=issues,
        cached_sites=len(cached_items),
        missing_sites=tuple(missing_sites),
        identity_errors=tuple(identity_errors),
        suspect_pairs=tuple(suspect_pairs),
        duplicate_pairs=tuple(duplicate_pairs),
        separate_pairs=tuple(separate_pairs),
    )


def _format_run_values(run: DuplicateRun) -> str:
    return " ".join(
        f"{issue}期:{value}@顺序{order}/位置{position}"
        for issue, value, order, position in run.values
    )


def format_report(report: DuplicateReport) -> str:
    basis = "recent_10_cache.json schema=2（含原始顺序/位置和来源证据，不联网、不写缓存）"
    rule = "判定依据：同一期半头值相同且期号连续；原始顺序/位置只作来源证据"
    lines = [
        f"检测依据：{basis}",
        f"检测窗口：{report.issues[0]}期~{report.issues[-1]}期，共 {len(report.issues)} 期",
        rule,
        "阈值：连续1-2期不处理；3-5期疑似重复；6期及以上重复拒收",
        f"缓存站点：{report.cached_sites} 个",
        f"可比较疑似重复：{len(report.suspect_pairs)} 段",
        f"可比较重复拒收：{len(report.duplicate_pairs)} 段",
        f"专项单独列出：{len(report.separate_pairs)} 段",
        "",
        "===== 缓存或身份异常 =====",
    ]
    errors = [*report.missing_sites, *report.identity_errors]
    lines.extend(errors or ["无"])
    lines.extend(["", "===== 疑似重复（连续3-5期） ====="])
    if report.suspect_pairs:
        lines.append("网站A\t网站B\t起始期\t结束期\t连续期数\t逐期原始数据")
        lines.extend(
            f"{run.left_name}\t{run.right_name}\t{run.start}期\t{run.end}期\t{run.length}\t{_format_run_values(run)}"
            for run in report.suspect_pairs
        )
    else:
        lines.append("无")
    lines.extend(["", "===== 重复拒收（连续6期及以上） ====="])
    if report.duplicate_pairs:
        lines.append("网站A\t网站B\t起始期\t结束期\t连续期数\t逐期原始数据")
        lines.extend(
            f"{run.left_name}\t{run.right_name}\t{run.start}期\t{run.end}期\t{run.length}\t{_format_run_values(run)}"
            for run in report.duplicate_pairs
        )
    else:
        lines.append("无")
    lines.extend(["", "===== 专项单独列出 ====="])
    if report.separate_pairs:
        lines.append("网站A\t网站B\t起始期\t结束期\t连续期数\t逐期原始数据")
        lines.extend(
            f"{run.left_name}\t{run.right_name}\t{run.start}期\t{run.end}期\t{run.length}\t{_format_run_values(run)}"
            for run in report.separate_pairs
        )
    else:
        lines.append("无")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="半头正式重复检测（只读取 recent_10_cache.json）")
    parser.add_argument("--period", type=int, help="当前期，必须手动指定期数，例如 202")
    parser.add_argument("--window", type=int, default=10, help="缓存内比较期数，默认 10")
    parser.add_argument("--sites", default=str(DEFAULT_SITES_FILE), help="正式 sites.json")
    parser.add_argument("--backup-file", default=str(DUPLICATE_BACKUP_FILE), help="schema=2 缓存文件")
    parser.add_argument("--output", default="", help="检测报告输出路径")
    parser.add_argument("--use-backup", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--write-backup", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.write_backup:
        raise ValueError("正式重复检测器不允许写入 recent_10_cache.json")
    if args.period is None:
        print("重复检测拒绝：必须手动指定期数")
        return 2

    try:
        payload = read_cache(Path(args.backup_file))
        if args.period is not None and args.period != int(payload["period"]):
            raise CacheValidationError(
                f"指定 {args.period}期 与缓存最新期 {payload['period']}期不一致，拒绝混用"
            )
        sites = read_sites(Path(args.sites))
        report = evaluate_cache(payload, sites, window=args.window)
    except (CacheValidationError, FileNotFoundError, ValueError) as exc:
        print(f"重复检测拒绝：{exc}")
        return 2

    output_path = Path(args.output) if args.output else RESULT_DIR / f"{report.period}期连续8期重复检测.txt"
    write_transaction({output_path: format_report(report).encode("utf-8-sig")})
    print(
        f"重复检测完成：疑似 {len(report.suspect_pairs)} 段，"
        f"重复拒收 {len(report.duplicate_pairs)} 段，"
        f"缓存/身份异常 {len(report.missing_sites) + len(report.identity_errors)} 项"
    )
    print(f"检测报告：{output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

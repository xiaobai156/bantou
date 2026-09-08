# -*- coding: utf-8 -*-
"""Formal single-period application flow for the half-head crawler."""

from __future__ import annotations

import concurrent.futures
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from ..cache.builders import build_bootstrap_cache_payload
from ..cache.legacy import migrate_legacy_cache_roll_payload
from ..cache.updates import merge_cache_updates, roll_cache_payload
from ..cache.validation import (
    CACHE_STATE_RESET,
    CacheValidationError,
    read_cache_for_update,
)
from ..config.cli import build_parser, resolve_inputs
from ..config.issues import parse_issue_range
from ..config.sites import read_failed_sites, read_sites
from ..domain.models import Match, Site, SiteResult
from ..fetching.policy import INSECURE_TLS_COMPATIBILITY_URLS, run_transport_scope
from ..fetching.transport import canonical_url
from ..outputs.formatting import (
    append_script_error,
    build_success_output_lines,
    configure_console_encoding,
    default_fail_path_for_issues,
    default_output_names,
    fail_line,
    read_fail_entries,
    read_fail_entries_from_lines,
    read_success_data,
    spaced_failure_lines,
)
from ..outputs.transaction import formal_write_lock, write_transaction
from ..paths import DUPLICATE_BACKUP_FILE, FAILURE_RESULT_DIR
from ..text import normalize_target
from .site_crawl import crawl_site, format_progress_line, print_failure_summary


def _failure_rows(lines: list[str]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 4:
            rows.append((parts[0], parts[2], parts[3]))
    return rows


def _success_bytes(rows: list[tuple[str, str, str, str]]) -> bytes:
    return ("\n".join(build_success_output_lines(rows)) + "\n").encode("utf-8-sig")


def _failure_url_identity(url: str) -> str:
    parsed = urlsplit(url.strip())
    base = canonical_url(url)
    return base + (f"#{parsed.fragment}" if parsed.fragment else "")


def _failure_bytes(lines: list[str]) -> bytes | None:
    formatted = spaced_failure_lines(lines)
    if len(formatted) <= 1:
        return None
    return ("\n".join(formatted) + "\n").encode("utf-8-sig")


def _merge_retry_rows(
    issues_label: str,
    retry_rows: list[tuple[str, str, str, str]],
    retry_fail_lines: list[str],
) -> tuple[list[tuple[str, str, str, str]], list[str]]:
    success_name, fail_name = default_output_names(issues_label)
    success_path = Path(default_success_name_path(success_name))
    fail_path = Path(default_failure_name_path(fail_name))
    issue_text = f"{issues_label}期"
    existing_success = read_success_data(success_path, issue_text)
    existing_success_names = {row[0] for row in existing_success}
    for row in retry_rows:
        if row[0] not in existing_success_names:
            existing_success.append(row)
            existing_success_names.add(row[0])
    retry_success_names = {row[0] for row in retry_rows}
    retry_success_urls = {_failure_url_identity(row[3]) for row in retry_rows}
    retry_failures = {
        name: (name, category, reason, url)
        for name, category, reason, url in read_fail_entries_from_lines(retry_fail_lines)
    }
    existing_failures = {
        name: (name, category, reason, url)
        for name, category, reason, url in read_fail_entries(fail_path)
        if name not in retry_success_names and _failure_url_identity(url) not in retry_success_urls
    }
    existing_failures.update(retry_failures)
    lines = ["网站名称\t分类\t原因\t网址"]
    lines.extend(
        f"{name}\t{category}\t{reason}\t{url}"
        for name, category, reason, url in existing_failures.values()
    )
    return existing_success, lines


def default_success_name_path(name: str) -> Path:
    from ..paths import RESULT_DIR

    return RESULT_DIR / name


def default_failure_name_path(name: str) -> Path:
    return FAILURE_RESULT_DIR / name


def _prepare_cache_payload(
    args,
    issues: list[int],
    sites: list[Site],
    success_rows: dict[str, tuple[Site, dict[int, Match]]],
    failures: list[tuple[str, str, str]],
) -> tuple[dict[str, object] | None, dict[str, str]]:
    if args.rebuild_cache:
        raise CacheValidationError("缓存重建已停用；缓存只允许每天单期顺序滚动")
    if args.write_backup and len(issues) != 1:
        raise CacheValidationError("正式缓存只允许单期抓取后更新")
    if args.diagnose or args.multi_mode:
        return None, {}
    if not args.write_backup:
        return None, {}

    payload = read_cache_for_update(
        DUPLICATE_BACKUP_FILE,
        allow_legacy_bootstrap=True,
    )
    if payload.get("state") == CACHE_STATE_RESET:
        return build_bootstrap_cache_payload(
            issues[0], issues, success_rows, failures
        ), {}
    if payload.get("schema") == 1:
        return migrate_legacy_cache_roll_payload(
            payload, issues[0], sites, success_rows, failures
        )
    if args.retry_fail:
        updated, conflicts = merge_cache_updates(payload, success_rows, failures)
        period_text = str(issues[0])
        missing = [
            name for name, (_site, records) in success_rows.items()
            if not any(
                isinstance(item, dict)
                and period_text in item.get("records", {})
                for item in updated.get("sites", [])
                if item.get("name") == name
            )
        ]
        if missing:
            conflicts.update({name: "缓存缺少目标期记录" for name in missing})
        return updated, conflicts
    if len(issues) == 1:
        return roll_cache_payload(payload, issues[0], sites, success_rows, failures)
    raise CacheValidationError(
        "多期不更新缓存；缓存只允许按当天单期顺序滚动"
    )


def _prepare_cache_update(
    args,
    issues: list[int],
    sites: list[Site],
    rank_rows: list[tuple[str, str, str, str]],
    cache_rows: dict[str, tuple[Site, dict[int, Match]]],
    fail_lines: list[str],
) -> tuple[list[tuple[str, str, str, str]], dict[str, tuple[Site, dict[int, Match]]], list[str], dict[str, object] | None, dict[str, str]]:
    payload, conflicts = _prepare_cache_payload(
        args, issues, sites, cache_rows, _failure_rows(fail_lines)
    )
    if conflicts:
        print(
            "缓存更新提示（不影响本次抓取结果）："
            + "；".join(f"{name}：{reason}" for name, reason in sorted(conflicts.items())),
            file=sys.stderr,
        )
    return rank_rows, cache_rows, fail_lines, payload, conflicts


def _run_sites(
    args, sites: list[Site], wanted_issues: set[int], target: str | None
) -> list[SiteResult]:
    worker_count = max(1, min(args.workers, len(sites)))
    print(f"并发线程数：{worker_count}", flush=True)
    results: list[SiteResult] = []
    start_time = time.perf_counter()
    progress_success = 0
    progress_fail = 0

    def record_result(index: int, site: Site, result: SiteResult) -> None:
        nonlocal progress_success, progress_fail
        results.append(result)
        if result.matches:
            progress_success += 1
        else:
            progress_fail += 1
        print(
            format_progress_line(
                len(results),
                len(sites),
                progress_success,
                progress_fail,
                time.perf_counter() - start_time,
                site.name,
            ),
            flush=True,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {}
        for index, site in enumerate(sites, start=1):
            try:
                future = executor.submit(
                    crawl_site,
                    index,
                    site,
                    wanted_issues,
                    target,
                    args.timeout,
                    args.verify_ssl,
                    args.retries,
                    max(0, args.delay) * ((index - 1) % worker_count),
                    site_timeout=args.site_timeout,
                )
            except Exception as exc:
                record_result(
                    index,
                    site,
                    SiteResult(
                        index,
                        site,
                        [],
                        f"任务提交失败：{type(exc).__name__}: {exc}",
                    ),
                )
            else:
                future_map[future] = (index, site)

        for future in concurrent.futures.as_completed(future_map):
            index, site = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                result = SiteResult(index, site, [], f"解析失败：{type(exc).__name__}: {exc}")
            record_result(index, site, result)
    return results


def _finalize_run(
    args,
    issues: list[int],
    sites: list[Site],
    issues_label: str,
    rank_rows: list[tuple[str, str, str, str]],
    cache_rows: dict[str, tuple[Site, dict[int, Match]]],
    fail_lines: list[str],
) -> int:
    if args.diagnose:
        print(f"完成：成功 {len(rank_rows)} 条，失败 {len(fail_lines) - 1} 条")
        print_failure_summary(fail_lines)
        print("无写入诊断完成：未更新成功TXT、失败TXT或 recent_10_cache.json")
        return 0

    with formal_write_lock():
        cache_update_error: CacheValidationError | None = None
        try:
            rank_rows, cache_rows, fail_lines, cache_payload, cache_conflicts = _prepare_cache_update(
                args, issues, sites, rank_rows, cache_rows, fail_lines
            )
            if cache_conflicts:
                cache_update_error = CacheValidationError(
                    "缓存更新未完成："
                    + "；".join(
                        f"{name}：{reason}"
                        for name, reason in sorted(cache_conflicts.items())
                    )
                )
        except CacheValidationError as exc:
            cache_payload = None
            cache_update_error = exc

        print(f"完成：成功 {len(rank_rows)} 条，失败 {len(fail_lines) - 1} 条")
        print_failure_summary(fail_lines)
        if cache_update_error is not None:
            print(
                f"缓存更新未完成（不影响本次抓取结果）：{cache_update_error}",
                file=sys.stderr,
            )

        default_success_name, default_fail_name = default_output_names(issues_label)
        success_path = default_success_name_path(args.success_out or default_success_name)
        fail_path = default_failure_name_path(args.fail_out or default_fail_name)
        if args.retry_fail:
            rank_rows, fail_lines = _merge_retry_rows(
                issues_label, rank_rows, fail_lines
            )

        try:
            write_transaction(
                {
                    success_path: _success_bytes(rank_rows),
                    fail_path: _failure_bytes(fail_lines),
                }
            )
        except Exception as exc:
            print(f"结果输出事务失败：{exc}", file=sys.stderr)
            return 2

        cache_write_error: Exception | None = None
        if cache_payload is not None:
            try:
                write_transaction(
                    {
                        DUPLICATE_BACKUP_FILE: (
                            json.dumps(cache_payload, ensure_ascii=False, indent=2)
                            + "\n"
                        ).encode("utf-8-sig")
                    }
                )
            except Exception as exc:
                cache_write_error = exc

        print(f"成功结果：{success_path.resolve()}")
        print(
            f"失败结果：{fail_path.resolve() if fail_path.exists() else '无失败，不生成失败文件'}"
        )
        if cache_payload is not None:
            if cache_write_error is None:
                print(f"最近10期缓存已独立同步：{DUPLICATE_BACKUP_FILE.resolve()}")
            else:
                print(
                    f"缓存写入失败（结果文件已保留）：{cache_write_error}",
                    file=sys.stderr,
                )
        return 2 if cache_update_error is not None or cache_write_error is not None else 0


def main(argv: list[str] | None = None) -> int:
    configure_console_encoding()
    args = build_parser().parse_args(argv)
    if args.diagnose and (args.write_backup or args.rebuild_cache):
        print("输入错误：--diagnose 不允许写入 TXT 或 recent_10_cache.json", file=sys.stderr)
        return 2

    try:
        if args.workers < 1:
            raise ValueError("--workers 必须大于 0")
        if args.timeout < 1:
            raise ValueError("--timeout 必须大于 0")
        if args.site_timeout < 1:
            raise ValueError("--site-timeout 必须大于 0")
        if args.retries < 0:
            raise ValueError("--retries 不能小于 0")
        if args.delay < 0:
            raise ValueError("--delay 不能小于 0")
        target_input, issues_input, sites_input = resolve_inputs(args)
        target = normalize_target(target_input) if target_input else None
        issues, issue_width, issues_label = parse_issue_range(issues_input)
        if args.retry_fail and len(issues) != 1:
            raise ValueError("失败站点重跑一次只能指定一期")
        if args.rebuild_cache:
            raise ValueError("缓存重建已停用；缓存只允许每天单期顺序滚动")
        if not args.diagnose and not args.multi_mode and len(issues) == 1:
            args.write_backup = True
        if args.write_backup and len(issues) != 1:
            raise ValueError("正式缓存只允许单期抓取后更新")
        wanted_issues = set(issues)
        sites = read_sites(Path(sites_input))
        if args.retry_fail:
            retry_fail_path = default_fail_path_for_issues(issues_label, args.retry_fail_file)
            sites = read_failed_sites(retry_fail_path, sites)
            print(f"只重跑失败网站：{len(sites)} 个，来源：{retry_fail_path.resolve()}")
        sites = sorted(
            sites,
            key=lambda site: site.line_no,
        )
        if not args.verify_ssl:
            unregistered = [
                site.name
                for site in sites
                if canonical_url(site.url) not in INSECURE_TLS_COMPATIBILITY_URLS
            ]
            if unregistered:
                raise ValueError(
                    "--no-verify-ssl 只允许明确登记的TLS兼容站；未登记："
                    + "、".join(unregistered)
                )
    except Exception as exc:
        print(f"输入错误：{exc}", file=sys.stderr)
        return 2

    fail_lines = ["网站名称\t分类\t原因\t网址"]
    rank_rows: list[tuple[str, str, str, str]] = []
    cache_rows: dict[str, tuple[Site, dict[int, Match]]] = {}
    with run_transport_scope():
        results = _run_sites(args, sites, wanted_issues, target)

    for result in sorted(results, key=lambda item: item.index):
        site = result.site
        matches = [match for match in result.matches if match.issue in wanted_issues]
        if result.error or not matches or {match.issue for match in matches} != wanted_issues:
            reason = result.error or result.miss_reason or f"{issues_label}期未抓到头"
            fail_lines.append(fail_line(site, append_script_error(reason, result.script_error_count)))
            continue
        by_issue = {match.issue: match for match in matches}
        cache_rows[site.name] = (site, by_issue)
        for match in matches:
            rank_rows.append((site.name, f"{match.issue:0{issue_width}d}期", match.value, site.url))

    return _finalize_run(
        args, issues, sites, issues_label, rank_rows, cache_rows, fail_lines
    )

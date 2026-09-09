# -*- coding: utf-8 -*-
"""Formal site workflow: identity-bound parse, direction gate, and timeout."""

from __future__ import annotations

import time

from ..documents.collection import (
    collect_dynamic_browser_documents,
    collect_site_documents,
    resolve_mengxiaomeng_detail_url,
    resolve_wealth_reference_detail_url,
)
from ..documents.dynamic.aggregate import resolve_user_aggregate_detail_url
from ..documents.dynamic.records import (
    dynamic_browser_fallback_allowed,
    target_record_document,
)
from ..documents.dynamic.routes import (
    dynamic_record_scope,
    is_user_aggregate_page_without_record_id,
)
from ..domain.models import Site, SiteResult
from ..domain.validation import validate_exact_matches
from ..fetching.policy import FetchError, should_retry_fetch_error
from ..outputs.formatting import failure_category
from ..parsers.matching import (
    apply_direction_source_scope,
    apply_secondary_site_scope,
    site_scoped_raw_matches,
)
from ..parsers.segments import candidate_issue_set, format_issue_list
from ..selection.engine import (
    conflicting_issue_values,
    select_direction_window_matches,
    select_requested_matches,
)
from ..text import html_to_text, normalize_text


def debug_sample_from_documents(
    documents: list[str], wanted_issues: set[int], limit: int = 4000
) -> str:
    samples: list[str] = []
    for document in documents:
        text = normalize_text(html_to_text(document))
        if not text:
            continue
        for issue in sorted(wanted_issues):
            marker = f"{issue}期"
            index = text.find(marker)
            if index >= 0:
                samples.append(text[max(0, index - 500) : index + 1800])
                break
        if len("\n\n".join(samples)) >= limit:
            break
    if not samples:
        samples = [
            normalize_text(html_to_text(document))[:1500]
            for document in documents[:3]
            if normalize_text(html_to_text(document))
        ]
    return "\n\n-----\n\n".join(samples)[:limit]


def _site_deadline(timeout: int, site_timeout: int | None) -> float:
    if site_timeout is None:
        site_timeout = max(45, timeout * 3)
    return time.monotonic() + site_timeout


def _fetch_url_for_issue(
    site: Site,
    issue: int,
    timeout: int,
    verify_ssl: bool,
    deadline: float,
) -> str:
    if site.entry_mode == "issue_link":
        return resolve_mengxiaomeng_detail_url(
            site, issue, timeout, verify_ssl, deadline=deadline
        )
    if site.entry_mode == "reference_issue_link":
        return resolve_wealth_reference_detail_url(
            site, issue, timeout, verify_ssl, deadline=deadline
        )
    if is_user_aggregate_page_without_record_id(site.url):
        return resolve_user_aggregate_detail_url(
            site, issue, timeout, verify_ssl, deadline=deadline
        )
    return site.fetch_url or site.url


def _documents_for_requested_issues(
    site: Site,
    wanted_issues: set[int],
    timeout: int,
    verify_ssl: bool,
    deadline: float,
) -> tuple[list, list[str]]:
    """Fetch issue-specific entry pages per issue; list pages only once."""
    issue_specific = site.entry_mode in {"issue_link", "reference_issue_link"} or is_user_aggregate_page_without_record_id(site.url)
    issue_groups = sorted(wanted_issues) if issue_specific else [max(wanted_issues)]
    documents = []
    script_errors: list[str] = []
    for issue in issue_groups:
        if time.monotonic() >= deadline:
            raise FetchError("单站总超时：停止继续抓取期数入口")
        fetch_url = _fetch_url_for_issue(site, issue, timeout, verify_ssl, deadline)
        try:
            loaded, errors = collect_site_documents(
                site,
                fetch_url,
                {issue} if issue_specific else wanted_issues,
                timeout,
                verify_ssl,
                deadline=deadline,
            )
            scoped = target_record_document(loaded, fetch_url, site, wanted_issues={issue} if issue_specific else wanted_issues)
        except ValueError as exc:
            if dynamic_record_scope(fetch_url) is None or not dynamic_browser_fallback_allowed(exc):
                raise
            browser_documents = collect_dynamic_browser_documents(
                fetch_url, timeout, verify_ssl, deadline=deadline
            )
            scoped = target_record_document(browser_documents, fetch_url, site, wanted_issues={issue} if issue_specific else wanted_issues)
            errors = []
        documents.extend(scoped)
        script_errors.extend(errors)
    return documents, script_errors


def crawl_site(
    index: int,
    site: Site,
    wanted_issues: set[int],
    target: str | None,
    timeout: int,
    verify_ssl: bool,
    retries: int,
    start_delay: float = 0,
    *,
    site_timeout: int | None = None,
) -> SiteResult:
    if not wanted_issues:
        return SiteResult(index, site, [], "指定期数不能为空")
    if site_timeout is not None and site_timeout <= 0:
        return SiteResult(index, site, [], "单站总超时：未发起请求")
    if start_delay > 0:
        time.sleep(start_delay)

    deadline = _site_deadline(timeout, site_timeout)
    last_error: str | None = None
    last_script_errors = 0
    debug_sample = ""
    issue_width = max(3, max(len(str(issue)) for issue in wanted_issues))

    for attempt in range(retries + 1):
        if time.monotonic() >= deadline:
            last_error = "单站总超时：停止继续抓取"
            break
        try:
            documents, script_errors = _documents_for_requested_issues(
                site, wanted_issues, timeout, verify_ssl, deadline
            )
            last_script_errors = len(script_errors)
            candidate_issues = candidate_issue_set(documents)
            candidate_issues.update(wanted_issues)
            raw_matches = site_scoped_raw_matches(
                documents,
                candidate_issues,
                site,
                region_issues=wanted_issues,
            )
            direction_candidates, source_reason = apply_direction_source_scope(
                raw_matches, site, documents
            )
            if source_reason is not None:
                return SiteResult(
                    index,
                    site,
                    [],
                    None,
                    last_script_errors,
                    source_reason,
                    debug_sample_from_documents(documents, wanted_issues),
                )
            matches, secondary_reason, rejection_evidence = apply_secondary_site_scope(
                direction_candidates, site, wanted_issues
            )
            if secondary_reason is not None:
                return SiteResult(
                    index, site, [], None, last_script_errors, secondary_reason,
                    debug_sample_from_documents(documents, wanted_issues),
                    rejection_evidence,
                    direction_candidates,
                )
            decision = select_direction_window_matches(
                matches, wanted_issues, site.pick
            )
            if decision.reason is not None:
                return SiteResult(
                    index, site, [], None, last_script_errors, decision.reason,
                    debug_sample_from_documents(documents, wanted_issues),
                    direction_evidence=decision.evidence,
                )
            direction_evidence = decision.evidence
            window_conflicts = conflicting_issue_values(
                direction_evidence, wanted_issues
            )
            if window_conflicts:
                details = "；".join(
                    f"{issue}期同期候选冲突：{','.join(values)}"
                    for issue, values in window_conflicts.items()
                )
                return SiteResult(
                    index,
                    site,
                    [],
                    None,
                    last_script_errors,
                    details,
                    debug_sample_from_documents(documents, wanted_issues),
                    direction_evidence=direction_evidence,
                )
            matches = list(direction_evidence)
            final_decision = select_requested_matches(
                matches, wanted_issues, site.pick
            )
            if final_decision.reason is not None:
                return SiteResult(
                    index, site, [], None, last_script_errors, final_decision.reason,
                    debug_sample_from_documents(documents, wanted_issues),
                    rejection_evidence,
                    direction_evidence,
                )
            matches = final_decision.matches
            if target is not None:
                matches = [match for match in matches if match.value == target]
            missing = sorted(wanted_issues - {match.issue for match in matches})
            if not missing:
                final_error = validate_exact_matches(matches, wanted_issues)
                if final_error:
                    return SiteResult(index, site, [], miss_reason=final_error)
                return SiteResult(
                    index,
                    site,
                    matches,
                    None,
                    last_script_errors,
                    rejection_evidence=rejection_evidence,
                    direction_evidence=direction_evidence,
                )
            found = {match.issue for match in matches}
            missing_text = format_issue_list(missing, issue_width)
            found_text = format_issue_list(found, issue_width) or "无"
            last_error = f"只找到部分期数；已找到：{found_text}；缺少：{missing_text}"
            debug_sample = debug_sample_from_documents(documents, wanted_issues)
            if attempt >= retries:
                return SiteResult(index, site, [], None, last_script_errors, last_error, debug_sample)
        except FetchError as exc:
            last_error = str(exc)
            if not should_retry_fetch_error(exc):
                break
        except Exception as exc:
            last_error = f"解析失败：{type(exc).__name__}: {exc}"

        if attempt < retries and time.monotonic() < deadline:
            time.sleep(min(0.3 * (attempt + 1), max(0.0, deadline - time.monotonic())))

    return SiteResult(index, site, [], last_error or "未知错误", last_script_errors, None, debug_sample)


def print_failure_summary(fail_lines: list[str]) -> None:
    counts: dict[str, int] = {}
    for line in fail_lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        category = parts[1] if len(parts) >= 4 else failure_category(line)
        if category:
            counts[category] = counts.get(category, 0) + 1
    if counts:
        print("失败分类：" + "，".join(f"{category} {count}" for category, count in sorted(counts.items())))


def format_progress_line(
    completed: int,
    total: int,
    success_count: int,
    fail_count: int,
    elapsed_seconds: float,
    site_name: str,
) -> str:
    percent = int(completed * 100 / total) if total else 0
    return (
        f"[进度 {completed}/{total} {percent}% 成功 {success_count} "
        f"失败 {fail_count} 用时 {elapsed_seconds:.1f}s] 当前: {site_name}"
    )

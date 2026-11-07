# -*- coding: utf-8 -*-
"""Formal site workflow: identity-bound parse, direction gate, and timeout."""

from __future__ import annotations

import re
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
from ..site_profiles.registry import (
    DEDICATED_RENDERED_AUTHOR_CONTEXT_URLS,
    DEDICATED_RENDERED_SITE_RULES,
    SITE_RENDERED_PAGE_AUTHORITY_URLS,
)
from ..domain.models import Match, Site, SiteResult
from ..domain.validation import validate_exact_matches
from ..fetching.policy import FetchError, should_retry_fetch_error
from ..outputs.formatting import failure_category
from ..parsers.matching import (
    ambiguous_column_issues,
    apply_direction_source_scope,
    apply_secondary_site_scope,
    column_labels,
    has_generic_half_head_anchor,
    same_period_position_conflicts,
    site_scoped_raw_matches,
)
from ..parsers.segments import candidate_issue_set, format_issue_list
from ..selection.engine import (
    conflicting_issue_values,
    direction_window,
    select_direction_window_matches,
    select_requested_matches,
)
from ..text import html_to_text, normalize_text

# 本期未开奖时站点普遍写「开？00」「开:0000」「开 ??」；已开奖写「开虎16」「开 13」。
# 繁体站写「開:0000 / 開:虎16」，与简体等价处理（烟花易冷）。
# 这两类记录在页面上往往并排存在（当期记录 + 历史/存档记录），不是同一类候选。
_PENDING_OPEN_RE = re.compile(r"[开開][:：]?[?？]{1,}|[开開][:：]?[0０]{2,}")


def draw_state(match: Match) -> str:
    """Return whether a record still waits for the draw or already has a result."""
    compact = re.sub(r"\s+", "", normalize_text(match.snippet))
    return "pending" if _PENDING_OPEN_RE.search(compact) else "settled"


# 泛化锚点站在权威文档里只剩一条本期候选时，没有任何同页对照，必须证明栏目归属。
SINGLE_CANDIDATE_NO_LABEL = "单条候选且栏目名不可辨识"
SINGLE_CANDIDATE_NO_REFERENCE = "单条候选且同文档没有其他期记录可对照"
SINGLE_CANDIDATE_UNSEEN_LABEL = "单条候选且栏目名在同文档其他期从未出现"


def single_candidate_verdict(candidate: Match, other_period_matches: list[Match]) -> str:
    """Prove a lone candidate's column from the page itself; "" means accepted.

    Only page evidence is used: the candidate's own column label must reappear on
    another period of the same authoritative document.
    """
    labels = column_labels(candidate.snippet)
    if not labels:
        return (
            f"{SINGLE_CANDIDATE_NO_LABEL}："
            f"{candidate.issue}期 {candidate.value}@位置{candidate.position}"
        )
    if not other_period_matches:
        return (
            f"{SINGLE_CANDIDATE_NO_REFERENCE}："
            f"{candidate.issue}期 {candidate.value}@位置{candidate.position}"
        )
    seen: set[str] = set()
    for match in other_period_matches:
        seen |= column_labels(match.snippet)
    if labels & seen:
        return ""
    return (
        f"{SINGLE_CANDIDATE_UNSEEN_LABEL}："
        f"{candidate.issue}期 {candidate.value}@位置{candidate.position}"
        f"（{'/'.join(sorted(labels))}）"
    )


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
    if (
        is_user_aggregate_page_without_record_id(site.url)
        and site.url not in SITE_RENDERED_PAGE_AUTHORITY_URLS
    ):
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
    issue_specific = (
        site.entry_mode in {"issue_link", "reference_issue_link"}
        or (
            is_user_aggregate_page_without_record_id(site.url)
            and site.url not in SITE_RENDERED_PAGE_AUTHORITY_URLS
        )
    )
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
            if site.parser_id in {"caiyuntong_macau", "guangdong_baer_left_half_head"}:
                # These parsers enumerate the complete declared column themselves.
                # None means all its periods, not just the requested boundary.
                candidate_issues = None
            else:
                candidate_issues = candidate_issue_set(documents)
                candidate_issues.update(wanted_issues)
            raw_matches = site_scoped_raw_matches(
                documents,
                candidate_issues,
                site,
                region_issues=wanted_issues,
            )
            # 先只做文档锁定，在「未过滤」的权威文档候选上确定真实方向边界；
            # 锚点/栏目过滤之后若边界发生位移，说明内部记录被顶成边界，必须失败。
            # 例外：专属容器/作者上下文站的多容器页面需先按作者、身份筛选才能唯一
            # 锁定文档，否则同一页面里的广告块会让整站失败，故对这些站沿用过滤优先。
            filter_first = site.url in DEDICATED_RENDERED_SITE_RULES or (
                site.url in DEDICATED_RENDERED_AUTHOR_CONTEXT_URLS
            )
            if filter_first:
                identity_candidates, secondary_reason, rejection_evidence = (
                    apply_secondary_site_scope(raw_matches, site, wanted_issues)
                )
                if secondary_reason is not None:
                    return SiteResult(
                        index, site, [], None, last_script_errors, secondary_reason,
                        debug_sample_from_documents(documents, wanted_issues),
                        rejection_evidence,
                        tuple(raw_matches),
                    )
                document_matches, source_reason = apply_direction_source_scope(
                    identity_candidates, site, documents
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
                        rejection_evidence,
                        tuple(identity_candidates),
                    )
                true_boundary = direction_window(document_matches, site.pick)
                displaced: list[Match] = []
            else:
                document_matches, source_reason = apply_direction_source_scope(
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
                        direction_evidence=tuple(raw_matches),
                    )
                true_boundary = direction_window(document_matches, site.pick)
                identity_candidates, secondary_reason, rejection_evidence = (
                    apply_secondary_site_scope(document_matches, site, wanted_issues)
                )
                if secondary_reason is not None:
                    return SiteResult(
                        index, site, [], None, last_script_errors, secondary_reason,
                        debug_sample_from_documents(documents, wanted_issues),
                        rejection_evidence,
                        tuple(document_matches),
                    )
                surviving = {
                    (match.document_order, match.position, match.issue, match.value)
                    for match in identity_candidates
                }
                displaced = [
                    match
                    for match in true_boundary
                    if (match.document_order, match.position, match.issue, match.value)
                    not in surviving
                ]
            if not true_boundary:
                return SiteResult(
                    index, site, [], None, last_script_errors,
                    f"{site.pick} 方向边界无有效候选",
                    debug_sample_from_documents(documents, wanted_issues),
                )
            if displaced:
                details = "、".join(
                    f"{match.issue}期 {match.value}@位置{match.position}"
                    for match in displaced
                )
                return SiteResult(
                    index, site, [], None, last_script_errors,
                    f"{site.pick} 方向边界候选未通过栏目校验，禁止内部记录顶替边界：{details}",
                    debug_sample_from_documents(documents, wanted_issues),
                    rejection_evidence,
                    tuple(true_boundary),
                )
            # 通用锚点「半头」无法区分栏目：只检查真正落在方向边界上的同期候选，
            # 非边界位置的同期期数不参与边界裁决（项目规则）。
            if has_generic_half_head_anchor(site):
                boundary_candidates = [
                    match
                    for match in identity_candidates
                    if (match.document_order, match.position) in {
                        (item.document_order, item.position) for item in true_boundary
                    }
                ]
                ambiguous = ambiguous_column_issues(
                    boundary_candidates, wanted_issues
                )
                if ambiguous:
                    details = "；".join(
                        f"{issue}期栏目归属不唯一：{','.join(labels)}"
                        for issue, labels in ambiguous.items()
                    )
                    return SiteResult(
                        index,
                        site,
                        [],
                        None,
                        last_script_errors,
                        details,
                        debug_sample_from_documents(documents, wanted_issues),
                        rejection_evidence,
                        tuple(boundary_candidates),
                    )
            # 归属不明一律否决，但只比较「同一开奖状态」的同期候选：这些站点常把
            # 本期未开奖记录（开？？/开0000）与已开奖的历史记录（开虎16）并列写在
            # 同一页，两者不是同一类候选，跨状态比较会把当期值误杀。
            # 该闸只做否决、不参与选取：边界仍由未过滤候选决定，非边界位置的同期
            # 候选不决定选哪个值，只让归属不明的本站本期失败。
            authoritative_orders = {
                match.document_order for match in document_matches
            }
            same_issue_candidates = [
                match
                for match in identity_candidates
                if match.document_order in authoritative_orders
                and match.issue in wanted_issues
            ]
            # 泛化锚点站只剩一条本期候选时，没有同页对照就必须自证栏目归属：
            # 栏目名要在同一权威文档的其他期记录里重现，否则按 fail-closed 判失败。
            if (
                has_generic_half_head_anchor(site)
                and site.parser_id == "strict_half_head"
            ):
                for issue in sorted(wanted_issues):
                    issue_candidates = [
                        match
                        for match in same_issue_candidates
                        if match.issue == issue
                    ]
                    if len(issue_candidates) != 1:
                        continue
                    # 对照池用次级校验之前的同权威文档候选：占位符/系列规则会把其他
                    # 期的记录筛掉，但那仍是页面上真实存在的同类栏目证据。
                    # 代价：本闸因此只负责拦「认不出栏目」「栏目孤例」；整页只剩广告
                    # 的情形仍由锚点、专属正则和同期冲突闸负责，不要把这里当兜底。
                    other_period_matches = [
                        match
                        for match in document_matches
                        if match.document_order in authoritative_orders
                        and match.issue != issue
                    ]
                    reason = single_candidate_verdict(
                        issue_candidates[0], other_period_matches
                    )
                    if reason:
                        return SiteResult(
                            index,
                            site,
                            [],
                            None,
                            last_script_errors,
                            reason,
                            debug_sample_from_documents(documents, wanted_issues),
                            rejection_evidence,
                            tuple(issue_candidates),
                        )
            same_issue_values = same_period_position_conflicts(
                same_issue_candidates, wanted_issues
            )
            if same_issue_values:
                boundary_state = {
                    match.issue: draw_state(match) for match in true_boundary
                }
                gated_values: dict[int, list[str]] = {}
                for issue, values in same_issue_values.items():
                    state = boundary_state.get(issue)
                    same_state_values = {
                        match.value
                        for match in same_issue_candidates
                        if match.issue == issue and draw_state(match) == state
                    }
                    if len(same_state_values) > 1:
                        gated_values[issue] = values
                if gated_values:
                    details = "；".join(
                        f"{issue}期同期候选冲突（权威文档多处同期候选）：{','.join(values)}"
                        for issue, values in gated_values.items()
                    )
                    return SiteResult(
                        index,
                        site,
                        [],
                        None,
                        last_script_errors,
                        details,
                        debug_sample_from_documents(documents, wanted_issues),
                        rejection_evidence,
                        tuple(same_issue_candidates),
                    )
            matches, source_reason = apply_direction_source_scope(
                identity_candidates, site, documents
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
                    rejection_evidence,
                    tuple(identity_candidates),
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
    # 第 4 类（同文档无其他期对照）必须单独统计，不能被混进“其他失败”。
    single_candidate = {
        "栏目不可辨识": sum(
            1 for line in fail_lines[1:] if SINGLE_CANDIDATE_NO_LABEL in line
        ),
        "无其他期对照": sum(
            1 for line in fail_lines[1:] if SINGLE_CANDIDATE_NO_REFERENCE in line
        ),
        "栏目未在其他期出现": sum(
            1 for line in fail_lines[1:] if SINGLE_CANDIDATE_UNSEEN_LABEL in line
        ),
    }
    if any(single_candidate.values()):
        print(
            "单条候选闸："
            + "，".join(
                f"{label} {count} 站"
                for label, count in single_candidate.items()
                if count
            )
        )


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

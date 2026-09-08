# -*- coding: utf-8 -*-
"""Strict original-order selection for top/bottom sites."""

from dataclasses import dataclass

from ..domain.models import Match


@dataclass(frozen=True)
class SelectionDecision:
    matches: list[Match]
    reason: str | None = None
    evidence: tuple[Match, ...] = ()


def _ordered(matches: list[Match]) -> list[Match]:
    return sorted(
        matches,
        key=lambda item: (
            item.document_order,
            item.position,
            item.order,
            item.snippet,
        ),
    )


def direction_window(
    matches: list[Match],
    pick: str,
    wanted_issues: set[int] | None = None,
) -> list[Match]:
    """Return every parse of the single legal record at the declared boundary."""
    ordered = _ordered(matches)
    if pick not in {"top", "bottom"}:
        raise ValueError(f"方向只能是 top/bottom，当前为：{pick}")
    if not ordered:
        return []
    boundary_position = ordered[0].position if pick == "top" else ordered[-1].position
    boundary = [match for match in ordered if match.position == boundary_position]
    if wanted_issues is None:
        return boundary
    return [match for match in boundary if match.issue in wanted_issues]


def _same_source_candidate(left: Match, right: Match) -> bool:
    return (
        left.issue,
        left.value,
        left.document_order,
        left.position,
        left.source_url,
        left.source_kind,
        left.record_id,
        left.record_path,
        left.block_id,
    ) == (
        right.issue,
        right.value,
        right.document_order,
        right.position,
        right.source_url,
        right.source_kind,
        right.record_id,
        right.record_path,
        right.block_id,
    )


def _document_identity(match: Match) -> tuple[object, ...]:
    return (
        match.document_order,
        match.source_url,
        match.source_kind,
        match.record_id,
        match.record_path,
        match.route_type,
        match.url_record_id,
        match.api_url,
    )


def _validated_representatives(
    issue: int, issue_matches: list[Match], pick: str
) -> tuple[list[Match], str | None]:
    unique: list[Match] = []
    for candidate in _ordered(issue_matches):
        if not any(_same_source_candidate(candidate, existing) for existing in unique):
            unique.append(candidate)
    if len({match.value for match in unique}) > 1:
        details = ",".join(
            f"{match.value}@位置{match.position}" for match in unique
        )
        return [], f"{issue}期边界候选冲突：{details}"
    selected = unique[0]
    return [selected], None


def conflicting_issue_values(
    matches: list[Match], wanted_issues: set[int]
) -> dict[int, list[str]]:
    """Detect same-document evidence drift and cross-document value disagreement."""
    candidates: dict[int, list[Match]] = {}
    for match in matches:
        if match.issue in wanted_issues:
            candidates.setdefault(match.issue, []).append(match)
    conflicts: dict[int, list[str]] = {}
    for issue, items in sorted(candidates.items()):
        by_document: dict[tuple[object, ...], list[Match]] = {}
        for item in items:
            by_document.setdefault(_document_identity(item), []).append(item)

        details: list[str] = []
        for document_items in by_document.values():
            values = {item.value for item in document_items}
            if len(values) > 1:
                details.extend(
                    f"{item.value}@顺序{item.order}/位置{item.position}"
                    for item in _ordered(document_items)
                )
        if len({item.value for item in items}) > 1:
            details.extend(
                f"{item.value}@文档{item.document_order}/位置{item.position}"
                for item in sorted(
                    items,
                    key=lambda item: (item.document_order, item.order, item.position),
                )
            )
        if details:
            conflicts[issue] = list(dict.fromkeys(details))
    return conflicts


def select_requested_matches(
    candidates: list[Match],
    wanted_issues: set[int],
    pick: str,
) -> SelectionDecision:
    direction = select_direction_window_matches(candidates, wanted_issues, pick)
    if direction.reason is not None:
        return direction

    clean: list[Match] = []
    for issue in sorted(wanted_issues):
        issue_matches = [match for match in direction.matches if match.issue == issue]
        representatives, reason = _validated_representatives(
            issue, issue_matches, pick
        )
        if reason is not None:
            return SelectionDecision([], reason, direction.evidence)
        clean.append(_ordered(representatives)[0])
    return SelectionDecision(_ordered(clean), evidence=direction.evidence)


def select_direction_window_matches(
    candidates: list[Match],
    wanted_issues: set[int],
    pick: str,
) -> SelectionDecision:
    """Return requested candidates only when they are the direction boundary.

    Callers must apply author, title, column, placeholder, and other validity
    checks first so invalid records never occupy the hard boundary.
    """
    if pick not in {"top", "bottom"}:
        return SelectionDecision([], f"方向无效：{pick}")

    if not candidates:
        label = "、".join(f"{issue}期" for issue in sorted(wanted_issues))
        return SelectionDecision([], f"{pick} 候选内未找到 {label}")
    document_orders = {candidate.document_order for candidate in candidates}
    if len(document_orders) != 1:
        details = "、".join(str(order) for order in sorted(document_orders))
        return SelectionDecision(
            [],
            f"权威文档未唯一确定：文档{details}",
            tuple(_ordered(candidates)),
        )
    invalid_positions = [candidate for candidate in candidates if candidate.position < 0]
    if invalid_positions:
        return SelectionDecision(
            [],
            "权威文档存在无法映射的页面位置",
            tuple(_ordered(candidates)),
        )

    boundary = direction_window(candidates, pick)
    requested = [match for match in boundary if match.issue in wanted_issues]
    missing = sorted(wanted_issues - {match.issue for match in requested})
    if missing:
        label = "、".join(f"{issue}期" for issue in missing)
        actual = "、".join(
            f"{match.issue}期@位置{match.position}"
            for match in boundary
        )
        return SelectionDecision(
            [],
            f"{pick} 边界不是指定期：边界为 {actual}；未找到 {label}",
            tuple(boundary),
        )
    return SelectionDecision(_ordered(requested), evidence=tuple(boundary))

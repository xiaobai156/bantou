from unittest.mock import patch

import pytest

from bantou.application.site_crawl import crawl_site
from bantou.domain import Match, Site
from bantou.outputs import failure_category
from bantou.selection import select_requested_matches


def _match(
    issue: int,
    value: str,
    position: int,
    *,
    order: int | None = None,
    document_order: int = 0,
    snippet: str | None = None,
) -> Match:
    return Match(
        issue=issue,
        issue_text=str(issue),
        value=value,
        snippet=snippet or f"{issue}期 {value}",
        order=position if order is None else order,
        document_order=document_order,
        position=position,
        source_url="https://example.test/plan",
        source_kind="page",
        block_id="plan-block",
        anchor_text="西库规划",
        anchor_position=1,
        rule_id="strict_half_head",
    )


def test_top_accepts_only_first_legal_record():
    candidates = [
        _match(215, "2头单", 10),
        _match(214, "1头双", 20),
        _match(213, "3头单", 30),
    ]

    decision = select_requested_matches(candidates, {215}, "top")

    assert decision.reason is None
    assert [(match.issue, match.value) for match in decision.matches] == [(215, "2头单")]
    assert [(match.issue, match.position) for match in decision.evidence] == [(215, 10)]


def test_top_rejects_target_in_second_record_and_reports_real_boundary():
    candidates = [
        _match(215, "2头单", 10),
        _match(214, "1头双", 20),
        _match(213, "3头单", 30),
    ]

    decision = select_requested_matches(candidates, {214}, "top")

    assert decision.matches == []
    assert decision.reason is not None
    assert "边界" in decision.reason
    assert "214期" in decision.reason
    assert [(match.issue, match.position) for match in decision.evidence] == [(215, 10)]


def test_bottom_accepts_only_last_legal_record():
    candidates = [
        _match(215, "2头单", 10),
        _match(214, "1头双", 20),
        _match(213, "3头单", 30),
    ]

    decision = select_requested_matches(candidates, {213}, "bottom")

    assert decision.reason is None
    assert [(match.issue, match.value) for match in decision.matches] == [(213, "3头单")]
    assert [(match.issue, match.position) for match in decision.evidence] == [(213, 30)]


def test_bottom_rejects_target_in_penultimate_record_and_reports_real_boundary():
    candidates = [
        _match(215, "2头单", 10),
        _match(214, "1头双", 20),
        _match(213, "3头单", 30),
    ]

    decision = select_requested_matches(candidates, {214}, "bottom")

    assert decision.matches == []
    assert decision.reason is not None
    assert "边界" in decision.reason
    assert "214期" in decision.reason
    assert [(match.issue, match.position) for match in decision.evidence] == [(213, 30)]


def test_non_boundary_same_issue_different_value_does_not_conflict():
    candidates = [
        _match(215, "2头单", 10),
        _match(214, "1头双", 20),
        _match(215, "4头单", 30),
    ]

    decision = select_requested_matches(candidates, {215}, "top")

    assert decision.reason is None
    assert [(match.value, match.position) for match in decision.matches] == [("2头单", 10)]


def test_bottom_uses_last_same_issue_value_without_conflicting_with_first():
    candidates = [
        _match(215, "2头单", 10),
        _match(214, "1头双", 20),
        _match(215, "4头单", 30),
    ]

    decision = select_requested_matches(candidates, {215}, "bottom")

    assert decision.reason is None
    assert [(match.value, match.position) for match in decision.matches] == [("4头单", 30)]


def test_boundary_record_with_different_legal_values_conflicts():
    candidates = [
        _match(215, "2头单", 10, order=1),
        _match(215, "4头单", 10, order=2),
        _match(214, "1头双", 20, order=3),
    ]

    decision = select_requested_matches(candidates, {215}, "top")

    assert decision.matches == []
    assert decision.reason is not None
    assert "边界候选冲突" in decision.reason
    assert "2头单" in decision.reason
    assert "4头单" in decision.reason
    assert {match.value for match in decision.evidence} == {"2头单", "4头单"}


def test_same_boundary_display_is_deduplicated():
    candidates = [
        _match(215, "2头单", 10, order=1, snippet="图文展示"),
        _match(215, "2头单", 10, order=2, snippet="图文展示"),
        _match(214, "1头双", 20, order=3),
    ]

    decision = select_requested_matches(candidates, {215}, "top")

    assert decision.reason is None
    assert len(decision.matches) == 1
    assert decision.matches[0].value == "2头单"
    assert decision.matches[0].position == 10


@pytest.mark.parametrize(
    ("candidates", "expected_reason"),
    [
        ([], "未找到"),
        ([_match(215, "2头单", -1)], "无法映射"),
        (
            [
                _match(215, "2头单", 10, document_order=0),
                _match(214, "1头双", 20, document_order=1),
            ],
            "权威文档未唯一确定",
        ),
    ],
)
def test_boundary_selection_preserves_source_safety_gates(candidates, expected_reason):
    decision = select_requested_matches(candidates, {215}, "top")

    assert decision.matches == []
    assert decision.reason is not None
    assert expected_reason in decision.reason


@pytest.mark.parametrize(
    ("reason", "expected_category"),
    [
        ("top 边界不是指定期：边界为 215期@位置10；未找到 214期", "方向越界"),
        ("215期同期候选冲突：2头单@位置10,4头单@位置10", "方向候选冲突"),
        ("215期边界候选冲突：2头单@位置10,4头单@位置10", "方向候选冲突"),
    ],
)
def test_boundary_failures_keep_specific_failure_categories(reason, expected_category):
    assert failure_category(reason) == expected_category


def test_crawl_site_uses_first_xiku_style_215_record_only():
    candidates = [
        _match(215, "2头单", 10),
        _match(214, "1头双", 20),
        _match(213, "3头单", 30),
        _match(224, "0头双", 40),
        _match(215, "4头单", 50),
    ]
    site = Site(
        name="西库规划",
        url="https://example.test/plan",
        pick="top",
        line_no=1,
        parser_id="strict_half_head",
        anchors=("西库规划",),
    )

    with (
        patch(
            "bantou.application.site_crawl._documents_for_requested_issues",
            return_value=(["document"], []),
        ),
        patch(
            "bantou.application.site_crawl.candidate_issue_set",
            return_value={213, 214, 215, 224},
        ),
        patch(
            "bantou.application.site_crawl.site_scoped_raw_matches",
            return_value=candidates,
        ),
        patch(
            "bantou.application.site_crawl.apply_direction_source_scope",
            return_value=(candidates, None),
        ),
        patch(
            "bantou.application.site_crawl.apply_secondary_site_scope",
            return_value=(candidates, None, ()),
        ),
    ):
        result = crawl_site(
            1,
            site,
            {215},
            None,
            ("半头",),
            timeout=1,
            verify_ssl=True,
            retries=0,
            site_timeout=5,
        )

    assert result.error is None
    assert result.miss_reason is None
    assert [(match.issue, match.value, match.position) for match in result.matches] == [
        (215, "2头单", 10)
    ]
    assert [(match.issue, match.position) for match in result.direction_evidence] == [
        (215, 10)
    ]


def test_crawl_site_does_not_search_second_xiku_style_record_for_214():
    candidates = [
        _match(215, "2头单", 10),
        _match(214, "1头双", 20),
        _match(213, "3头单", 30),
        _match(224, "0头双", 40),
        _match(215, "4头单", 50),
    ]
    site = Site(
        name="西库规划",
        url="https://example.test/plan",
        pick="top",
        line_no=1,
        parser_id="strict_half_head",
        anchors=("西库规划",),
    )

    with (
        patch(
            "bantou.application.site_crawl._documents_for_requested_issues",
            return_value=(["document"], []),
        ),
        patch(
            "bantou.application.site_crawl.candidate_issue_set",
            return_value={213, 214, 215, 224},
        ),
        patch(
            "bantou.application.site_crawl.site_scoped_raw_matches",
            return_value=candidates,
        ),
        patch(
            "bantou.application.site_crawl.apply_direction_source_scope",
            return_value=(candidates, None),
        ),
        patch(
            "bantou.application.site_crawl.apply_secondary_site_scope",
            return_value=(candidates, None, ()),
        ),
    ):
        result = crawl_site(
            1,
            site,
            {214},
            None,
            ("半头",),
            timeout=1,
            verify_ssl=True,
            retries=0,
            site_timeout=5,
        )

    assert result.matches == []
    assert result.miss_reason is not None
    assert "边界" in result.miss_reason
    assert [(match.issue, match.position) for match in result.direction_evidence] == [
        (215, 10)
    ]

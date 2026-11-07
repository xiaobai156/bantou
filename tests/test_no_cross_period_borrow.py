# -*- coding: utf-8 -*-
"""跨期/跨栏目借值回归：审查发现的四条通道必须 fail-closed。"""
from __future__ import annotations

from bantou.domain.models import Match, Site
from bantou.parsers.matching import (
    ambiguous_column_issues,
    column_labels,
    has_generic_half_head_anchor,
    same_period_position_conflicts,
)
from bantou.parsers.segments import (
    focused_half_head_block,
    half_head_values_in_segment,
    iter_issue_segments,
)
from bantou.selection.engine import direction_window


def _match(issue: int, value: str, position: int, snippet: str = "") -> Match:
    return Match(
        issue=issue,
        issue_text=str(issue),
        value=value,
        snippet=snippet or f"{issue}期 绝杀半头【{value}】",
        order=position,
        document_order=0,
        position=position,
    )


def test_boundary_uses_unfiltered_candidates_not_filtered_ones():
    """顶部真实边界是 298 期；297 期不能被过滤后的集合顶成边界。"""
    full = [_match(298, "4头单", 100), _match(297, "1头双", 200)]
    assert direction_window(full, "top")[0].issue == 298
    filtered = [item for item in full if item.issue == 297]
    assert direction_window(filtered, "top")[0].issue == 297


def test_generic_anchor_flagged_and_specific_anchor_not():
    generic = Site(name="测试站", url="https://a.test/x.html", pick="top", line_no=1, anchors=("半头",))
    specific = Site(name="测试站", url="https://a.test/x.html", pick="top", line_no=1, anchors=("绝杀半头",))
    assert has_generic_half_head_anchor(generic)
    assert not has_generic_half_head_anchor(specific)


def test_footer_ad_column_shadows_body_and_must_be_rejected():
    """正文 绝杀半头【2头双】 + 页脚广告 秒杀半头【4头单】→ 栏目归属不唯一。"""
    matches = [
        _match(298, "2头双", 100, "298期 绝杀半头【2头双】开00准"),
        _match(298, "4头单", 900, "298期 秒杀半头【4头单】开00准"),
    ]
    ambiguous = ambiguous_column_issues(matches, {298})
    assert 298 in ambiguous
    assert len(ambiguous[298]) == 2


def test_single_column_is_not_reported_as_ambiguous():
    matches = [
        _match(298, "2头双", 100, "298期 绝杀半头【2头双】开00准"),
        _match(297, "1头单", 200, "297期 绝杀半头【1头单】开00准"),
    ]
    assert ambiguous_column_issues(matches, {298, 297}) == {}


def test_previous_period_line_is_not_merged_into_current_record():
    """下一行「上期开3头双」属于上一期开奖信息，不能并入本期字段。"""
    text = "298期 绝杀半头\n上期开3头双 中\n297期 绝杀半头【1头单】开00准"
    for issue, _text, segment, _pos in iter_issue_segments(text, {298}):
        if issue != 298:
            continue
        focused = focused_half_head_block(segment)
        values = half_head_values_in_segment(focused)
        assert "3头双" not in values, f"借到上一期值：{values}"


def test_current_record_value_still_parsed_after_boundary_hardening():
    text = "298期 绝杀半头【2头双】开00准"
    for issue, _text, segment, _pos in iter_issue_segments(text, {298}):
        if issue != 298:
            continue
        assert half_head_values_in_segment(focused_half_head_block(segment)) == ["2头双"]


def test_column_labels_cover_words_outside_any_vocabulary():
    """站方新增栏目（瞬杀/灭杀）不需要改代码也能识别为不同栏目。"""
    assert column_labels("298期 瞬杀半头【4头单】") == {"瞬杀"}
    assert column_labels("298期 灭杀半头【1头单】") == {"灭杀"}
    assert column_labels("298期 绝杀半头【2头双】") == {"绝杀"}


def test_column_labels_allow_decorations_between_modifier_and_half_head():
    """装饰符（㊣/正/★）与解析器共用同一字符集，不能把同一栏目拆成两个标签。"""
    assert column_labels("310期 绝杀㊣半头[3头单]开:鸡46准") == {"绝杀"}
    assert column_labels("310期 秒杀正半头【2头双】") == {"秒杀"}
    assert column_labels("310期 ★必杀★半头【1头单】") == {"必杀"}


def test_decorated_same_column_is_not_ambiguous():
    """带装饰符的同栏目记录：标签相同，不能判成栏目歧义。"""
    matches = [
        _match(298, "2头双", 100, "298期 绝杀㊣半头【2头双】开00准"),
        _match(298, "4头单", 900, "298期 绝杀半头【4头单】开00准"),
    ]
    assert ambiguous_column_issues(matches, {298}) == {}
    assert same_period_position_conflicts(matches, {298}) == {298: ["2头双", "4头单"]}


def test_decorated_different_columns_still_ambiguous():
    """带装饰符的异栏目记录：仍然判栏目归属不唯一，不能因装饰符退化。"""
    matches = [
        _match(298, "2头双", 100, "298期 绝杀㊣半头【2头双】开00准"),
        _match(298, "4头单", 900, "298期 秒杀㊣半头【4头单】开00准"),
    ]
    assert set(ambiguous_column_issues(matches, {298})[298]) == {"绝杀", "秒杀"}


def test_out_of_vocabulary_ad_column_is_rejected():
    """正文 绝杀半头 + 页脚 瞬杀半头（词表外）仍须判归属不唯一。"""
    matches = [
        _match(298, "2头双", 100, "298期 绝杀半头【2头双】开00准"),
        _match(298, "4头单", 900, "298期 瞬杀半头【4头单】开00准"),
    ]
    ambiguous = ambiguous_column_issues(matches, {298})
    assert 298 in ambiguous
    assert set(ambiguous[298]) == {"绝杀", "瞬杀"}


def test_same_column_name_at_two_positions_is_rejected():
    """同名栏目在正文与页脚各写一个不同值时，归属不明必须失败。"""
    matches = [
        _match(298, "2头双", 100, "298期 绝杀半头【2头双】开00准"),
        _match(298, "4头单", 900, "298期 绝杀半头【4头单】开00准"),
    ]
    assert ambiguous_column_issues(matches, {298}) == {}
    conflicts = same_period_position_conflicts(matches, {298})
    assert conflicts == {298: ["2头双", "4头单"]}


def test_same_value_repeated_at_two_positions_is_not_a_conflict():
    """同值重复展示可去重，不算冲突。"""
    matches = [
        _match(298, "2头双", 100, "298期 绝杀半头【2头双】开00准"),
        _match(298, "2头双", 900, "298期 绝杀半头【2头双】开00准"),
    ]
    assert same_period_position_conflicts(matches, {298}) == {}


def test_normal_copy_containing_benqi_is_not_treated_as_previous_period():
    """「当前期开奖」「本期历史准确率」是正常文案，不能触发跨期截断。"""
    from bantou.parsers.segments import _CROSS_PERIOD_LINE_RE

    assert not _CROSS_PERIOD_LINE_RE.search("当前期开奖结果")
    assert not _CROSS_PERIOD_LINE_RE.search("本期历史准确率")
    assert _CROSS_PERIOD_LINE_RE.search("上期开3头双 中")

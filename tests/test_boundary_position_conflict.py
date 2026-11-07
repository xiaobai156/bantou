# -*- coding: utf-8 -*-
"""生产链路回归：页脚/页首的另一条「半头」记录不得顶替真实边界。

与 test_no_cross_period_borrow.py 的区别：这里直接调用 ``crawl_site``，
走的是正式边界裁决顺序（文档锁定 → 未过滤边界 → 栏目过滤 → 位移检测 →
跨位置冲突闸），因此能覆盖「过滤发生在判据之前」这类只在生产链路出现的漏洞。

闸口按开奖状态分组：站点常把「当期未开奖记录（开？？/开0000）」与「已开奖的
历史记录（开虎16）」并列写在同一页，二者不是同一类候选，跨状态比较会误杀当期值。
"""
from __future__ import annotations

from bantou.application import site_crawl as sc
from bantou.domain.models import Site, SourceDocument


def _site(anchors: tuple[str, ...], pick: str, name: str = "测试站") -> Site:
    return Site(
        name=name,
        url="https://audit.test/topic/1.html",
        pick=pick,
        line_no=1,
        parser_id="strict_half_head",
        anchors=anchors,
    )


def _crawl(monkeypatch, site: Site, text: str, issue: int):
    document = SourceDocument(
        text,
        source_url=site.url,
        source_kind="browser-text",
        container_id="audit:rendered",
        document_authority="declared-rendered-page",
        block_start=0,
        block_end=len(text),
    )
    monkeypatch.setattr(
        sc, "_documents_for_requested_issues", lambda *args, **kwargs: ([document], [])
    )
    return sc.crawl_site(1, site, {issue}, None, 20, True, 0)


BODY = "310期 绝杀半头 【2头双】 开：1234 对\n正文其他内容\n"
PENDING_BODY = "310期 绝杀半头 【2头双】 开：？？ 准\n正文其他内容\n"
ARCHIVE = "309期 绝杀半头 【1头单】 开：13 准\n310期 绝杀半头 【4头单】 开：16 准\n"


def _assert_rejected(result) -> None:
    assert not result.matches, f"不应采纳任何值，实际：{[m.value for m in result.matches]}"
    assert result.error or result.miss_reason


def test_footer_other_column_cannot_replace_body_value(monkeypatch):
    """泛化锚点 + 页脚异名栏目（秒杀半头）写另一个值。"""
    result = _crawl(
        monkeypatch,
        _site(("半头",), "bottom"),
        BODY + "310期 秒杀半头 【4头单】 开：1234 对\n",
        310,
    )
    _assert_rejected(result)
    assert "同期候选冲突" in (result.error or result.miss_reason)


def test_footer_same_column_cannot_replace_body_value(monkeypatch):
    """专属锚点 + 页脚同名栏目写另一个值（此前只对异名有防御）。"""
    result = _crawl(
        monkeypatch,
        _site(("绝杀半头",), "bottom"),
        BODY + "310期 绝杀半头 【4头单】 开：1234 对\n",
        310,
    )
    _assert_rejected(result)
    assert "同期候选冲突" in (result.error or result.miss_reason)


def test_header_record_cannot_replace_body_value(monkeypatch):
    """top 方向：页首记录写另一个值。"""
    result = _crawl(
        monkeypatch,
        _site(("半头",), "top"),
        "310期 秒杀半头 【4头单】 开：1234 对\n" + BODY,
        310,
    )
    _assert_rejected(result)
    assert "同期候选冲突" in (result.error or result.miss_reason)


def test_plain_half_head_footer_cannot_replace_body_value(monkeypatch):
    """页脚只写「半头」、没有栏目修饰词时同样不能顶替。"""
    result = _crawl(
        monkeypatch,
        _site(("半头",), "bottom"),
        BODY + "310期 半头 【4头单】 开：1234 对\n",
        310,
    )
    _assert_rejected(result)
    assert "同期候选冲突" in (result.error or result.miss_reason)


def test_two_pending_records_with_different_values_are_rejected(monkeypatch):
    """当期未开奖（开？？）两条候选写出不同值：同状态冲突，必须失败。"""
    result = _crawl(
        monkeypatch,
        _site(("半头",), "bottom"),
        PENDING_BODY + "310期 绝杀半头 【4头单】 开：？？ 准\n",
        310,
    )
    _assert_rejected(result)
    assert "同期候选冲突" in (result.error or result.miss_reason)


def test_drawn_archive_record_does_not_veto_pending_current_record(monkeypatch):
    """当期未开奖记录 + 已开奖历史记录并存：仍取当期记录，不误杀。"""
    result = _crawl(
        monkeypatch,
        _site(("半头",), "top"),
        PENDING_BODY + ARCHIVE,
        310,
    )
    assert [match.value for match in result.matches] == ["2头双"]
    assert result.error is None and result.miss_reason is None


def test_settled_record_with_drawn_archive_conflict_is_rejected(monkeypatch):
    """已开奖的当期候选与已开奖历史值同状态冲突：归属不明，必须失败。"""
    result = _crawl(
        monkeypatch,
        _site(("半头",), "top"),
        BODY + ARCHIVE,
        310,
    )
    _assert_rejected(result)
    assert "同期候选冲突" in (result.error or result.miss_reason)


def test_same_value_at_two_positions_is_still_accepted(monkeypatch):
    """同一期在不同位置重复展示同一个值：允许去重，不能误杀。"""
    result = _crawl(
        monkeypatch,
        _site(("半头",), "bottom"),
        BODY + "310期 绝杀半头 【2头双】 开：1234 对\n",
        310,
    )
    assert [match.value for match in result.matches] == ["2头双"]
    assert result.error is None and result.miss_reason is None


def test_single_candidate_without_other_periods_fails_closed(monkeypatch):
    """第 4 类：单条候选且同文档没有其他期记录可对照 → fail-closed 失败。"""
    result = _crawl(monkeypatch, _site(("半头",), "bottom"), BODY, 310)
    _assert_rejected(result)
    assert sc.SINGLE_CANDIDATE_NO_REFERENCE in (result.error or result.miss_reason)


def test_single_candidate_with_label_seen_elsewhere_passes(monkeypatch):
    """第 1 类：单条候选，但栏目名在同文档另一期记录里重现 → 通过。"""
    result = _crawl(
        monkeypatch,
        _site(("半头",), "top"),
        "310期 必杀半头 【2头双】 开：1234 对\n"
        "309期 必杀半头 【1头单】 开：13 对\n",
        310,
    )
    assert [match.value for match in result.matches] == ["2头双"]


def test_single_candidate_with_unseen_label_fails(monkeypatch):
    """第 2 类：单条候选，栏目名在同文档其他期从未出现 → 失败。"""
    result = _crawl(
        monkeypatch,
        _site(("半头",), "top"),
        "310期 必杀半头 【2头双】 开：1234 对\n"
        "309期 秒杀半头 【1头单】 开：13 对\n",
        310,
    )
    _assert_rejected(result)
    assert sc.SINGLE_CANDIDATE_UNSEEN_LABEL in (result.error or result.miss_reason)


def test_single_candidate_without_label_fails(monkeypatch):
    """第 3 类：裸「半头」提不出栏目名 → 失败。"""
    result = _crawl(
        monkeypatch,
        _site(("半头",), "top"),
        "310期 半头 【2头双】 开：1234 对\n"
        "309期 必杀半头 【1头单】 开：13 对\n",
        310,
    )
    _assert_rejected(result)
    assert sc.SINGLE_CANDIDATE_NO_LABEL in (result.error or result.miss_reason)


def test_non_generic_anchor_site_is_not_affected(monkeypatch):
    """专属锚点站不适用单条候选闸：单条记录照常通过。"""
    result = _crawl(monkeypatch, _site(("绝杀半头",), "bottom"), BODY, 310)
    assert [match.value for match in result.matches] == ["2头双"]


def test_traditional_kai_placeholder_counts_as_pending(monkeypatch):
    """繁体「開:0000」同样是未开奖占位，不能被当成已开奖历史。"""
    result = _crawl(
        monkeypatch,
        _site(("半头",), "top"),
        "310期 绝杀半头 【4头单】 開:0000准\n"
        "309期 绝杀半头 【1头单】 開:13准\n"
        "310期 绝杀半头 【1头单】 開:16准\n",
        310,
    )
    assert [match.value for match in result.matches] == ["4头单"]


def test_placeholder_filtered_other_periods_still_count_as_reference(monkeypatch):
    """对照池在次级过滤之前：被占位符规则筛掉的其他期记录仍可作栏目证据。"""
    site = Site(
        name="测试站",
        url="https://kjkkzzg.eiu7u-3edk2-gjzmrl.xyz:16677/topic/446873.html",
        pick="top",
        line_no=1,
        parser_id="strict_half_head",
        anchors=("半头",),
    )
    result = _crawl(
        monkeypatch,
        site,
        "310期:必杀半头[0头单]？00对\n309期:必杀半头[1头双]猴23对\n",
        310,
    )
    assert [match.value for match in result.matches] == ["0头单"]


def test_other_period_at_boundary_still_fails_as_before(monkeypatch):
    """页脚写的是别的期：保持原有失败口径，不能被新闸改写成成功。"""
    result = _crawl(
        monkeypatch,
        _site(("半头",), "bottom"),
        BODY + "309期 绝杀半头 【4头单】 开：1234 对\n",
        310,
    )
    _assert_rejected(result)
    assert "边界不是指定期" in (result.error or result.miss_reason)

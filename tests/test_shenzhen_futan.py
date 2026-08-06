import json

import pytest

from bantou.config.sites import parse_json_sites
from bantou.domain import Site, SourceDocument
from bantou.parsers import (
    apply_secondary_site_scope,
    shenzhen_futan_matches,
    site_scoped_raw_matches,
)
from bantou.selection import select_requested_matches


URL = "https://128.241.252.220:9201/tz/bbsjs/080.html"
SITE = Site(
    name="深圳福坛",
    url=URL,
    pick="bottom",
    line_no=1,
    parser_id="shenzhen_futan_half_head",
    anchors=("深圳福坛", "绝杀半头"),
)


def _document(
    *,
    duplicate_target_table: bool = False,
    extra_table_in_target_section: bool = False,
) -> SourceDocument:
    target = """
    <div class="pb-head xxnr-head">
      <div class="pb-tit xxnr-tit">深圳福坛【绝杀半头】</div>
    </div>
    <div class="pb-content xxnr-content">
      <table class="ta1"><tbody>
        <tr><td><pre>214期:<font>绝杀半头</font>开:15准<br>【3头单】</pre></td></tr>
        <tr><td><pre>215期:<font>绝杀半头</font>开:21对<br>【1头单】</pre></td></tr>
        <tr><td><pre>216期:<font>绝杀半头</font>开:00准<br>【0头单】</pre></td></tr>
      </tbody></table>
    </div>
    """
    duplicate = target.replace("216期", "217期").replace("0头单", "2头双")
    extra_table = "<table><tr><td><pre>217期:绝杀半头【2头双】</pre></td></tr></table>"
    html = f"""
    <html><body>
      <div class="pb-tit xxnr-tit">其他栏目【绝杀半头】</div>
      <table><tr><td><pre>216期:绝杀半头【4头双】</pre></td></tr></table>
      {target}
      {extra_table if extra_table_in_target_section else ""}
      {duplicate if duplicate_target_table else ""}
      <div class="pb-tit xxnr-tit">深圳福坛【美女图】刷新继续看</div>
      <table><tr><td><pre>218期:绝杀半头【3头双】</pre></td></tr></table>
    </body></html>
    """
    return SourceDocument(
        html,
        source_url=URL,
        source_kind="page",
        container_id="primary-page",
        document_authority="primary",
    )


def test_parser_locks_to_shenzhen_futan_target_table_and_preserves_evidence():
    matches = shenzhen_futan_matches([_document()], {214, 215, 216, 218})

    assert [(match.issue, match.value) for match in matches] == [
        (214, "3头单"),
        (215, "1头单"),
        (216, "0头单"),
    ]
    assert all(match.source_url == URL for match in matches)
    assert all(match.anchor_text == "深圳福坛【绝杀半头】" for match in matches)
    assert all(match.anchor_position >= 0 for match in matches)
    assert len({match.block_id for match in matches}) == 1
    assert all(match.table_column == "target-table:0" for match in matches)
    assert all(match.rule_id == "shenzhen_futan_half_head" for match in matches)
    assert [match.position for match in matches] == sorted(match.position for match in matches)
    assert matches[0].anchor_position == str(_document()).find("深圳福坛【绝杀半头】")


def test_filtered_match_keeps_its_true_row_order_inside_target_table():
    matches = shenzhen_futan_matches([_document()], {216})

    assert len(matches) == 1
    assert matches[0].order == 3


def test_bottom_accepts_only_last_valid_target_table_record():
    document = _document()
    raw = site_scoped_raw_matches([document], {214, 215, 216, 218}, SITE, ("半头",))
    scoped, reason, rejected = apply_secondary_site_scope(raw, SITE, {216})
    decision = select_requested_matches(scoped, {216}, SITE.pick)

    assert reason is None
    assert rejected == ()
    assert decision.reason is None
    assert [(match.issue, match.value) for match in decision.matches] == [(216, "0头单")]


def test_bottom_rejects_215_even_though_it_exists_in_target_table():
    raw = site_scoped_raw_matches([_document()], {214, 215, 216}, SITE, ("半头",))
    scoped, reason, _ = apply_secondary_site_scope(raw, SITE, {215})
    decision = select_requested_matches(scoped, {215}, SITE.pick)

    assert reason is None
    assert decision.matches == []
    assert decision.reason is not None
    assert "bottom 边界不是指定期" in decision.reason
    assert "216期" in decision.reason


def test_parser_rejects_ambiguous_duplicate_target_tables():
    matches = shenzhen_futan_matches(
        [_document(duplicate_target_table=True)],
        {214, 215, 216, 217},
    )

    assert matches == []


def test_parser_rejects_second_table_inside_same_target_title_section():
    matches = shenzhen_futan_matches(
        [_document(extra_table_in_target_section=True)],
        {214, 215, 216, 217},
    )

    assert matches == []


def test_dedicated_parser_cannot_be_declared_for_another_url():
    config = json.dumps(
        [
            {
                "name": "伪深圳福坛",
                "url": "https://example.test/not-shenzhen.html",
                "pick": "bottom",
                "parser": "shenzhen_futan_half_head",
                "anchors": ["深圳福坛", "绝杀半头"],
            }
        ],
        ensure_ascii=False,
    )

    with pytest.raises(ValueError, match="解析器与专属 URL 不匹配"):
        parse_json_sites(config, "test.json")

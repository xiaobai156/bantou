"""Bounded scans must retain every candidate and its original evidence."""
from dataclasses import replace
from unittest.mock import Mock

import pytest

from bantou.application import site_crawl
from bantou.domain.models import Site, SourceDocument
from bantou.parsers import matching
from bantou.site_profiles import registry
from bantou.text import issue_token_positions, normalize_text, source_position_lookup


def test_repeated_records_index_source_once(monkeypatch):
    site = Site("A", "https://example.test/a", "top", 1, "strict_half_head", ("半头",))
    row = "264期 必杀半头【2头双】开00对\n"
    document = SourceDocument(row * 40, source_url=site.url, source_kind="browser-text")
    scan = Mock(wraps=matching.source_issue_token_positions)
    monkeypatch.setattr(matching, "source_issue_token_positions", scan)
    matches = matching.find_matches([document], {264}, site)
    assert [(m.issue, m.value, m.position) for m in matches] == [
        (264, "2头双", i * len(row)) for i in range(40)
    ]
    assert scan.call_count == 1


def scoped_document(parser, first="264", value="2头双"):
    if parser == "caiyuntong_macau":
        return (
            "彩运通 澳门综合杀<div id='con_jihuadanshuang50000aloa_1'><table>"
            f"<tr><td>{first}期</td><td>肖</td><td>尾</td><td>{value}</td></tr>"
            "<tr><td>263期</td><td>肖</td><td>尾</td><td>1头单</td></tr>"
            "</table></div><div id='con_jihuadanshuang50000aloa_2'></div>"
        )
    return (
        "广东八二『半波半头』<div class='dz_content08'><table><tr><td>"
        f"{first}期 杀【{value}】开00对<br>263期 杀【1头单】开00对"
        "</td><td>264期 杀【4头双】开00对</td></tr></table></div>『其他栏目』"
    )


@pytest.mark.parametrize("parser,url", [
    ("caiyuntong_macau", registry.CAIYUNTONG_URL),
    ("guangdong_baer_left_half_head", registry.GUANGDONG_BAER_URL),
])
def test_dedicated_parsers_skip_generic_scan_but_keep_direction(monkeypatch, parser, url):
    site = Site("A", url, "top", 1, parser, ("半头",))
    document = SourceDocument(scoped_document(parser), source_url=url, source_kind="browser")
    monkeypatch.setattr(site_crawl, "_documents_for_requested_issues", lambda *a: ([document], []))
    generic_scan = Mock(side_effect=AssertionError("dedicated parser scanned unrelated tables"))
    monkeypatch.setattr(site_crawl, "candidate_issue_set", generic_scan)
    result = site_crawl.crawl_site(1, site, {264}, None, 5, True, 0)
    assert [(m.issue, m.value) for m in result.matches] == [(264, "2头双")]
    for issue in (263, 265):
        rejected = site_crawl.crawl_site(1, site, {issue}, None, 5, True, 0)
        assert not rejected.matches
        assert "边界不是指定期" in rejected.miss_reason
    bottom = site_crawl.crawl_site(1, replace(site, pick="bottom"), {263}, None, 5, True, 0)
    assert [(m.issue, m.value) for m in bottom.matches] == [(263, "1头单")]
    generic_scan.assert_not_called()


@pytest.mark.parametrize("parser,url", [
    ("caiyuntong_macau", registry.CAIYUNTONG_URL),
    ("guangdong_baer_left_half_head", registry.GUANGDONG_BAER_URL),
])
@pytest.mark.parametrize("case", ["wrong_column", "ambiguous_browser_sources", "multiple_values"])
def test_dedicated_all_period_scan_still_rejects_bad_evidence(monkeypatch, parser, url, case):
    site = Site("A", url, "top", 1, parser, ("半头",))
    html = scoped_document(parser)
    if case == "wrong_column":
        html = html.replace("澳门综合杀", "其他栏目").replace("『半波半头』", "『其他栏目』")
    elif case == "multiple_values":
        html = scoped_document(parser, value="2头双 3头单")
    # The collector retains the HTTP shell before the declared browser source.
    documents = [SourceDocument("<html></html>", source_url=url, source_kind="page"),
                 SourceDocument(html, source_url=url, source_kind="browser")]
    if case == "ambiguous_browser_sources":
        documents.append(SourceDocument(scoped_document(parser, value="3头双"),
                                        source_url=url, source_kind="browser"))
    monkeypatch.setattr(site_crawl, "_documents_for_requested_issues", lambda *a: (documents, []))
    result = site_crawl.crawl_site(1, site, {264}, None, 5, True, 0)
    assert not result.matches
    assert result.miss_reason
    if case == "ambiguous_browser_sources":
        assert "权威文档未唯一确定" in result.miss_reason


def test_bounded_token_scan_keeps_absolute_offsets_and_digit_boundary():
    text = "前缀1264期--２６４&nbsp;期--264期"
    assert issue_token_positions(text, "264", start=3) == [9, 21]
    assert issue_token_positions(text, "264", start=9, end=21) == [9]


def test_position_lookup_keeps_value_occurrence_and_document_isolation():
    raw = "<script>264期 4头双</script><div title='264期'>２６４期 半头2头双</div><p>264期 半头1头单</p>"
    searched = "264期 半头2头双\n264期 半头1头单"
    lookup = source_position_lookup(raw, searched)
    assert lookup("264", "2头双")[0] == raw.index("２６４期")
    assert lookup("264", "1头单")[searched.index("264期", 1)] == raw.rindex("264期")
    assert lookup("264", "4头双") == {}
    other = SourceDocument("264期 半头4头双", source_kind="browser-text")
    assert source_position_lookup(other, normalize_text(other))("264", "2头双") == {}


@pytest.mark.parametrize('url,name', [
    ('https://dh81163.2cv5a08j69.cyou/PrZpSoLrkj.html', '孟婆大人'),
    ('https://dh81163.xx947zqiqi.cyou/duiijLEuEl.html', '星宇股份'),
])
def test_anti_bot_sites_wait_for_identity_and_content_instead_of_all_scripts(url, name):
    assert registry.SITE_BROWSER_HTML_WAIT_UNTIL[url] == 'commit'
    assert set(registry.SITE_BROWSER_READY_TERMS[url]) == {name, '半头'}

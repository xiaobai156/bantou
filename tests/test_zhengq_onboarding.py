from bantou.documents.content import extract_dedicated_rendered_documents
from bantou.domain.models import Site
from bantou.fetching.transport import FetchedText
from bantou.parsers.matching import (
    apply_direction_source_scope,
    apply_secondary_site_scope,
    site_scoped_raw_matches,
)
from bantou.selection.engine import conflicting_issue_values, select_direction_window_matches


URL = "https://zouibdh.6c8rw-eic61-abilpw.work:17477/topic/256298.html"
SITE = Site("争奇斗异", URL, "bottom", 1, "strict_half_head", ("绝杀特码半头",))


def candidates(author="争奇斗异", rows="269期:绝杀特码半头【2头双数】开00准\n270期:绝杀特码半头【1头单数】开0000准", title="澳门百事通【绝杀特码半头】", final_url=URL):
    html = (
        "<h1>" + title + "</h1><div class='author'>" + author + " 发表于 09月27日</div>"
        "<div class='content'>" + rows + "</div>"
    )
    documents = extract_dedicated_rendered_documents(FetchedText(html, URL, final_url), SITE, {270}, direction_first=True)
    raw = site_scoped_raw_matches(documents, {269, 270, 271}, SITE)
    scoped, reason, _ = apply_secondary_site_scope(raw, SITE, {270})
    if reason:
        return [], reason
    return apply_direction_source_scope(scoped, SITE, documents)


def test_zhengq_bottom_270_and_neighbor_boundary():
    matches, reason = candidates()
    assert reason is None
    result = select_direction_window_matches(matches, {270}, "bottom")
    assert result.reason is None
    assert [(m.issue, m.value, m.author, m.source_url) for m in result.matches] == [
        (270, "1头单", "争奇斗异 发表于 09月27日", URL)
    ]
    assert "边界不是指定期" in select_direction_window_matches(matches, {269}, "bottom").reason
    assert "边界不是指定期" in select_direction_window_matches(matches, {271}, "bottom").reason


def test_zhengq_rejects_wrong_author_or_column():
    assert "作者不匹配" in candidates(author="其他作者")[1]
    assert "无有效结果" in candidates(rows="270期:必杀半头【1头单数】开0000准")[1]


def test_zhengq_rejects_wrong_article_identity():
    import pytest

    with pytest.raises(ValueError, match="页面身份未匹配"):
        candidates(title="其他栏目")
    with pytest.raises(ValueError, match="文章 URL"):
        candidates(final_url=URL.replace("256298", "123456"))


def test_zhengq_same_issue_conflict_is_not_silenced():
    matches, reason = candidates(rows="270期:绝杀特码半头【1头单数】开0000准 2头双")
    assert reason is None
    assert {match.value for match in matches} == {"1头单", "2头双"}
    assert 270 in conflicting_issue_values(matches, {270})

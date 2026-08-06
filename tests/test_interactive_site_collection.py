import pytest

from bantou.documents import collection
from bantou.domain import Site, SourceDocument
from bantou.parsers.dedicated import wuzhuanxingyi_matches
from bantou.fetching.transport import _click_interactive_card


BABA_FORUM_URL = "https://43666.886677a.app:2563/htm/bbs/top080.html"
WUZHUANXINGYI_URL = "https://ocnrhq.du156-vb27w-tmhsed.xyz:16677/"


def _site(name: str, url: str, pick: str, parser_id: str) -> Site:
    return Site(
        name=name,
        url=url,
        pick=pick,
        line_no=1,
        parser_id=parser_id,
        anchors=("半头",),
    )


def test_baba_forum_collects_iframe_instead_of_empty_rendered_text(monkeypatch):
    site = _site("把把论坛", BABA_FORUM_URL, "bottom", "strict_half_head")
    calls = []

    def fake_collect(url, timeout, verify_ssl, *, deadline=None):
        calls.append(url)
        return [
            SourceDocument(
                "213期: 瞬杀半头 开:猴35中 [1头单]",
                source_url="https://43666.886677a.app:2563/main/bbs/080.html",
                source_kind="iframe",
            )
        ], []

    def unexpected_render(*_args, **_kwargs):
        raise AssertionError("把把论坛不应再读取空的 browser-text")

    monkeypatch.setattr(collection, "collect_documents", fake_collect)
    monkeypatch.setattr(collection, "fetch_rendered_text", unexpected_render)

    documents, errors = collection.collect_site_documents(
        site, site.url, {213}, 20, True
    )

    assert calls == [site.url]
    assert errors == []
    assert documents[0].source_kind == "iframe"


def test_wuzhuanxingyi_collects_expanded_card_document(monkeypatch):
    site = _site("星移物换", WUZHUANXINGYI_URL, "top", "wuzhuanxingyi_embedded")
    expanded_html = """
    <div class="title_container">
        213期: 白蛇传【绝杀半头】→星移物换
      <div class="textriow">
        213期: 【绝杀半头】 【4头单】 开0000准
        213期: 【绝杀半头】 【4头单】 开0000准
      </div>
    </div>
    """

    monkeypatch.setattr(
        collection,
        "fetch_interactive_rendered_html",
        lambda url, timeout, verify_ssl, issue, site_name, *, deadline=None, wait_until="load": expanded_html,
        raising=False,
    )
    monkeypatch.setattr(
        collection,
        "collect_documents",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("星移物换应走展开卡片获取")
        ),
    )

    documents, errors = collection.collect_site_documents(
        site, site.url, {213}, 20, True
    )
    matches = wuzhuanxingyi_matches(documents, {213})

    assert errors == []
    assert documents[0].source_kind == "browser-interactive"
    assert [(match.issue, match.value) for match in matches] == [(213, "4头单")]


class _FakeLocator:
    def __init__(self, count: int):
        self._count = count
        self.clicked = False

    def count(self):
        return self._count

    def click(self):
        self.clicked = True


class _FakePage:
    def __init__(self, count: int):
        self.locator = _FakeLocator(count)
        self.requested_text = None
        self.waited = False

    def get_by_text(self, text, *, exact):
        self.requested_text = (text, exact)
        return self.locator

    def wait_for_function(self, *_args, **_kwargs):
        self.waited = True


def test_interactive_card_click_requires_one_exact_target():
    page = _FakePage(1)

    _click_interactive_card(page, 213, "星移物换", timeout=20)

    assert page.requested_text == (
        "213期: 白蛇传【绝杀半头】→星移物换",
        True,
    )
    assert page.locator.clicked is True
    assert page.waited is True


def test_interactive_card_click_rejects_ambiguous_targets():
    with pytest.raises(ValueError, match="唯一"):
        _click_interactive_card(_FakePage(2), 213, "星移物换", timeout=20)

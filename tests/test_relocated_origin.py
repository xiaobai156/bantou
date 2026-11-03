"""换址跟随的单元测试：只验证判定函数，不联网、不启动 Chromium。"""
from bantou.fetching.browser_process import (
    GATE_BUTTON_TEXTS,
    _relocated_identity_ok,
)


def test_same_article_path_on_rotated_domain_is_accepted():
    requested = "https://jogavu.6bl6s-ilo1w-yfnvvl.work:16677/topic/678626.html"
    landed = "https://solnxusu.3e3ux-nfe96-ktnvgy.cyou:17466/topic/678626.html"
    assert _relocated_identity_ok(requested, landed)


def test_root_entry_page_allows_domain_rotation():
    requested = "https://pvxiftuf.yumkw-u4s81-hpytyz.work:16677/"
    landed = "https://scgufrwx.1vk5h-cwdg6-mtflir.work:17477/#dq"
    assert _relocated_identity_ok(requested, landed)


def test_changed_article_id_is_rejected():
    requested = "https://jogavu.6bl6s-ilo1w-yfnvvl.work:16677/topic/678626.html"
    landed = "https://solnxusu.3e3ux-nfe96-ktnvgy.cyou:17466/topic/999999.html"
    assert not _relocated_identity_ok(requested, landed)


def test_root_landing_is_rejected_when_article_path_required():
    requested = "https://jogavu.6bl6s-ilo1w-yfnvvl.work:16677/topic/678626.html"
    landed = "https://solnxusu.3e3ux-nfe96-ktnvgy.cyou:17466/"
    assert not _relocated_identity_ok(requested, landed)


def test_gate_button_texts_cover_observed_security_page():
    assert "立即进入" in GATE_BUTTON_TEXTS

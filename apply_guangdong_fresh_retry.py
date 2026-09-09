from pathlib import Path


collection = Path("bantou/documents/collection.py")
text = collection.read_text(encoding="utf-8")

if "GUANGDONG_BAER_URL," not in text:
    text = text.replace(
        "    BABA_FORUM_URL,\n",
        "    BABA_FORUM_URL,\n    GUANGDONG_BAER_URL,\n",
        1,
    )

if "from ..text import html_to_text, normalize_text" not in text:
    text = text.replace(
        "from ..text import normalize_text\n",
        "from ..text import html_to_text, normalize_text\n",
        1,
    )

if "def _guangdong_render_has_region(" not in text:
    anchor = "\ndef collect_dynamic_api_documents(\n"
    if anchor not in text:
        raise RuntimeError("collect_dynamic_api_documents anchor not found")
    helper = '''\n\ndef _guangdong_render_has_region(rendered_html: str) -> bool:\n    \"\"\"Check render completeness only; never parse the business value here.\"\"\"\n    visible = normalize_text(html_to_text(str(rendered_html)))\n    return \"半波半头\" in visible\n\n\ndef _fetch_browser_html_for_site(\n    url: str,\n    timeout: int,\n    verify_ssl: bool,\n    *,\n    deadline: float | None = None,\n) -> str:\n    wait_until = SITE_BROWSER_HTML_WAIT_UNTIL.get(url, \"networkidle\")\n    rendered_html = fetch_rendered_html(\n        url,\n        timeout,\n        verify_ssl,\n        deadline=deadline,\n        wait_until=wait_until,\n    )\n    if url == GUANGDONG_BAER_URL and not _guangdong_render_has_region(rendered_html):\n        # The SPA can intermittently expose only its shell under concurrent\n        # browser load. A different wait key forces exactly one fresh render\n        # of the same authoritative URL. Parser/direction rules remain unchanged.\n        rendered_html = fetch_rendered_html(\n            url,\n            timeout,\n            verify_ssl,\n            deadline=deadline,\n            wait_until=\"load\",\n        )\n        if not _guangdong_render_has_region(rendered_html):\n            raise ValueError(\"广东八二渲染正文未出现半波半头区域\")\n    return rendered_html\n'''
    text = text.replace(anchor, helper + anchor, 1)

old = '''    if url in SITE_BROWSER_HTML_URLS:\n        try:\n            rendered_html = fetch_rendered_html(\n                url,\n                timeout,\n                verify_ssl,\n                deadline=deadline,\n                wait_until=SITE_BROWSER_HTML_WAIT_UNTIL.get(url, \"networkidle\"),\n            )\n'''
new = '''    if url in SITE_BROWSER_HTML_URLS:\n        try:\n            rendered_html = _fetch_browser_html_for_site(\n                url, timeout, verify_ssl, deadline=deadline\n            )\n'''
if old in text:
    text = text.replace(old, new, 1)
elif "rendered_html = _fetch_browser_html_for_site(" not in text:
    raise RuntimeError("SITE_BROWSER_HTML_URLS render branch not found")

collection.write_text(text, encoding="utf-8", newline="\n")


test_path = Path("tests/test_issue252_failed_repairs.py")
tests = test_path.read_text(encoding="utf-8")
# Remove a previous draft of these tests if the helper is ever re-applied.
marker = "\ndef test_guangdong_render_completeness_gate_requires_target_region():"
if marker in tests:
    tests = tests[: tests.index(marker)].rstrip() + "\n"

addition = r'''


def test_guangdong_render_region_gate_requires_declared_region():
    from bantou.documents.collection import _guangdong_render_has_region

    assert not _guangdong_render_has_region(
        "<html><body>澳门广东八二站</body></html>"
    )
    assert _guangdong_render_has_region(
        "<html><body>『半波半头』 252期 杀[1头双]开00准</body></html>"
    )


def test_guangdong_shell_gets_one_fresh_same_url_render(monkeypatch):
    from bantou.documents import collection
    from bantou.site_profiles.registry import GUANGDONG_BAER_URL

    calls = []

    def render(url, timeout, verify_ssl, *, deadline=None, wait_until="networkidle"):
        calls.append((url, wait_until))
        if len(calls) == 1:
            return "<html><body>澳门广东八二站</body></html>"
        return "<html><body>『半波半头』 252期 杀[1头双]开00准</body></html>"

    monkeypatch.setattr(collection, "fetch_rendered_html", render)
    rendered = collection._fetch_browser_html_for_site(
        GUANGDONG_BAER_URL, 20, True
    )

    assert "252期" in rendered
    assert [wait for _url, wait in calls] == ["domcontentloaded", "load"]
    assert all(url == GUANGDONG_BAER_URL for url, _wait in calls)


def test_guangdong_second_shell_still_fails(monkeypatch):
    import pytest
    from bantou.documents import collection
    from bantou.site_profiles.registry import GUANGDONG_BAER_URL

    calls = []

    def render(url, timeout, verify_ssl, *, deadline=None, wait_until="networkidle"):
        calls.append(wait_until)
        return "<html><body>澳门广东八二站</body></html>"

    monkeypatch.setattr(collection, "fetch_rendered_html", render)
    with pytest.raises(ValueError, match="渲染正文未出现半波半头区域"):
        collection._fetch_browser_html_for_site(
            GUANGDONG_BAER_URL, 20, True
        )
    assert calls == ["domcontentloaded", "load"]
'''
test_path.write_text(tests.rstrip() + addition + "\n", encoding="utf-8", newline="\n")

print("Applied Guangdong Baer same-source fresh render retry.")

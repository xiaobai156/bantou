from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one replacement, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


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

helper_marker = "def _guangdong_render_has_target("
if helper_marker not in text:
    anchor = "\ndef collect_site_documents(\n"
    if anchor not in text:
        raise RuntimeError("collect_site_documents anchor not found")
    helper = '''\n\ndef _guangdong_render_has_target(\n    rendered_html: str, wanted_issues: set[int] | None\n) -> bool:\n    \"\"\"Check only that Guangdong Baer rendered its declared target region.\n\n    This is a render-completeness gate, not a value parser.  The dedicated\n    left-half-head parser still decides the business value and conflicts.\n    \"\"\"\n    visible = normalize_text(html_to_text(str(rendered_html)))\n    if \"半波半头\" not in visible:\n        return False\n    if not wanted_issues:\n        return True\n    return all(\n        re.search(rf\"(?<!\\d){issue}\\s*期(?!\\d)\", visible) is not None\n        for issue in wanted_issues\n    )\n'''
    text = text.replace(anchor, helper + anchor, 1)

old_branch = '''    if fetch_url == site.url and site.url in DEDICATED_RENDERED_SITE_RULES:\n        rendered_html = fetch_rendered_html(\n            fetch_url,\n            timeout,\n            verify_ssl,\n            deadline=deadline,\n            wait_until=SITE_BROWSER_HTML_WAIT_UNTIL.get(site.url, \"networkidle\"),\n        )\n        return extract_dedicated_rendered_documents(\n            rendered_html, site, wanted_issues, direction_first=True\n        ), []\n'''
new_branch = '''    if fetch_url == site.url and site.url in DEDICATED_RENDERED_SITE_RULES:\n        wait_until = SITE_BROWSER_HTML_WAIT_UNTIL.get(site.url, \"networkidle\")\n        rendered_html = fetch_rendered_html(\n            fetch_url,\n            timeout,\n            verify_ssl,\n            deadline=deadline,\n            wait_until=wait_until,\n        )\n        if (\n            site.url == GUANGDONG_BAER_URL\n            and not _guangdong_render_has_target(rendered_html, wanted_issues)\n        ):\n            # This SPA occasionally returns only its page shell under concurrent\n            # browser load.  A different wait key forces one fresh same-URL\n            # render; it never changes source, direction or parser rules.\n            rendered_html = fetch_rendered_html(\n                fetch_url,\n                timeout,\n                verify_ssl,\n                deadline=deadline,\n                wait_until=\"load\",\n            )\n            if not _guangdong_render_has_target(rendered_html, wanted_issues):\n                raise ValueError(\n                    \"广东八二渲染正文未出现目标期半波半头内容\"\n                )\n        return extract_dedicated_rendered_documents(\n            rendered_html, site, wanted_issues, direction_first=True\n        ), []\n'''
if old_branch in text:
    text = text.replace(old_branch, new_branch, 1)
elif "广东八二渲染正文未出现目标期半波半头内容" not in text:
    raise RuntimeError("dedicated rendered branch not found")

collection.write_text(text, encoding="utf-8", newline="\n")


test_path = Path("tests/test_issue252_failed_repairs.py")
tests = test_path.read_text(encoding="utf-8")
addition = r'''


def test_guangdong_render_completeness_gate_requires_target_region():
    from bantou.documents.collection import _guangdong_render_has_target

    assert not _guangdong_render_has_target(
        "<html><body>澳门广东八二站</body></html>", {252}
    )
    assert _guangdong_render_has_target(
        "<html><body>『半波半头』 252期 杀[1头双]开00准</body></html>", {252}
    )


def test_guangdong_shell_gets_one_fresh_same_url_render(monkeypatch):
    from bantou.documents import collection
    from bantou.domain.models import Site, SourceDocument
    from bantou.site_profiles.registry import GUANGDONG_BAER_URL

    site = Site(
        "广东八二",
        GUANGDONG_BAER_URL,
        "top",
        1,
        "guangdong_baer_left_half_head",
        ("半头",),
    )
    calls = []

    def render(url, timeout, verify_ssl, *, deadline=None, wait_until="networkidle"):
        calls.append((url, wait_until))
        if len(calls) == 1:
            return "<html><body>澳门广东八二站</body></html>"
        return "<html><body>『半波半头』 252期 杀[1头双]开00准</body></html>"

    expected = [
        SourceDocument(
            "252期 杀[1头双]开00准",
            source_url=GUANGDONG_BAER_URL,
            source_kind="browser",
        )
    ]
    monkeypatch.setattr(collection, "fetch_rendered_html", render)
    monkeypatch.setattr(
        collection,
        "extract_dedicated_rendered_documents",
        lambda *args, **kwargs: expected,
    )

    documents, errors = collection.collect_site_documents(
        site, GUANGDONG_BAER_URL, {252}, 20, True
    )

    assert documents == expected
    assert errors == []
    assert [wait for _url, wait in calls] == ["domcontentloaded", "load"]


def test_guangdong_second_shell_still_fails(monkeypatch):
    import pytest
    from bantou.documents import collection
    from bantou.domain.models import Site
    from bantou.site_profiles.registry import GUANGDONG_BAER_URL

    site = Site(
        "广东八二",
        GUANGDONG_BAER_URL,
        "top",
        1,
        "guangdong_baer_left_half_head",
        ("半头",),
    )
    calls = []

    def render(url, timeout, verify_ssl, *, deadline=None, wait_until="networkidle"):
        calls.append(wait_until)
        return "<html><body>澳门广东八二站</body></html>"

    monkeypatch.setattr(collection, "fetch_rendered_html", render)
    with pytest.raises(ValueError, match="渲染正文未出现目标期"):
        collection.collect_site_documents(
            site, GUANGDONG_BAER_URL, {252}, 20, True
        )
    assert calls == ["domcontentloaded", "load"]
'''
if "test_guangdong_shell_gets_one_fresh_same_url_render" not in tests:
    test_path.write_text(tests.rstrip() + addition + "\n", encoding="utf-8", newline="\n")

print("Applied Guangdong Baer fresh-render retry.")

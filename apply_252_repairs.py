from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, got {count}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) Site-specific browser waits and the declared authoritative iframe for 把把论坛.
replace_once(
    "bantou/site_profiles/registry.py",
    'SITE_BROWSER_HTML_WAIT_UNTIL = {\n    GUANGDONG_BAER_URL: "load",\n    MENGXIAOMENG_URL: "domcontentloaded",',
    'SITE_BROWSER_HTML_WAIT_UNTIL = {\n    CAIYUNTONG_URL: "domcontentloaded",\n    GUANGDONG_BAER_URL: "load",\n    MENGXIAOMENG_URL: "domcontentloaded",\n    "https://opfeal.zbwno-faau4-zilwkd.xyz:16677/topic/930772.html": "domcontentloaded",',
)
replace_once(
    "bantou/site_profiles/registry.py",
    'BABA_FORUM_URL = "https://43666.886677a.app:2563/htm/bbs/top080.html"\nSHENZHEN_FUTAN_URL',
    'BABA_FORUM_URL = "https://43666.886677a.app:2563/htm/bbs/top080.html"\nBABA_FORUM_DATA_URL = "https://43666.886677a.app:2563/main/bbs/080.html"\nSHENZHEN_FUTAN_URL',
)

# 2) Avoid a 57 MB aggregate response while still requesting enough rows to prove the current-year prefix.
replace_once(
    "bantou/documents/dynamic/routes.py",
    'f"{base}/api/v1/users/{user_id}/forums?per_page=5000",',
    'f"{base}/api/v1/users/{user_id}/forums?per_page=500",',
)

# 3) Some aggregate endpoints ignore page=2. If page 1 contains the complete current-year prefix,
#    followed by older years, with strictly descending IDs, that is sufficient for current-year uniqueness.
aggregate_path = Path("bantou/documents/dynamic/aggregate.py")
aggregate = aggregate_path.read_text(encoding="utf-8-sig")
marker = '\n\ndef _pages(api_url, timeout, verify_ssl, deadline):\n'
if marker not in aggregate:
    raise RuntimeError("aggregate.py: _pages marker missing")
helper = '''\n\ndef _current_year_prefix_complete(rows) -> bool:\n    if not rows:\n        return False\n    current_year = date.today().year\n    years: list[int] = []\n    ids: list[int] = []\n    for row in rows:\n        if not isinstance(row, dict):\n            return False\n        try:\n            year = int(row.get("year"))\n            record_id = int(row.get("id"))\n        except (TypeError, ValueError):\n            return False\n        if year > current_year:\n            return False\n        years.append(year)\n        ids.append(record_id)\n    try:\n        first_old = next(index for index, year in enumerate(years) if year < current_year)\n    except StopIteration:\n        return False\n    if first_old == 0:\n        return False\n    if any(year != current_year for year in years[:first_old]):\n        return False\n    if any(year == current_year for year in years[first_old:]):\n        return False\n    if any(left <= right for left, right in zip(ids, ids[1:])):\n        return False\n    return True\n'''
aggregate = aggregate.replace(marker, helper + marker, 1)
old_end = '        yield rows\n        if (last is not None and page == last) or (last is None and len(rows) < page_size):\n            return\n'
new_end = '        yield rows\n        if (\n            (last is not None and page == last)\n            or (last is None and len(rows) < page_size)\n            or (last is None and page == 1 and _current_year_prefix_complete(rows))\n        ):\n            return\n'
if aggregate.count(old_end) != 1:
    raise RuntimeError("aggregate.py: page termination block mismatch")
aggregate_path.write_text(aggregate.replace(old_end, new_end, 1), encoding="utf-8")

# 4) Let rendered-text callers choose a stable readiness event instead of hardcoding networkidle.
replace_once(
    "bantou/fetching/policy.py",
    '''def fetch_rendered_text(\n    url: str, timeout: int, verify_ssl: bool, *, deadline: float | None = None\n) -> str:\n    return DEFAULT_TRANSPORT.fetch_rendered(\n        url, _request_timeout(timeout, deadline), verify_ssl, html=False\n    )\n''',
    '''def fetch_rendered_text(\n    url: str,\n    timeout: int,\n    verify_ssl: bool,\n    *,\n    deadline: float | None = None,\n    wait_until: str = "networkidle",\n) -> str:\n    return DEFAULT_TRANSPORT.fetch_rendered(\n        url,\n        _request_timeout(timeout, deadline),\n        verify_ssl,\n        html=False,\n        wait_until=wait_until,\n    )\n''',
)

# 5) Collection: seed the declared 把把论坛 authority source; resolve 萌小萌 from only the
#    entry document instead of recursively crawling hundreds of unrelated links; honor per-site waits.
replace_once(
    "bantou/documents/collection.py",
    '    BABA_FORUM_URL,\n    DEDICATED_RENDERED_SITE_RULES,',
    '    BABA_FORUM_DATA_URL,\n    BABA_FORUM_URL,\n    DEDICATED_RENDERED_SITE_RULES,',
)
replace_once(
    "bantou/documents/collection.py",
    '    frame_urls: list[str] = []\n    seen_frames: set[str] = set()\n    half_head_urls: list[str] = []',
    '    frame_urls: list[str] = []\n    seen_frames: set[str] = set()\n    if url == BABA_FORUM_URL:\n        seen_frames.add(BABA_FORUM_DATA_URL)\n        frame_urls.append(BABA_FORUM_DATA_URL)\n    half_head_urls: list[str] = []',
)
replace_once(
    "bantou/documents/collection.py",
    '''    entry_url = site.fetch_url or site.url\n    documents, _script_errors = collect_documents(\n        entry_url, timeout, verify_ssl, deadline=deadline\n    )\n    link_re = re.compile''',
    '''    entry_url = site.fetch_url or site.url\n    page_html = fetch_text(entry_url, timeout, verify_ssl, deadline=deadline)\n    rendered_html = fetch_rendered_html(\n        entry_url,\n        timeout,\n        verify_ssl,\n        deadline=deadline,\n        wait_until=SITE_BROWSER_HTML_WAIT_UNTIL.get(site.url, "domcontentloaded"),\n    )\n    documents = [\n        SourceDocument(\n            str(page_html),\n            source_url=str(getattr(page_html, "final_url", "") or entry_url),\n            source_kind="page",\n            document_authority="primary",\n        ),\n        SourceDocument(\n            str(rendered_html),\n            source_url=entry_url,\n            source_kind="browser",\n            document_authority="declared-browser",\n        ),\n    ]\n    link_re = re.compile''',
)
replace_once(
    "bantou/documents/collection.py",
    '''        rendered_text = fetch_rendered_text(\n            fetch_url, timeout, verify_ssl, deadline=deadline\n        )\n''',
    '''        rendered_text = fetch_rendered_text(\n            fetch_url,\n            timeout,\n            verify_ssl,\n            deadline=deadline,\n            wait_until=SITE_BROWSER_HTML_WAIT_UNTIL.get(site.url, "networkidle"),\n        )\n''',
)

# 6) Add focused regressions for the exact repair invariants.
test_path = Path("tests/test_audit_repairs.py")
tests = test_path.read_text(encoding="utf-8-sig")
append_marker = "\n\ndef test_252_repair_current_year_prefix_complete():"
if append_marker not in tests:
    tests += r'''\n\ndef test_252_repair_current_year_prefix_complete():\n    from bantou.documents.dynamic import aggregate\n\n    current = aggregate.date.today().year\n    rows = [\n        {"id": 30, "year": current},\n        {"id": 29, "year": current},\n        {"id": 28, "year": current - 1},\n        {"id": 27, "year": current - 1},\n    ]\n    assert aggregate._current_year_prefix_complete(rows)\n    assert not aggregate._current_year_prefix_complete([\n        {"id": 30, "year": current},\n        {"id": 29, "year": current - 1},\n        {"id": 28, "year": current},\n    ])\n\n\ndef test_252_repair_meng_resolver_uses_exact_same_origin_anchor(monkeypatch):\n    from bantou.documents import collection\n    from bantou.domain.models import Site\n    from bantou.site_profiles.registry import MENGXIAOMENG_URL\n\n    site = Site(\n        name="萌小萌",\n        url=MENGXIAOMENG_URL,\n        pick="top",\n        line_no=1,\n        anchors=("绝杀半头",),\n        entry_mode="issue_link",\n    )\n    monkeypatch.setattr(collection, "fetch_text", lambda *a, **k: "<html></html>")\n    monkeypatch.setattr(\n        collection,\n        "fetch_rendered_html",\n        lambda *a, **k: (\n            '<a href="https://other.test/topic/1">252期:[绝杀半头◇◇萌小萌]</a>'\n            '<a href="/topic/1090013.html">252期:[绝杀半头◇◇萌小萌]←※已更新</a>'\n            '<a href="/topic/320718.html">杀料区 252期:[绝杀半头] 超级稳定</a>'\n        ),\n    )\n    assert collection.resolve_mengxiaomeng_detail_url(site, 252, 2, True).endswith(\n        "/topic/1090013.html"\n    )\n\n\ndef test_252_repair_baba_declared_data_source_is_fetched(monkeypatch):\n    from bantou.documents import collection\n    from bantou.site_profiles.registry import BABA_FORUM_DATA_URL, BABA_FORUM_URL\n\n    calls = []\n    monkeypatch.setattr(collection, "fetch_text", lambda *a, **k: "<html></html>")\n    monkeypatch.setattr(collection, "extra_api_urls", lambda url: [])\n\n    def fake_group(urls, *args, **kwargs):\n        calls.extend(urls)\n        return [(url, "", None) for url in urls]\n\n    monkeypatch.setattr(collection, "fetch_resource_group", fake_group)\n    collection.collect_documents(BABA_FORUM_URL, 2, True)\n    assert BABA_FORUM_DATA_URL in calls\n\n\ndef test_252_repair_rendered_text_forwards_wait_until(monkeypatch):\n    from bantou.fetching import policy\n\n    seen = {}\n\n    def fake_rendered(url, timeout, verify_ssl, *, html, wait_until, interaction=None):\n        seen["wait_until"] = wait_until\n        return "ok"\n\n    monkeypatch.setattr(policy.DEFAULT_TRANSPORT, "fetch_rendered", fake_rendered)\n    assert policy.fetch_rendered_text(\n        "https://example.test", 3, True, wait_until="domcontentloaded"\n    ) == "ok"\n    assert seen["wait_until"] == "domcontentloaded"\n'''
    # Convert the raw literal's escaped newlines into real file newlines.
    tests = tests.replace(r'\n', '\n')
    test_path.write_text(tests, encoding="utf-8")

print("252 production repair patch applied")

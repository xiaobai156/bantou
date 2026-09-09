from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, got {count}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Site-specific browser waits and the declared authoritative data document for 把把论坛.
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

# Bound the aggregate response while retaining enough rows to cross the current-year boundary.
replace_once(
    "bantou/documents/dynamic/routes.py",
    'f"{base}/api/v1/users/{user_id}/forums?per_page=5000",',
    'f"{base}/api/v1/users/{user_id}/forums?per_page=500",',
)

# Some aggregate endpoints ignore page=2. Accept page 1 as complete only when it proves
# a strictly ordered current-year prefix followed by older years and no current-year row after that boundary.
aggregate_path = Path("bantou/documents/dynamic/aggregate.py")
aggregate = aggregate_path.read_text(encoding="utf-8-sig")
marker = "\n\ndef _pages(api_url, timeout, verify_ssl, deadline):\n"
if aggregate.count(marker) != 1:
    raise RuntimeError("aggregate.py: _pages marker mismatch")
helper = '''

def _current_year_prefix_complete(rows) -> bool:
    if not rows:
        return False
    current_year = date.today().year
    years: list[int] = []
    ids: list[int] = []
    for row in rows:
        if not isinstance(row, dict):
            return False
        try:
            year = int(row.get("year"))
            record_id = int(row.get("id"))
        except (TypeError, ValueError):
            return False
        if year > current_year:
            return False
        years.append(year)
        ids.append(record_id)
    try:
        first_old = next(index for index, year in enumerate(years) if year < current_year)
    except StopIteration:
        return False
    if first_old == 0:
        return False
    if any(year != current_year for year in years[:first_old]):
        return False
    if any(year == current_year for year in years[first_old:]):
        return False
    if any(left <= right for left, right in zip(ids, ids[1:])):
        return False
    return True
'''
aggregate = aggregate.replace(marker, helper + marker, 1)
old_end = '        yield rows\n        if (last is not None and page == last) or (last is None and len(rows) < page_size):\n            return\n'
new_end = '''        yield rows
        if (
            (last is not None and page == last)
            or (last is None and len(rows) < page_size)
            or (last is None and page == 1 and _current_year_prefix_complete(rows))
        ):
            return
'''
if aggregate.count(old_end) != 1:
    raise RuntimeError("aggregate.py: page termination block mismatch")
aggregate_path.write_text(aggregate.replace(old_end, new_end, 1), encoding="utf-8")

# Allow rendered-text sites to select a stable browser readiness event.
replace_once(
    "bantou/fetching/policy.py",
    '''def fetch_rendered_text(
    url: str, timeout: int, verify_ssl: bool, *, deadline: float | None = None
) -> str:
    return DEFAULT_TRANSPORT.fetch_rendered(
        url, _request_timeout(timeout, deadline), verify_ssl, html=False
    )
''',
    '''def fetch_rendered_text(
    url: str,
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
    wait_until: str = "networkidle",
) -> str:
    return DEFAULT_TRANSPORT.fetch_rendered(
        url,
        _request_timeout(timeout, deadline),
        verify_ssl,
        html=False,
        wait_until=wait_until,
    )
''',
)

# Collection fixes: declared 把把论坛 data source, lightweight exact 萌小萌 entry resolution,
# and site-specific browser waits for rendered-text detail pages.
replace_once(
    "bantou/documents/collection.py",
    '    BABA_FORUM_URL,\n    DEDICATED_RENDERED_SITE_RULES,',
    '    BABA_FORUM_DATA_URL,\n    BABA_FORUM_URL,\n    DEDICATED_RENDERED_SITE_RULES,',
)
replace_once(
    "bantou/documents/collection.py",
    '''def collect_documents(
    url: str,
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
) -> tuple[list[SourceDocument], list[str]]:
''',
    '''def collect_documents(
    url: str,
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
    follow_resources: bool = True,
) -> tuple[list[SourceDocument], list[str]]:
''',
)
replace_once(
    "bantou/documents/collection.py",
    '    frame_urls: list[str] = []\n    seen_frames: set[str] = set()\n    half_head_urls: list[str] = []',
    '    frame_urls: list[str] = []\n    seen_frames: set[str] = set()\n    if url == BABA_FORUM_URL:\n        seen_frames.add(BABA_FORUM_DATA_URL)\n        frame_urls.append(BABA_FORUM_DATA_URL)\n    half_head_urls: list[str] = []',
)
replace_once(
    "bantou/documents/collection.py",
    '''            add_document_with_decoded(
                rendered_html, documents, seen_docs, source_url=url, source_kind="browser"
            )

    add_fetched_resources(
''',
    '''            add_document_with_decoded(
                rendered_html, documents, seen_docs, source_url=url, source_kind="browser"
            )

    if not follow_resources:
        return documents, script_errors

    add_fetched_resources(
''',
)
replace_once(
    "bantou/documents/collection.py",
    '''    documents, _script_errors = collect_documents(
        entry_url, timeout, verify_ssl, deadline=deadline
    )
''',
    '''    documents, _script_errors = collect_documents(
        entry_url,
        timeout,
        verify_ssl,
        deadline=deadline,
        follow_resources=False,
    )
''',
)
replace_once(
    "bantou/documents/collection.py",
    '''        rendered_text = fetch_rendered_text(
            fetch_url, timeout, verify_ssl, deadline=deadline
        )
''',
    '''        rendered_text = fetch_rendered_text(
            fetch_url,
            timeout,
            verify_ssl,
            deadline=deadline,
            wait_until=SITE_BROWSER_HTML_WAIT_UNTIL.get(site.url, "networkidle"),
        )
''',
)

# Focused independent regressions. Do not rewrite existing regression files.
Path("tests/test_issue252_repairs.py").write_text(
    '''from __future__ import annotations


def test_current_year_prefix_complete():
    from bantou.documents.dynamic import aggregate

    current = aggregate.date.today().year
    assert aggregate._current_year_prefix_complete([
        {"id": 30, "year": current},
        {"id": 29, "year": current},
        {"id": 28, "year": current - 1},
        {"id": 27, "year": current - 1},
    ])
    assert not aggregate._current_year_prefix_complete([
        {"id": 30, "year": current},
        {"id": 29, "year": current - 1},
        {"id": 28, "year": current},
    ])


def test_meng_resolver_uses_exact_same_origin_anchor(monkeypatch):
    from bantou.documents import collection
    from bantou.domain.models import Site
    from bantou.site_profiles.registry import MENGXIAOMENG_URL

    site = Site(
        name="萌小萌",
        url=MENGXIAOMENG_URL,
        pick="top",
        line_no=1,
        anchors=("绝杀半头",),
        entry_mode="issue_link",
    )
    monkeypatch.setattr(collection, "fetch_text", lambda *a, **k: "<html></html>")
    monkeypatch.setattr(
        collection,
        "fetch_rendered_html",
        lambda *a, **k: (
            '<a href="https://other.test/topic/1">252期:[绝杀半头◇◇萌小萌]</a>'
            '<a href="/topic/1090013.html">252期:[绝杀半头◇◇萌小萌]←※已更新</a>'
            '<a href="/topic/320718.html">杀料区 252期:[绝杀半头] 超级稳定</a>'
        ),
    )
    assert collection.resolve_mengxiaomeng_detail_url(site, 252, 2, True).endswith(
        "/topic/1090013.html"
    )


def test_entry_only_collection_does_not_follow_resources(monkeypatch):
    from bantou.documents import collection
    from bantou.site_profiles.registry import MENGXIAOMENG_URL

    monkeypatch.setattr(collection, "fetch_text", lambda *a, **k: "<html></html>")
    monkeypatch.setattr(collection, "fetch_rendered_html", lambda *a, **k: "<html></html>")
    monkeypatch.setattr(
        collection,
        "add_fetched_resources",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("followed resources")),
    )
    documents, errors = collection.collect_documents(
        MENGXIAOMENG_URL, 2, True, follow_resources=False
    )
    assert len(documents) == 2
    assert errors == []


def test_baba_declared_data_source_is_fetched(monkeypatch):
    from bantou.documents import collection
    from bantou.site_profiles.registry import BABA_FORUM_DATA_URL, BABA_FORUM_URL

    calls = []
    monkeypatch.setattr(collection, "fetch_text", lambda *a, **k: "<html></html>")
    monkeypatch.setattr(collection, "extra_api_urls", lambda url: [])

    def fake_group(urls, *args, **kwargs):
        calls.extend(urls)
        return [(url, "", None) for url in urls]

    monkeypatch.setattr(collection, "fetch_resource_group", fake_group)
    collection.collect_documents(BABA_FORUM_URL, 2, True)
    assert BABA_FORUM_DATA_URL in calls


def test_rendered_text_forwards_wait_until(monkeypatch):
    from bantou.fetching import policy

    seen = {}

    def fake_rendered(url, timeout, verify_ssl, *, html, wait_until, interaction=None):
        seen["wait_until"] = wait_until
        return "ok"

    monkeypatch.setattr(policy.DEFAULT_TRANSPORT, "fetch_rendered", fake_rendered)
    assert policy.fetch_rendered_text(
        "https://example.test", 3, True, wait_until="domcontentloaded"
    ) == "ok"
    assert seen["wait_until"] == "domcontentloaded"
''',
    encoding="utf-8",
)

print("252 production repair patch applied")

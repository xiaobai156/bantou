from __future__ import annotations

from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path}: expected one replacement, found {count}: {old[:120]!r}"
        )
    write(path, text.replace(old, new, 1))


def append_once(path: str, marker: str, addition: str) -> None:
    text = read(path)
    if marker in text:
        raise RuntimeError(f"{path}: follow-up marker already present")
    write(path, text.rstrip() + "\n\n" + addition.strip() + "\n")


replace_once(
    "bantou/outputs/formatting.py",
    '''    if not path.exists():
        return []
    expected_name = f"{issue_text}-半头.txt"
''',
    '''    if not path.exists():
        raise ValueError(f"找不到成功结果文件：{path}")
    expected_name = f"{issue_text}-半头.txt"
''',
)

replace_once(
    "bantou/application/single_period.py",
    '''    *,
    multi_mode: bool = False,
) -> int:
''',
    '''    *,
    multi_mode: bool = False,
    configured_sites: list[Site] | None = None,
) -> int:
''',
)
replace_once(
    "bantou/application/single_period.py",
    '''                    configured_sites=sites,
''',
    '''                    configured_sites=configured_sites or sites,
''',
)
replace_once(
    "bantou/application/single_period.py",
    '''        sites = read_sites(Path(sites_input))
        if args.retry_fail:
''',
    '''        sites = read_sites(Path(sites_input))
        configured_sites = list(sites)
        if args.retry_fail:
''',
)
replace_once(
    "bantou/application/single_period.py",
    '''        multi_mode=multi_mode,
    )
''',
    '''        multi_mode=multi_mode,
        configured_sites=configured_sites,
    )
''',
)

replace_once(
    "bantou/text.py",
    '''IGNORED_HTML_TAGS = {"script", "style", "template", "noscript"}


class PlainTextParser''',
    '''IGNORED_HTML_TAGS = {"script", "style", "template", "noscript"}
_IGNORED_HTML_BLOCK_RE = re.compile(
    r"<(?P<tag>script|style|template|noscript)\\b[^>]*>[\\s\\S]*?(?:</(?P=tag)\\s*>|\\Z)",
    re.I,
)


def _ignored_html_ranges(text: str) -> tuple[tuple[int, int], ...]:
    return tuple((match.start(), match.end()) for match in _IGNORED_HTML_BLOCK_RE.finditer(text or ""))


def _position_in_ranges(position: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= position < end for start, end in ranges)


def _mask_ignored_html_blocks(text: str) -> str:
    def mask(match: re.Match[str]) -> str:
        return "".join("\\n" if char == "\\n" else " " for char in match.group(0))

    return _IGNORED_HTML_BLOCK_RE.sub(mask, text or "")


class PlainTextParser''',
)
replace_once(
    "bantou/text.py",
    '''def source_issue_token_positions(text: str, *, browser_text: bool = False) -> list[int]:
    positions: list[int] = []
    for match in SOURCE_ISSUE_TOKEN_RE.finditer(text or ""):
        if browser_text or not _inside_html_tag(text, match.start()):
            positions.append(match.start())
    return positions
''',
    '''def source_issue_token_positions(text: str, *, browser_text: bool = False) -> list[int]:
    positions: list[int] = []
    ignored_ranges = () if browser_text else _ignored_html_ranges(text)
    for match in SOURCE_ISSUE_TOKEN_RE.finditer(text or ""):
        if browser_text or (
            not _inside_html_tag(text, match.start())
            and not _position_in_ranges(match.start(), ignored_ranges)
        ):
            positions.append(match.start())
    return positions
''',
)
replace_once(
    "bantou/text.py",
    '''    source_positions = [
        position
        for position in issue_token_positions(source_text, issue_text)
        if is_browser_text or not _inside_html_tag(source_text, position)
    ]
''',
    '''    ignored_ranges = () if is_browser_text else _ignored_html_ranges(source_text)
    source_positions = [
        position
        for position in issue_token_positions(source_text, issue_text)
        if is_browser_text
        or (
            not _inside_html_tag(source_text, position)
            and not _position_in_ranges(position, ignored_ranges)
        )
    ]
''',
)
replace_once(
    "bantou/text.py",
    '''    except Exception:
        return normalize_text(re.sub(r"<[^>]+>", " ", document))
''',
    '''    except Exception:
        visible = _mask_ignored_html_blocks(document)
        return normalize_text(re.sub(r"<[^>]+>", " ", visible))
''',
)
replace_once(
    "bantou/text.py",
    '''def extract_half_head_table_texts(document: str) -> list[str]:
    extracted = []
    seen = set()
    tables = list(TABLE_RE.finditer(document or ""))
    groups = [(m.group(1), m.start(1)) for m in tables] or [(document or "", 0)]
''',
    '''def extract_half_head_table_texts(document: str) -> list[str]:
    extracted = []
    seen = set()
    working_document = _mask_ignored_html_blocks(document or "")
    tables = list(TABLE_RE.finditer(working_document))
    groups = [(m.group(1), m.start(1)) for m in tables] or [(working_document, 0)]
''',
)
replace_once(
    "bantou/text.py",
    '''positions = [p for p in issue_token_positions(document, token.group(1)) if raw_cell_start <= p < raw_cell_end]''',
    '''positions = [p for p in issue_token_positions(working_document, token.group(1)) if raw_cell_start <= p < raw_cell_end]''',
)

replace_once(
    "bantou/documents/content.py",
    '''    alternate_data_anchors = DEDICATED_RENDERED_ALTERNATE_DATA_ANCHORS.get(site.url, ())
    blocks: list[tuple[str, int, int, str, str]] = []
''',
    '''    alternate_data_anchors = DEDICATED_RENDERED_ALTERNATE_DATA_ANCHORS.get(site.url, ())
    page_matches = bool(page_identity and page_identity in root_text)
    blocks: list[tuple[str, int, int, str, str]] = []
''',
)

replace_once(
    "bantou/documents/collection.py",
    '''        if source_kind in {"linked-page", "api"}:
            continue
        if source_url and source_url != entry_url and source_kind not in {
            "script",
            "script-decoded",
            "iframe",
            "iframe-decoded",
        }:
            continue
''',
    '''        if source_kind in {
            "linked-page", "linked-page-decoded", "api", "api-decoded"
        }:
            continue
        allowed_link_sources = {
            "page", "page-decoded", "browser", "browser-decoded",
            "script", "script-decoded", "iframe", "iframe-decoded",
        }
        if source_kind not in allowed_link_sources:
            continue
        if source_url and not same_origin(entry_url, source_url):
            continue
''',
)

replace_once(
    "bantou/fetching/policy.py",
    '''from .transport import DEFAULT_TRANSPORT, FetchedText, canonical_url, same_origin
''',
    '''from .transport import (
    DEFAULT_TRANSPORT,
    FetchedText,
    MAX_BODY_BYTES,
    canonical_url,
    same_origin,
)
''',
)
replace_once(
    "bantou/fetching/policy.py",
    '''        body, raw_meta = completed.stdout.rsplit(marker, 1)
        meta = raw_meta.decode("utf-8", errors="replace").strip().split("\\t")
''',
    '''        body, raw_meta = completed.stdout.rsplit(marker, 1)
        if len(body) > MAX_BODY_BYTES:
            raise FetchError(
                f"兼容 TLS 兜底失败：响应正文超过 {MAX_BODY_BYTES} 字节上限"
            )
        meta = raw_meta.decode("utf-8", errors="replace").strip().split("\\t")
''',
)

replace_once(
    "tests/test_audit_round3.py",
    '''from bantou.application import multi_period, site_crawl, site_validation
''',
    '''from bantou.application import multi_period, single_period, site_crawl, site_validation
''',
)

append_once(
    "tests/test_audit_round3.py",
    "test_hidden_script_same_issue_does_not_steal_source_position",
    r'''
def test_hidden_script_same_issue_does_not_steal_source_position(monkeypatch):
    html = (
        "<script>const old='251期 必杀半头 2头双 开00对';</script>"
        "<p>251期 必杀半头 2头双 开00对</p>"
    )
    result = run_document(monkeypatch, html)
    assert result.matches
    assert result.matches[0].position == html.rindex("251期")
    assert result.matches[0].anchor_position == html.rindex("半头")


def test_fake_table_inside_script_is_not_parsed():
    html = (
        "<script>const old=`<table><tr><th>期数</th><th>半头</th><th>开奖</th></tr>"
        "<tr><td>251期</td><td>2头双</td><td>开00对</td></tr></table>`;</script>"
        "<p>正常正文</p>"
    )
    assert extract_half_head_table_texts(html) == []


def test_strict_success_reader_requires_existing_file(tmp_path):
    with pytest.raises(ValueError, match="找不到成功结果文件"):
        read_success_data_strict(
            tmp_path / "251期-半头.txt", "251期", [site("A")]
        )


def test_retry_finalize_receives_full_configured_site_set(tmp_path, monkeypatch):
    selected = [site("A")]
    configured = selected + [site("B", "https://example.test/b")]
    args = SimpleNamespace(
        diagnose=False,
        retry_fail=True,
        replace_existing=False,
        resolved_success_path=tmp_path / "251期-半头.txt",
        resolved_fail_path=tmp_path / "251期-半头-失败.txt",
    )
    captured = {}

    monkeypatch.setattr(
        single_period,
        "_prepare_cache_update",
        lambda *a, **k: (a[3], a[4], a[5], None, {}),
    )

    def merge(*args, configured_sites, **kwargs):
        captured["sites"] = configured_sites
        return args[1], args[2]

    monkeypatch.setattr(single_period, "_merge_retry_rows", merge)
    code = single_period._finalize_run(
        args,
        [251],
        selected,
        "251",
        [],
        {},
        ["网站名称\t分类\t原因\t网址"],
        configured_sites=configured,
    )
    assert code == 0
    assert captured["sites"] == configured


def test_issue_link_accepts_same_origin_redirected_primary_document(monkeypatch):
    entry = "https://example.test/root/index.html"
    s = site("A", entry, fetch_url=entry, entry_mode="issue_link")
    document = SourceDocument(
        "<a href='251.html'>251期 半头 A</a>",
        source_url="https://example.test/root/redirected.html",
        source_kind="page",
        document_authority="primary",
    )
    monkeypatch.setattr(collection, "collect_documents", lambda *a, **k: ([document], []))
    assert collection.resolve_mengxiaomeng_detail_url(s, 251, 2, True) == (
        "https://example.test/root/251.html"
    )


def test_empty_dedicated_container_set_has_precise_failure():
    url = "https://peubwtt.t3vdj-h3294-qpbmtj.work:16677/#am"
    with pytest.raises(ValueError, match="方向候选容器为空"):
        extract_dedicated_rendered_documents(
            "<div>澳门跑狗</div>", site("澳门跑狗", url), {251}, direction_first=True
        )


def test_curl_body_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(policy, "MAX_BODY_BYTES", 4)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: curl_result(200, body=b"12345"),
    )
    with pytest.raises(policy.FetchError, match="正文超过"):
        policy.fetch_with_curl("https://example.test/a", 2, True)
''',
)

print("Applied round-three follow-up safety corrections.")

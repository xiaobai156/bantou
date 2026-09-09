"""Additional fail-closed regressions; no public network access."""
from __future__ import annotations

import io
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bantou.application import multi_period, single_period, site_crawl, site_validation
from bantou.cache.validation import cache_entry_from_match, compare_cached_match
from bantou.config.cli import build_parser
from bantou.documents import collection
from bantou.documents.content import extract_dedicated_rendered_documents
from bantou.domain.models import Match, Site, SourceDocument
from bantou.fetching import policy
from bantou.fetching.transport import MAX_BODY_BYTES, RunTransport
from bantou.outputs.formatting import (
    build_success_output_lines,
    read_success_data_strict,
)
from bantou.parsers.matching import apply_direction_source_scope
from bantou.text import extract_half_head_table_texts, html_to_text


def site(name="A", url="https://example.test/a", **kwargs):
    return Site(
        name,
        url,
        kwargs.pop("pick", "top"),
        1,
        kwargs.pop("parser_id", "strict_half_head"),
        kwargs.pop("anchors", ("半头",)),
        **kwargs,
    )


def run_document(monkeypatch, text, s=None, kind="page"):
    s = s or site()
    document = SourceDocument(
        text,
        source_url=s.url,
        source_kind=kind,
        container_id="test",
        document_authority="primary",
        block_start=0,
        block_end=len(text),
    )
    monkeypatch.setattr(
        site_crawl,
        "_documents_for_requested_issues",
        lambda *args: ([document], []),
    )
    return site_crawl.crawl_site(1, s, {251}, None, 5, True, 0)


def evidence_match(**kwargs):
    fields = dict(
        issue=251,
        issue_text="251",
        value="2头双",
        snippet="251期 必杀半头 2头双 开00对",
        order=1,
        position=0,
        source_url="https://example.test/a",
        source_kind="page",
        anchor_text="半头",
        anchor_position=7,
        block_id="row",
        block_start=0,
        block_end=40,
        container_id="body",
        document_authority="primary-page",
        rule_id="structural",
    )
    fields.update(kwargs)
    return Match(**fields)


def test_other_column_value_is_never_borrowed(monkeypatch):
    result = run_document(
        monkeypatch,
        "251期 必杀半头：等待更新 三头中特：3头单 开00对",
    )
    assert not result.matches


def test_half_head_value_stops_before_other_column(monkeypatch):
    result = run_document(
        monkeypatch,
        "251期 必杀半头：2头双 三头中特：3头单 开00对",
    )
    assert [match.value for match in result.matches] == ["2头双"]


def test_two_values_inside_half_head_field_still_conflict(monkeypatch):
    result = run_document(
        monkeypatch,
        "251期 必杀半头：2头双 3头单 开00对",
    )
    assert not result.matches
    assert "冲突" in (result.error or result.miss_reason or "")


def test_new_table_header_clears_old_half_head_column():
    html = (
        "<table>"
        "<tr><th>期数</th><th>半头</th><th>开奖</th></tr>"
        "<tr><td>250期</td><td>2头双</td><td>开00对</td></tr>"
        "<tr><th>期数</th><th>三头中特</th><th>开奖</th></tr>"
        "<tr><td>251期</td><td>3头单</td><td>开00对</td></tr>"
        "</table>"
    )
    values = [str(item) for item in extract_half_head_table_texts(html)]
    assert any("250期" in item and "2头双" in item for item in values)
    assert all("251期" not in item for item in values)


def test_hidden_script_and_style_are_not_visible_text(monkeypatch):
    html = (
        "<html><style>.x{content:'251期 必杀半头 2头双 开00对'}</style>"
        "<script>const old='251期 必杀半头 2头双 开00对';</script>"
        "<body>正常页面</body></html>"
    )
    assert "必杀半头" not in html_to_text(html)
    assert not run_document(monkeypatch, html).matches


def test_ambiguous_global_rendered_identity_fails_closed():
    url = "https://peubwtt.t3vdj-h3294-qpbmtj.work:16677/#am"
    s = site("澳门跑狗", url)
    html = (
        "<div>澳门跑狗</div>"
        "<div class='dz_content08'>251期 必杀半头 1头单 开00对</div>"
        "<div class='dz_content08'>251期 必杀半头 2头双 开00对</div>"
    )
    with pytest.raises(ValueError, match="候选容器不唯一"):
        extract_dedicated_rendered_documents(html, s, {251}, direction_first=True)


def test_rendered_source_scope_never_flattens_two_containers():
    url = "https://peubwtt.t3vdj-h3294-qpbmtj.work:16677/#am"
    s = site("澳门跑狗", url)
    matches = [evidence_match(document_order=0), evidence_match(document_order=1)]
    scoped, reason = apply_direction_source_scope(matches, s)
    assert not scoped
    assert "未唯一" in reason


def valid_success(path: Path, sites: list[Site]):
    rows = [
        (sites[0].name, "251期", "2头双", sites[0].url),
        (sites[1].name, "251期", "1头单", sites[1].url),
    ]
    path.write_text(
        "\n".join(build_success_output_lines(rows)) + "\n",
        encoding="utf-8-sig",
    )


def test_strict_success_reader_validates_name_rows_and_ranking(tmp_path):
    sites = [site("A"), site("B", "https://example.test/b")]
    path = tmp_path / "251期-半头.txt"
    valid_success(path, sites)
    rows = read_success_data_strict(path, "251期", sites)
    assert [row[0] for row in rows] == ["A", "B"]
    assert rows[0][3] == sites[0].url

    path.write_text("2头双 A\n损坏行\n\n内容\t次数\t排名\n2头双\t1\t1\n", encoding="utf-8-sig")
    with pytest.raises(ValueError, match="格式无效"):
        read_success_data_strict(path, "251期", sites)


def test_strict_success_reader_rejects_duplicate_or_bad_ranking(tmp_path):
    sites = [site("A")]
    path = tmp_path / "251期-半头.txt"
    path.write_text(
        "2头双 A\n2头双 A\n\n内容\t次数\t排名\n2头双\t2\t1\n",
        encoding="utf-8-sig",
    )
    with pytest.raises(ValueError, match="重复"):
        read_success_data_strict(path, "251期", sites)
    path.write_text(
        "2头双 A\n\n内容\t次数\t排名\n2头双\t9\t1\n",
        encoding="utf-8-sig",
    )
    with pytest.raises(ValueError, match="排行榜"):
        read_success_data_strict(path, "251期", sites)


def test_issue_link_uses_owning_document_base_and_full_origin(monkeypatch):
    s = site("A", "https://example.test/root/index.html", fetch_url="https://example.test/root/index.html", entry_mode="issue_link")
    document = SourceDocument(
        "<a href='../251.html'>251期 半头 A</a>",
        source_url="https://example.test/sub/frame/index.html",
        source_kind="iframe",
        document_authority="attached",
    )
    monkeypatch.setattr(collection, "collect_documents", lambda *a, **k: ([document], []))
    assert collection.resolve_mengxiaomeng_detail_url(s, 251, 2, True) == "https://example.test/sub/251.html"

    bad = SourceDocument(
        "<a href='https://example.test:444/251.html'>251期 半头 A</a>",
        source_url="https://example.test/root/index.html",
        source_kind="page",
        document_authority="primary",
    )
    monkeypatch.setattr(collection, "collect_documents", lambda *a, **k: ([bad], []))
    with pytest.raises(ValueError, match="找不到"):
        collection.resolve_mengxiaomeng_detail_url(s, 251, 2, True)


def test_irrelevant_cross_origin_cdn_script_is_ignored(monkeypatch):
    page = "<html><script src='https://cdn.example.net/assets/app.js'></script><body>ok</body></html>"
    monkeypatch.setattr(collection, "fetch_text", lambda *a, **k: page)
    monkeypatch.setattr(collection, "extra_api_urls", lambda url: [])
    documents, errors = collection.collect_documents("https://example.test/a", 2, True)
    assert documents and not errors


def curl_result(status, body=b"", redirect="", effective="https://example.test/a"):
    meta = f"\n__BANTOU_CURL_META__{status}\t{redirect}\t{effective}".encode()
    return SimpleNamespace(returncode=0, stdout=body + meta, stderr=b"")


def test_curl_rejects_cross_origin_redirect(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: curl_result(302, redirect="https://other.test/x"),
    )
    with pytest.raises(policy.FetchError, match="跨来源"):
        policy.fetch_with_curl("https://example.test/a", 2, True)


def test_curl_follows_same_origin_and_preserves_final_url(monkeypatch):
    results = iter(
        [
            curl_result(302, redirect="/b"),
            curl_result(200, body=b"body", effective="https://example.test/b"),
        ]
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: next(results))
    text = policy.fetch_with_curl("https://example.test/a", 2, True)
    assert text == "body"
    assert text.final_url == "https://example.test/b"
    assert text.redirect_chain == ("https://example.test/a",)


def test_cli_no_longer_accepts_public_multi_mode():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["251", "--multi-mode"])


def test_multi_period_uses_internal_mode(monkeypatch):
    called = []
    monkeypatch.setattr(
        multi_period,
        "run_single_period",
        lambda argv, **kwargs: called.append((argv, kwargs)) or 0,
    )
    multi_period.run_period(251)
    assert called == [(["251"], {"multi_mode": True})]


class StreamingResponse:
    def __init__(self, chunks, *, headers=None):
        self.status_code = 200
        self.headers = headers or {}
        self.encoding = "utf-8"
        self.url = "https://example.test/a"
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield from self._chunks


def test_http_stream_body_limit_and_session_close(monkeypatch):
    transport = RunTransport()
    session = Mock()
    session.get.return_value = StreamingResponse([b"123456", b"78901"])
    monkeypatch.setattr("bantou.fetching.transport.MAX_BODY_BYTES", 10)
    monkeypatch.setattr(transport, "session_for", lambda verify: session)
    with pytest.raises(Exception, match="超过"):
        transport.fetch_text("https://example.test/a", 2, True)

    tracked = Mock()
    transport._sessions.add(tracked)
    transport.close()
    tracked.close.assert_called_once()


def test_declared_http_body_limit_rejected_before_read(monkeypatch):
    transport = RunTransport()
    session = Mock()
    session.get.return_value = StreamingResponse(
        [], headers={"Content-Length": str(MAX_BODY_BYTES + 1)}
    )
    monkeypatch.setattr(transport, "session_for", lambda verify: session)
    with pytest.raises(Exception, match="超过"):
        transport.fetch_text("https://example.test/a", 2, True)


def test_cache_evidence_snippet_change_is_a_conflict():
    current = evidence_match()
    cached = cache_entry_from_match(current)
    reason = compare_cached_match(cached, replace(current, snippet="changed evidence"))
    assert reason is not None and "原始片段" in reason


def test_validation_output_reports_real_evidence(capsys):
    result = SimpleNamespace(
        error=None,
        miss_reason=None,
        matches=[evidence_match()],
        direction_evidence=(),
    )
    assert site_validation.print_result(1, 1, site(), result, {251})
    output = capsys.readouterr().out
    assert "来源=https://example.test/a" in output
    assert "锚点：通过" not in output


@pytest.mark.skipif(
    __import__("os").environ.get("RUN_BROWSER_SMOKE") != "1",
    reason="Chromium smoke explicitly enabled by Windows CI",
)
def test_browser_context_storage_isolated_between_tasks():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from bantou.fetching.browser_process import ProcessBrowserWorker

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/set"):
                body = (
                    "<body><script>localStorage.setItem('round3','secret');"
                    "document.body.textContent='set'</script></body>"
                )
            else:
                body = (
                    "<body><script>document.body.textContent="
                    "localStorage.getItem('round3')||'empty'</script></body>"
                )
            payload = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    worker = ProcessBrowserWorker()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert worker.render(base + "/set", 20, True, False, "load") == "set"
        assert worker.render(base + "/read", 20, True, False, "load") == "empty"
    finally:
        worker.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

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


def test_strict_success_reader_allows_all_failed_run_without_success_file(tmp_path):
    assert read_success_data_strict(
        tmp_path / "251期-半头.txt", "251期", [site("A")]
    ) == []


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

def test_hidden_script_anchor_after_visible_issue_is_ignored(monkeypatch):
    html = (
        "<p>251期</p><script>const fake='半头';</script>"
        "<p>必杀半头 2头双 开00对</p>"
    )
    result = run_document(monkeypatch, html)
    assert result.matches
    assert result.matches[0].anchor_position == html.rindex("半头")


def test_retry_without_success_requires_all_sites_in_failure_file(tmp_path):
    bad = failure_file(tmp_path)
    configured = [site("A"), site("B", "https://example.test/b")]
    with pytest.raises(ValueError, match="未覆盖全部正式站点"):
        single_period._merge_retry_rows(
            "251",
            [],
            ["网站名称\t分类\t原因\t网址"],
            success_path=tmp_path / "251期-半头.txt",
            fail_path=bad,
            configured_sites=configured,
        )


def test_retry_merge_revalidates_changed_failure_identity(tmp_path):
    good = tmp_path / "251期-半头.txt"
    good.write_text(
        "2头双 A\n\n内容\t次数\t排名\n2头双\t1\t1\n",
        encoding="utf-8-sig",
    )
    bad = failure_file(
        tmp_path,
        text=(
            "网站名称\t分类\t原因\t网址\n"
            "B\t超时\t超时\thttps://example.test/a\n"
        ),
    )
    with pytest.raises(ValueError, match="成对匹配"):
        single_period._merge_retry_rows(
            "251",
            [],
            ["网站名称\t分类\t原因\t网址"],
            success_path=good,
            fail_path=bad,
            configured_sites=[site("A"), site("B", "https://example.test/b")],
        )


def test_curl_command_enforces_download_size_limit():
    command = policy.curl_command("https://example.test/a", 2, True)
    index = command.index("--max-filesize")
    assert int(command[index + 1]) == policy.MAX_BODY_BYTES


def failure_file(tmp_path, name="251期-半头-失败.txt", text=None):
    path = tmp_path / name
    path.write_text(
        text
        or (
            "网站名称\t分类\t原因\t网址\n"
            "A\t访问超时\t超时\thttps://example.test/a\n"
        ),
        encoding="utf-8-sig",
    )
    return path

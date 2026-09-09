"""Offline regressions for the September 2026 audit; never crawl real sites."""
import copy
import io
import json
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bantou.config.issues import parse_issue_range, format_issue_label
from bantou.config.sites import read_failed_sites, normalized_site_url
from bantou.domain.models import Match, Site, SiteResult, SourceDocument
from bantou.domain.validation import validate_exact_matches
from bantou.application import single_period, site_crawl, multi_period, duplicate_detection, site_validation
from bantou.cache.builders import _site_cache_item_for_issues, _site_identity_from_site, _site_identity_from_item
from bantou.cache.updates import merge_cache_updates
from bantou.cache.validation import CACHE_KIND, cache_entry_from_match, validate_cache_payload, CacheValidationError
from bantou.outputs.formatting import build_success_output_lines, read_success_data, read_fail_entries_from_lines
from bantou.fetching.transport import RunTransport, canonical_url, canonical_browser_url, FetchedText
from bantou.documents.dynamic import records, aggregate
from bantou.text import extract_half_head_table_texts, normalize_target


@pytest.fixture(autouse=True)
def forbid_external_network(monkeypatch):
    original = socket.socket.connect
    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {'localhost', '127.0.0.1', '::1'}:
            raise AssertionError(f'Offline test attempted external network: {address[0]}')
        return original(sock, address)
    monkeypatch.setattr(socket.socket, 'connect', connect)


def site(name='A', url='https://example.test/a', **kwargs):
    return Site(name, url, kwargs.pop('pick', 'top'), 1, 'strict_half_head', ('半头',), **kwargs)


def match(issue=251, value='2头双', **kwargs):
    fields = dict(issue=issue, issue_text=str(issue), value=value,
                  snippet=f'{issue}期 必杀半头[{value}]开00对', order=1, position=0,
                  source_url='https://example.test/a', source_kind='page',
                  anchor_text='半头', anchor_position=7, block_id='row', block_start=0,
                  block_end=40, container_id='body', document_authority='primary-page', rule_id='structural')
    fields.update(kwargs)
    return Match(**fields)


def payload(sites=None):
    issues = list(range(242, 252))
    sites = sites or [site()]
    items = [_site_cache_item_for_issues(s, {i: match(i) for i in issues}, issues) for s in sites]
    return dict(schema=2, kind=CACHE_KIND, state='ready', period=251, window=10,
                issues=issues, sites=items, failures=[])


@pytest.mark.parametrize(('raw', 'label'), [('94', '094'), ('100,102', '100_102'), ('100-102', '100-102'), ('251', '251')])
def test_issue_labels(raw, label):
    assert parse_issue_range(raw)[2] == label


def test_multi_summary_reads_current_space_format(tmp_path, monkeypatch):
    s = site()
    good, bad = tmp_path/'success', tmp_path/'failure'
    good.mkdir()
    (good/'094期-半头.txt').write_text('\n'.join(build_success_output_lines([('A','094期','2头双',s.url)])), encoding='utf-8-sig')
    monkeypatch.setattr(multi_period, 'RESULT_DIR', good)
    monkeypatch.setattr(multi_period, 'FAILURE_RESULT_DIR', bad)
    monkeypatch.setattr(multi_period, 'load_sites', lambda: [s])
    # No actual project output file may be written.
    monkeypatch.setattr(multi_period, 'write_transaction', lambda writes: [p.write_bytes(content) for p,content in writes.items()])
    path = multi_period.write_summary([94])
    report = path.read_text(encoding='utf-8-sig')
    assert '无\t全部通过' in report
    assert 'A\t全部失败' not in report


def failure_file(tmp_path, name='251期-半头-失败.txt', text=None):
    p = tmp_path/name
    p.write_text(text or '网站名称\t分类\t原因\t网址\nA\t访问超时\t超时\thttps://example.test/a\n', encoding='utf-8-sig')
    return p


def test_retry_requires_exact_issue(tmp_path):
    with pytest.raises(ValueError, match='期数'):
        read_failed_sites(failure_file(tmp_path, '250期-半头-失败.txt'), [site()], issue=251)


def test_retry_rejects_mixed_name_url(tmp_path):
    p = failure_file(tmp_path, text='网站名称\t分类\t原因\t网址\nA\t超时\t超时\thttps://example.test/b\n')
    with pytest.raises(ValueError, match='成对'):
        read_failed_sites(p, [site(), site('B','https://example.test/b')], issue=251)


def test_retry_reason_url_is_not_a_target(tmp_path):
    p = failure_file(tmp_path, text='网站名称\t分类\t原因\t网址\nA\t超时\t引用 https://example.test/b\thttps://example.test/a\n')
    assert read_failed_sites(p, [site(), site('B','https://example.test/b')], issue=251) == [site()]


def test_retry_accepts_explicit_issue_tsv(tmp_path):
    text = '期数\t网站名称\t分类\t原因\t网址\n251\tA\t超时\t超时\thttps://example.test/a\n'
    p = failure_file(tmp_path, 'custom.txt', text)
    assert read_failed_sites(p, [site()], issue=251) == [site()]
    assert read_fail_entries_from_lines(text.splitlines())[0][0] == 'A'


def test_retry_no_failures_is_empty_not_all_sites(tmp_path):
    p = failure_file(tmp_path, text='网站名称\t分类\t原因\t网址\n无失败\n')
    assert read_failed_sites(p, [site()], issue=251) == []


def test_retry_hash_route_identity_not_merged(tmp_path):
    a=site('A','https://example.test/#/users/1')
    b=site('B','https://example.test/#/users/2')
    assert site_validation.select_sites([a,b], [], [a.url]) == [a]


@pytest.mark.parametrize('target_issue', [250, 241, 252, None])
def test_cache_historical_or_unspecified_retry_rejected(target_issue):
    original = payload()
    before = copy.deepcopy(original)
    with pytest.raises(CacheValidationError):
        merge_cache_updates(original, {}, [('A','retry failed',site().url)], target_issue=target_issue)
    assert original == before


def test_cache_key_must_match_live_issue():
    with pytest.raises(CacheValidationError, match='缓存键'):
        _site_cache_item_for_issues(site(), {251: match(250)}, [251])


def finalize_args(tmp_path, **kwargs):
    fields=dict(diagnose=False, retry_fail=False, replace_existing=False,
                success_out='', fail_out='',
                resolved_success_path=tmp_path/'251期-半头.txt',
                resolved_fail_path=tmp_path/'251期-半头-失败.txt')
    fields.update(kwargs)
    return SimpleNamespace(**fields)


def test_cache_conflict_never_written_but_live_result_preserved(tmp_path, monkeypatch):
    cache=tmp_path/'recent_10_cache.json'
    cache.write_bytes(b'original bytes')
    args=finalize_args(tmp_path)
    monkeypatch.setattr(single_period, 'DUPLICATE_BACKUP_FILE', cache)
    monkeypatch.setattr(single_period, '_prepare_cache_update', lambda *args: (args[3], args[4], args[5], {'bad':'partial'}, {'A':'identity conflict'}))
    rows=[('A','251期','2头双',site().url)]
    code=single_period._finalize_run(args,[251],[site()],'251',rows,{},['网站名称\t分类\t原因\t网址'])
    assert code == 2
    assert cache.read_bytes() == b'original bytes'
    assert '2头双 A' in args.resolved_success_path.read_text(encoding='utf-8-sig')


def test_retry_merge_uses_given_paths_and_preserves_old_order(tmp_path):
    good=tmp_path/'custom-success.txt'
    bad=failure_file(tmp_path)
    good.write_text('1头单 OLD\n\n内容\t次数\t排名\n1头单\t1\t1\n',encoding='utf-8-sig')
    rows, failures=single_period._merge_retry_rows('251',[('A','251期','2头双',site().url)],['网站名称\t分类\t原因\t网址'],success_path=good,fail_path=bad)
    assert [row[0] for row in rows] == ['OLD','A']
    assert len(failures)==1


def test_retry_conflicting_existing_success_is_not_cleared(tmp_path):
    good=tmp_path/'custom.txt'
    good.write_text('1头单 A\n',encoding='utf-8')
    bad=failure_file(tmp_path)
    with pytest.raises(ValueError,match='冲突'):
        single_period._merge_retry_rows('251',[('A','251期','2头双',site().url)],['网站名称\t分类\t原因\t网址'],success_path=good,fail_path=bad)
    assert good.read_text(encoding='utf-8')=='1头单 A\n'
    assert bad.exists()


def test_entry_mode_and_fetch_url_in_cache_identity():
    a=site()
    b=site(fetch_url='https://example.test/list',entry_mode='issue_link')
    assert _site_identity_from_site(a) != _site_identity_from_site(b)
    item=_site_cache_item_for_issues(b,{251:match()},[251])
    assert _site_identity_from_item(item) == _site_identity_from_site(b)
    item.pop('fetch_url'); item.pop('entry_mode')
    assert _site_identity_from_item(item) != _site_identity_from_site(b)


@pytest.mark.parametrize('field',['url','kind','snippet','container_id','document_authority','rule_id'])
def test_blank_source_evidence_is_rejected_on_read(field):
    p=payload()
    p['sites'][0]['records']['251']['source'][field]=''
    with pytest.raises(CacheValidationError):
        validate_cache_payload(p)


def dup_report(**kwargs):
    fields=dict(cache_schema=2,period=251,issues=tuple(range(242,252)),cached_sites=2,missing_sites=(),identity_errors=(),suspect_pairs=(),duplicate_pairs=(),separate_pairs=())
    fields.update(kwargs)
    return duplicate_detection.DuplicateReport(**fields)


@pytest.mark.parametrize(('report','expected'),[(dup_report(),('通过',0)),(dup_report(missing_sites=('A缺期',)),('未完成',2)),(dup_report(identity_errors=('A错身份',)),('未完成',2)),(dup_report(suspect_pairs=('run',)),('待人工审核',3)),(dup_report(duplicate_pairs=('run',)),('重复拒收',4))])
def test_duplicate_status(report,expected):
    assert duplicate_detection.report_decision(report)==expected


def test_short_duplicate_window_rejected():
    with pytest.raises(ValueError,match='近10期'):
        duplicate_detection.evaluate_cache(payload(),[site()],window=2)


def test_special_report_name_is_not_an_exemption():
    sites=[site('山高水厂'),site('B','https://example.test/b')]
    report=duplicate_detection.evaluate_cache(payload(sites),sites)
    assert report.separate_pairs and report.duplicate_pairs
    assert duplicate_detection.report_decision(report)==('重复拒收',4)


def run_document(monkeypatch,text,s=None,kind='page'):
    s=s or site()
    document=SourceDocument(text,source_url=s.url,source_kind=kind,container_id='test',document_authority='primary',block_start=0,block_end=len(text))
    monkeypatch.setattr(site_crawl,'_documents_for_requested_issues',lambda *args:([document],[]))
    return site_crawl.crawl_site(1,s,{251},None,5,True,0)


@pytest.mark.parametrize('text',[
    '251期\n必杀半头 2头双 开00对\n必杀半头 3头单 开00对\n250期 必杀半头 1头双 开00对',
    '251期 必杀半头 2头双 3头单 开00对',
    '251期 必杀半头 2头双 开00对\n' + '备注'*80 + ' 3头单\n250期 必杀半头 1头双 开00对',
])
def test_boundary_multivalue_never_success(monkeypatch,text):
    result=run_document(monkeypatch,text)
    assert not result.matches
    assert '冲突' in (result.error or result.miss_reason or '')


def test_identical_value_repeat_is_allowed(monkeypatch):
    result=run_document(monkeypatch,'251期 必杀半头 2头双 2头双 开00对')
    assert [m.value for m in result.matches]==['2头双']


def test_nonboundary_same_issue_conflict_does_not_veto(monkeypatch):
    result=run_document(monkeypatch,'251期 必杀半头 2头双 开00对\n250期 必杀半头 1头单 开00对\n251期 必杀半头 0头单 3头单 开00对')
    assert [m.value for m in result.matches]==['2头双']


def test_special_regex_must_not_hide_second_value(monkeypatch):
    s=site('忠不可兼','https://hbwtl.7xzry-2gul3-olawdt.xyz/topic/227014.html')
    result=run_document(monkeypatch,'251期:必杀半头[2头双]开00对\n必杀半头[3头单]开00对\n250期:必杀半头[1头单]开00对',s,'browser-text')
    assert not result.matches
    assert '冲突' in (result.error or result.miss_reason or '')


def test_anchor_offset_uses_raw_source_not_compacted_snippet(monkeypatch):
    text='<p>251期 <b>必杀半头</b> [2头双] 开00对</p>'
    result=run_document(monkeypatch,text)
    assert result.matches
    assert result.matches[0].anchor_position == text.index('半头')


def test_empty_table_cell_does_not_shift_halfhead_column():
    html='<table><tr><th>期数</th><th></th><th>半头</th><th>其他</th><th>开奖</th></tr><tr><td>251期</td><td>3头单</td><td>2头双</td><td>合</td><td>开00对</td></tr></table>'
    extracted=extract_half_head_table_texts(html)
    assert any('2头双' in s for s in extracted)
    assert all('3头单' not in s for s in extracted)


@pytest.mark.parametrize('matches', [[match(),match()],[],[match(250)],[match(value='8头单')]])
def test_final_cardinality(matches):
    assert validate_exact_matches(matches,{251}) is not None


def test_final_cardinality_valid():
    assert validate_exact_matches([match()],{251}) is None


def test_browser_fragments_are_distinct_and_reach_renderer(monkeypatch):
    transport=RunTransport()
    seen=[]
    def render(url,*args):
        seen.append(url)
        return url
    monkeypatch.setattr(transport,'_render_once',render)
    a='https://example.test/#/users/1/references/10'
    b='https://example.test/#/users/1/references/11'
    assert transport.fetch_rendered(a,1,True,html=True)==a
    assert transport.fetch_rendered(b,1,True,html=True)==b
    assert seen==[a,b]
    assert canonical_url(a)==canonical_url(b)
    assert canonical_browser_url(a)!=canonical_browser_url(b)


def test_singleflight_waiter_is_bounded(monkeypatch):
    transport=RunTransport()
    start, release=threading.Event(),threading.Event()
    def owner(*args):
        start.set(); release.wait(3); return 'ok'
    monkeypatch.setattr(transport,'_request_once',owner)
    thread=threading.Thread(target=lambda:transport.fetch_text('https://example.test/a',3,True))
    thread.start(); assert start.wait(1)
    try:
        began=time.monotonic()
        with pytest.raises(TimeoutError):
            transport.fetch_text('https://example.test/a',0.05,True)
        assert time.monotonic()-began < 0.8
    finally:
        release.set(); thread.join(2)


def response(url, status=200, location=None, data=b'ok'):
    item=Mock(url=url,status_code=status,headers={'Location':location} if location else {},content=data,encoding='utf-8')
    item.__enter__=Mock(return_value=item)
    item.__exit__=Mock(return_value=False)
    return item


def test_cross_origin_redirect_not_followed(monkeypatch):
    transport=RunTransport()
    session=Mock()
    session.get.return_value=response('https://example.test/a',302,'https://other.test/a')
    monkeypatch.setattr(transport,'session_for',lambda *args:session)
    with pytest.raises(Exception,match='跨来源'):
        transport.fetch_text('https://example.test/a',2,True)
    assert session.get.call_count==1
    assert session.get.call_args.kwargs['allow_redirects'] is False


def test_same_origin_redirect_preserves_final_url(monkeypatch):
    transport=RunTransport(); session=Mock()
    session.get.side_effect=[response('https://example.test/a',302,'/b'),response('https://example.test/b',data=b'body')]
    monkeypatch.setattr(transport,'session_for',lambda *args:session)
    data=transport.fetch_text('https://example.test/a',2,True)
    assert data=='body' and data.final_url=='https://example.test/b'
    assert data.requested_url=='https://example.test/a'


def test_browser_dynamic_evidence_needs_no_fake_api():
    m=match(source_kind='dynamic-record-browser',record_id='12',url_record_id='12',record_path='root',route_type='forum',title='必杀半头',author='A')
    entry=cache_entry_from_match(m)
    assert entry['source']['api_url']==''


def record(number=1,family='forums'):
    return dict(id=number,user_id=123,draw=251,title='251期必杀半头',content='251期必杀半头[2头双]开00对',author='A')


def test_pagination_finds_second_matching_record_after_page_one(monkeypatch):
    s=site(url='https://example.test/#/users/123')
    monkeypatch.setattr(aggregate,'extra_api_urls',lambda url:['https://example.test/api/v1/users/123/forums?per_page=20'])
    first=[record(1)]+[dict(record(i),draw=250) for i in range(2,21)]
    second=[record(21)]
    calls=[]
    def fetch(url,*args,**kwargs):
        calls.append(url)
        return json.dumps(first if 'page=1&' in url or url.endswith('page=1') else second)
    monkeypatch.setattr(aggregate,'fetch_text',fetch)
    with pytest.raises(ValueError,match='未唯一'):
        aggregate.resolve_user_aggregate_detail_url(s,251,2,True)
    assert len(calls)==2


def test_reference_route_is_not_rewritten_as_forum(monkeypatch):
    s=site(url='https://example.test/#/users/123')
    monkeypatch.setattr(aggregate,'extra_api_urls',lambda url:['https://example.test/api/v1/users/123/references'])
    monkeypatch.setattr(aggregate,'fetch_text',lambda *a,**k:json.dumps([record(5)]))
    assert aggregate.resolve_user_aggregate_detail_url(s,251,2,True).endswith('/references/5')


def test_repeated_full_api_page_is_incomplete(monkeypatch):
    s=site(url='https://example.test/#/users/123')
    monkeypatch.setattr(aggregate,'extra_api_urls',lambda url:['https://example.test/api/v1/users/123/forums'])
    monkeypatch.setattr(aggregate,'fetch_text',lambda *a,**k:json.dumps([record(i) for i in range(1,21)]))
    with pytest.raises(ValueError,match='同一页'):
        aggregate.resolve_user_aggregate_detail_url(s,251,2,True)


def test_unknown_discovery_route_is_rejected(monkeypatch):
    s=site(url='https://example.test/#/users/123')
    monkeypatch.setattr(aggregate,'extra_api_urls',lambda url:['https://example.test/api/v1/users/123/discoveries'])
    monkeypatch.setattr(aggregate,'fetch_text',lambda *a,**k:json.dumps([record(5)]))
    with pytest.raises(ValueError,match='禁止冒充'):
        aggregate.resolve_user_aggregate_detail_url(s,251,2,True)


def test_dynamic_draw_mismatch_rejected_before_browser():
    s=site(url='https://example.test/#/users/123/forums/1')
    doc=SourceDocument(json.dumps(dict(record(1),draw=250)),source_url='https://example.test/api/v1/forums/1',source_kind='api')
    with pytest.raises(ValueError,match='draw'):
        records.target_record_document([doc],s.url,s,wanted_issues={251})
    assert not records.dynamic_browser_fallback_allowed(ValueError('攻击者文字 缺少正文内容'))


@pytest.mark.parametrize('raw',['251 & echo NO','251|echo NO','251" & rem','', '251-252'])
def test_daily_input_is_not_executable(monkeypatch,raw):
    import run_daily
    crawl=Mock()
    monkeypatch.setattr(run_daily,'crawl_main',crawl)
    monkeypatch.setattr('builtins.input',lambda *args:raw)
    assert run_daily.main()==2
    crawl.assert_not_called()


def test_conflicting_cli_inputs_rejected():
    from bantou.config.cli import build_parser,resolve_inputs
    with pytest.raises(ValueError,match='不能'):
        resolve_inputs(build_parser().parse_args(['251','--issues','252']))


def test_target_requires_full_match():
    with pytest.raises(ValueError):
        normalize_target('abc2头双xyz')


def test_single_period_rejects_range_before_crawl(monkeypatch):
    crawl=Mock()
    monkeypatch.setattr(single_period,'_run_sites',crawl)
    assert single_period.main(['250-251'])==2
    crawl.assert_not_called()


def test_output_alias_rejected_before_crawl(tmp_path,monkeypatch):
    crawl=Mock()
    monkeypatch.setattr(single_period,'_run_sites',crawl)
    p=str(tmp_path/'same.txt')
    assert single_period.main(['251','--success-out',p,'--fail-out',p])==2
    crawl.assert_not_called()


def test_existing_success_not_overwritten_before_crawl(tmp_path,monkeypatch):
    p=tmp_path/'old.txt';p.write_bytes(b'old')
    crawl=Mock();monkeypatch.setattr(single_period,'_run_sites',crawl)
    assert single_period.main(['251','--success-out',str(p)])==2
    assert p.read_bytes()==b'old'
    crawl.assert_not_called()


def test_table_values_and_header_coordinates_reach_full_parser(monkeypatch):
    html='<table><tr><th>期数</th><th>半头</th><th>开奖</th></tr><tr><td>251期</td><td>2头双</td><td>开00对</td></tr></table>'
    result=run_document(monkeypatch,html)
    assert [m.value for m in result.matches]==['2头双']
    assert result.matches[0].anchor_position==html.index('半头')
    cache_entry_from_match(result.matches[0])


def test_same_table_cell_multiple_values_not_silently_truncated(monkeypatch):
    html='<table><tr><th>期数</th><th>半头</th><th>开奖</th></tr><tr><td>251期</td><td>2头双 3头单</td><td>开00对</td></tr></table>'
    result=run_document(monkeypatch,html)
    assert not result.matches
    assert '冲突' in (result.error or result.miss_reason or '')


def test_custom_retry_failure_keeps_explicit_issue(tmp_path, monkeypatch):
    bad = failure_file(tmp_path, 'custom.txt', '期数\t网站名称\t分类\t原因\t网址\n251\tA\t超时\t超时\thttps://example.test/a\n')
    args = finalize_args(tmp_path, retry_fail=True, resolved_fail_path=bad)
    monkeypatch.setattr(single_period, '_prepare_cache_update', lambda *a: (a[3], a[4], a[5], None, {}))
    code = single_period._finalize_run(args, [251], [site()], '251', [], {}, ['网站名称\t分类\t原因\t网址','A\t超时\t仍然超时\thttps://example.test/a'])
    assert code == 0
    assert bad.read_text(encoding='utf-8-sig').startswith('期数\t')
    assert read_failed_sites(bad, [site()], issue=251) == [site()]
    with pytest.raises(ValueError, match='期数'):
        read_failed_sites(bad, [site()], issue=250)

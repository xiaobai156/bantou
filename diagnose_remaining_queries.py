from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests

from bantou.config.sites import read_sites
from bantou.fetching.policy import fetch_rendered_html
from bantou.fetching.transport import DEFAULT_HEADERS
from bantou.parsers.dedicated import caiyuntong_macau_matches
from bantou.domain.models import SourceDocument
from bantou.text import html_to_text, normalize_text

ISSUE = 252


def sites():
    return {s.name: s for s in read_sites(Path('sites.json'))}


def inspect_baba(s):
    print('\n=== BABA DIRECT ===')
    sess = requests.Session(); sess.headers.update(DEFAULT_HEADERS)
    candidates = [
        s.url,
        urljoin(s.url, '/main/bbs/080.html'),
        urljoin(s.url, '/htm/tz/bbs/080.html'),
        urljoin(s.url, '/main/bbs/top080.html'),
    ]
    for url in candidates:
        try:
            r = sess.get(url, timeout=20, verify=True)
            text = normalize_text(html_to_text(r.text))
            idx = text.find('252期')
            print(f'BABA\tstatus={r.status_code}\tlen={len(r.content)}\turl={r.url}')
            if idx >= 0:
                print('BABA_252\t' + text[max(0, idx-250):idx+900].replace('\n',' '))
            for src in re.findall(r'<iframe\b[^>]*src=[\"\']?([^\"\'\s>]+)', r.text, re.I):
                print('BABA_IFRAME\t' + urljoin(r.url, src))
        except Exception as e:
            print(f'BABA_ERROR\t{url}\t{type(e).__name__}: {e}')


def inspect_simple(s):
    print('\n=== SIMPLE FILTERS ===')
    sess = requests.Session(); sess.headers.update(DEFAULT_HEADERS)
    base = s.url.split('/#/')[0].rstrip('/') + '/api/v1/users/1293/forums'
    variants = [
        {'per_page': 100},
        {'per_page': 100, 'year': 2026},
        {'per_page': 100, 'draw': ISSUE},
        {'per_page': 100, 'year': 2026, 'draw': ISSUE},
        {'per_page': 100, 'topic': '必杀半头'},
        {'per_page': 100, 'year': 2026, 'draw': ISSUE, 'topic': '必杀半头'},
    ]
    for params in variants:
        url = base + '?' + urlencode(params)
        try:
            r = sess.get(url, timeout=25, verify=True)
            print(f'SIMPLE\tstatus={r.status_code}\tbytes={len(r.content)}\tparams={json.dumps(params, ensure_ascii=False)}')
            data = r.json() if r.ok else None
            rows = data if isinstance(data, list) else data.get('data', []) if isinstance(data, dict) else []
            hits = []
            for item in rows if isinstance(rows, list) else []:
                if isinstance(item, dict) and str(item.get('draw')) == str(ISSUE):
                    hits.append({k:item.get(k) for k in ('id','user_id','draw','year','topic','sub_topic')})
            print(f'SIMPLE_ROWS\t{len(rows) if isinstance(rows,list) else -1}\thits=' + json.dumps(hits[:20], ensure_ascii=False))
        except Exception as e:
            print(f'SIMPLE_ERROR\tparams={params}\t{type(e).__name__}: {e}')


def inspect_meng(s):
    print('\n=== MENG ANCHORS ===')
    try:
        html = str(fetch_rendered_html(s.url, 25, True, wait_until='domcontentloaded'))
    except Exception as e:
        print(f'MENG_RENDER_ERROR\t{type(e).__name__}: {e}'); return
    link_re = re.compile(r'<a\b[^>]*href\s*=\s*[\"\']?([^\"\'\s>]+)[\"\']?[^>]*>(.*?)</a>', re.I|re.S)
    rows=[]
    for href, body in link_re.findall(html):
        text = normalize_text(re.sub(r'<[^>]+>', ' ', body))
        compact = re.sub(r'\s+','',text)
        if '252期' in compact or '半头' in compact or '萌小萌' in compact:
            rows.append((text, urljoin(s.url, href)))
    print(f'MENG_LINK_COUNT\t{len(rows)}')
    for text,url in rows[:100]:
        print('MENG_LINK\t' + text.replace('\t',' ')[:500] + '\t' + url)


def inspect_cai(s):
    print('\n=== CAI FRESH WAITS ===')
    for wait in ('domcontentloaded','load','networkidle'):
        try:
            html = fetch_rendered_html(s.url, 25, True, wait_until=wait)
            doc = SourceDocument(str(html), source_url=s.url, source_kind='browser')
            matches = caiyuntong_macau_matches([doc], {ISSUE})
            print(f'CAI\twait={wait}\tlen={len(str(html))}\tmatches={[(m.value,m.snippet) for m in matches]}')
        except Exception as e:
            print(f'CAI_ERROR\twait={wait}\t{type(e).__name__}: {e}')


def main():
    by = sites()
    inspect_baba(by['把把论坛'])
    inspect_simple(by['简单拖鞋'])
    inspect_meng(by['萌小萌'])
    inspect_cai(by['彩运通'])

if __name__ == '__main__':
    main()

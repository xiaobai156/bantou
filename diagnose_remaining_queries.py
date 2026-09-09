from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests

from bantou.config.sites import read_sites
from bantou.fetching.policy import fetch_rendered_html
from bantou.fetching.transport import DEFAULT_HEADERS
from bantou.text import html_to_text, normalize_text

ISSUE = 252
SELECTED = ('把把论坛','简单拖鞋','彩运通','萌小萌','山高水厂')


def sites():
    return {s.name: s for s in read_sites(Path('sites.json'))}


def cache_evidence():
    print('\n=== CACHE 251 EVIDENCE ===')
    data = json.loads(Path('recent_10_cache.json').read_text(encoding='utf-8-sig'))
    by = {item.get('name'): item for item in data.get('sites', [])}
    for name in SELECTED:
        item = by.get(name)
        record = (item or {}).get('records', {}).get('251', {})
        source = record.get('source', {}) if isinstance(record, dict) else {}
        print('CACHE\t' + '\t'.join([
            name,
            str(record.get('value','')),
            str(source.get('url','')),
            str(source.get('kind','')),
            str(source.get('snippet','')),
        ]))


def fetch_text_info(sess, label, url):
    try:
        r = sess.get(url, timeout=20, verify=True)
        text = normalize_text(html_to_text(r.text))
        issues = [int(x) for x in re.findall(r'(?<!\d)(\d{1,4})\s*期', text)]
        print(f'{label}\tstatus={r.status_code}\tbytes={len(r.content)}\turl={r.url}\tmax_issue={max(issues) if issues else ""}\thalf={"半头" in text}')
        for needle in ('252期','251期','半头'):
            idx = text.find(needle)
            if idx >= 0:
                print(f'{label}_WIN\t{needle}\t' + text[max(0,idx-250):idx+1000].replace('\n',' '))
        return r, text
    except Exception as e:
        print(f'{label}_ERROR\t{url}\t{type(e).__name__}: {e}')
        return None, ''


def inspect_baba(s):
    print('\n=== BABA SOURCES ===')
    sess = requests.Session(); sess.headers.update(DEFAULT_HEADERS)
    candidates = [
        s.url,
        urljoin(s.url, '/main/bbs/080.html'),
        urljoin(s.url, '/htm/tz/bbs/080.html'),
        urljoin(s.url, '/wap/sx.html'),
        'https://156.225.94.112:18908/jskj/amkjtop.html',
    ]
    for i,url in enumerate(candidates):
        r,text = fetch_text_info(sess, f'BABA{i}', url)
        if r is not None:
            for src in re.findall(r'<iframe\b[^>]*src=[\"\']?([^\"\'\s>]+)', r.text, re.I):
                print('BABA_IFRAME\t' + urljoin(r.url, src))


def inspect_simple(s):
    print('\n=== SIMPLE 500 PREFIX ===')
    sess = requests.Session(); sess.headers.update(DEFAULT_HEADERS)
    base = s.url.split('/#/')[0].rstrip('/') + '/api/v1/users/1293/forums'
    url = base + '?' + urlencode({'per_page': 500})
    try:
        r = sess.get(url, timeout=30, verify=True)
        print(f'SIMPLE500\tstatus={r.status_code}\tbytes={len(r.content)}')
        rows = r.json()
        years=[]; ids=[]; hits=[]
        for item in rows if isinstance(rows,list) else []:
            if not isinstance(item,dict): continue
            try: years.append(int(item.get('year')))
            except Exception: years.append(-1)
            try: ids.append(int(item.get('id')))
            except Exception: ids.append(-1)
            if str(item.get('draw')) == str(ISSUE) and int(item.get('year') or 0) == 2026:
                hits.append({k:item.get(k) for k in ('id','user_id','draw','year','topic','sub_topic')})
        first_old = next((i for i,y in enumerate(years) if y < 2026), None)
        current_after_old = any(y == 2026 for y in years[(first_old or 0)+1:]) if first_old is not None else None
        print(f'SIMPLE500_ROWS\t{len(rows) if isinstance(rows,list) else -1}\tfirst_year={years[0] if years else ""}\tlast_year={years[-1] if years else ""}\tfirst_old_index={first_old}\tcurrent_after_old={current_after_old}\tids_desc={all(ids[i]>=ids[i+1] for i in range(len(ids)-1)) if ids else False}')
        print('SIMPLE500_HITS\t' + json.dumps(hits, ensure_ascii=False))
    except Exception as e:
        print(f'SIMPLE500_ERROR\t{type(e).__name__}: {e}')


def inspect_meng(s):
    print('\n=== MENG HALF LINKS ===')
    try:
        html = str(fetch_rendered_html(s.url, 25, True, wait_until='domcontentloaded'))
    except Exception as e:
        print(f'MENG_RENDER_ERROR\t{type(e).__name__}: {e}'); return
    link_re = re.compile(r'<a\b[^>]*href\s*=\s*[\"\']?([^\"\'\s>]+)[\"\']?[^>]*>(.*?)</a>', re.I|re.S)
    sess = requests.Session(); sess.headers.update(DEFAULT_HEADERS)
    candidates=[]
    for href, body in link_re.findall(html):
        text = normalize_text(re.sub(r'<[^>]+>', ' ', body))
        compact = re.sub(r'\s+','',text)
        if '252期' in compact and '半头' in compact:
            url=urljoin(s.url,href)
            candidates.append((text,url))
            print('MENG_HALF_LINK\t' + text.replace('\t',' ')[:500] + '\t' + url)
    print(f'MENG_HALF_COUNT\t{len(candidates)}')
    for i,(title,url) in enumerate(candidates[:8]):
        r,text = fetch_text_info(sess, f'MENG_DETAIL{i}', url)
        if r is None or ('252期' not in text or '半头' not in text):
            try:
                rendered = str(fetch_rendered_html(url, 20, True, wait_until='domcontentloaded'))
                t = normalize_text(html_to_text(rendered))
                idx=t.find('252期')
                print(f'MENG_DETAIL{i}_BROWSER\tlen={len(t)}\t' + (t[max(0,idx-250):idx+1000].replace('\n',' ') if idx>=0 else t[:1000].replace('\n',' ')))
            except Exception as e:
                print(f'MENG_DETAIL{i}_BROWSER_ERROR\t{type(e).__name__}: {e}')


def main():
    by=sites()
    cache_evidence()
    inspect_baba(by['把把论坛'])
    inspect_simple(by['简单拖鞋'])
    inspect_meng(by['萌小萌'])

if __name__=='__main__': main()

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse

import requests

from bantou.config.sites import read_sites
from bantou.documents.collection import collect_site_documents
from bantou.documents.dynamic.routes import extra_api_urls
from bantou.fetching.policy import fetch_rendered_html
from bantou.fetching.transport import DEFAULT_HEADERS, DEFAULT_TRANSPORT, same_origin
from bantou.parsers.matching import (
    site_scoped_raw_matches,
    apply_secondary_site_scope,
    apply_direction_source_scope,
)
from bantou.site_profiles.registry import SCRIPT_SRC_RE, IFRAME_SRC_RE, HALF_HEAD_LINK_RE
from bantou.text import html_to_text, normalize_text

TARGETS = ["把把论坛", "简单拖鞋", "彩运通", "萌小萌", "山高水厂"]
ISSUE = 252


def windows(text: str, needles=("252期", "半头"), radius=220):
    clean = normalize_text(text)
    out = []
    for needle in needles:
        start = 0
        while True:
            pos = clean.find(needle, start)
            if pos < 0:
                break
            snippet = clean[max(0, pos-radius): min(len(clean), pos+radius)].replace("\n", " ")
            if snippet not in out:
                out.append(snippet)
            start = pos + len(needle)
            if len(out) >= 8:
                return out
    return out


def inspect_site_pipeline(site):
    print(f"\n=== PIPELINE {site.name} ===")
    deadline = time.monotonic() + 70
    try:
        docs, errors = collect_site_documents(site, site.fetch_url or site.url, {ISSUE}, 20, True, deadline=deadline)
    except Exception as exc:
        print(f"COLLECT_ERROR\t{type(exc).__name__}: {exc}")
        return
    print(f"DOCS\t{len(docs)}\tERRORS\t{len(errors)}")
    for idx, doc in enumerate(docs[:20]):
        kind = getattr(doc, "source_kind", "")
        surl = getattr(doc, "source_url", "")
        print(f"DOC\t{idx}\t{kind}\t{surl}\tlen={len(str(doc))}")
        for snip in windows(html_to_text(str(doc)) if "<" in str(doc) else str(doc))[:4]:
            print(f"WIN\t{idx}\t{snip}")
    raw = site_scoped_raw_matches(docs, {ISSUE}, site, region_issues={ISSUE})
    print(f"RAW\t{len(raw)}")
    for m in raw[:20]:
        print(f"RAW_MATCH\tissue={m.issue}\tvalue={m.value}\tdoc={m.document_order}\tpos={m.position}\tkind={m.source_kind}\tanchor={m.anchor_text}\tsnip={m.snippet}")
    scoped, reason, rejects = apply_secondary_site_scope(raw, site, {ISSUE})
    print(f"SECONDARY\t{len(scoped)}\treason={reason or ''}")
    for item in rejects[:20]:
        print(f"REJECT\t{item}")
    directed, dreason = apply_direction_source_scope(scoped, site, docs)
    print(f"SOURCE_SCOPE\t{len(directed)}\treason={dreason or ''}")


def inspect_resources(site):
    print(f"\n=== RESOURCES {site.name} ===")
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    for mode in ("http", "browser"):
        try:
            if mode == "http":
                resp = session.get(site.fetch_url or site.url, timeout=20, verify=True)
                text = resp.text
                base = resp.url
                print(f"BASE\thttp\tstatus={resp.status_code}\turl={base}\tlen={len(text)}")
            else:
                text = str(fetch_rendered_html(site.fetch_url or site.url, 20, True, wait_until="domcontentloaded"))
                base = site.fetch_url or site.url
                print(f"BASE\tbrowser\turl={base}\tlen={len(text)}")
        except Exception as exc:
            print(f"BASE_ERROR\t{mode}\t{type(exc).__name__}: {exc}")
            continue
        found = []
        for label, regex in (("script", SCRIPT_SRC_RE), ("iframe", IFRAME_SRC_RE), ("half", HALF_HEAD_LINK_RE)):
            for _quote, raw in regex.findall(text):
                full = urljoin(base, raw)
                item = (label, full, same_origin(site.fetch_url or site.url, full))
                if item not in found:
                    found.append(item)
        for label, full, origin_ok in found[:50]:
            print(f"RESOURCE\t{mode}\t{label}\tsame_origin={origin_ok}\t{full}")
        for snip in windows(html_to_text(text))[:6]:
            print(f"VISIBLE\t{mode}\t{snip}")


def inspect_aggregate(site):
    print(f"\n=== AGGREGATE {site.name} ===")
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    for base_url in extra_api_urls(site.url):
        parsed = urlparse(base_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        for page in (1, 2):
            q = dict(query)
            q["page"] = str(page)
            url = urlunparse(parsed._replace(query=urlencode(q)))
            try:
                resp = session.get(url, timeout=25, verify=True)
                print(f"API\tpage={page}\tstatus={resp.status_code}\tlen={len(resp.content)}\t{url}")
                if resp.status_code >= 400:
                    print(f"API_BODY\t{resp.text[:300].replace(chr(10),' ')}")
                    continue
                data = resp.json()
                rows = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
                print(f"API_ROWS\tpage={page}\ttype={type(data).__name__}\trows={len(rows) if isinstance(rows,list) else -1}")
                matches = []
                if isinstance(rows, list):
                    for item in rows:
                        if isinstance(item, dict) and str(item.get("draw")) == str(ISSUE):
                            matches.append({k: item.get(k) for k in ("id", "user_id", "draw", "year", "topic", "sub_topic", "title")})
                print("API_252\t" + json.dumps(matches[:10], ensure_ascii=False))
                if isinstance(data, dict):
                    meta = data.get("meta")
                    if meta is not None:
                        print("API_META\t" + json.dumps(meta, ensure_ascii=False)[:800])
            except Exception as exc:
                print(f"API_ERROR\tpage={page}\t{type(exc).__name__}: {exc}\t{url}")


def inspect_browser_wait(site):
    print(f"\n=== BROWSER_WAIT {site.name} ===")
    for wait in ("domcontentloaded", "load", "networkidle"):
        try:
            text = DEFAULT_TRANSPORT.fetch_rendered(site.url, 25, True, html=False, wait_until=wait)
            print(f"WAIT_OK\t{wait}\tlen={len(text)}")
            for snip in windows(str(text))[:4]:
                print(f"WAIT_WIN\t{wait}\t{snip}")
        except Exception as exc:
            print(f"WAIT_FAIL\t{wait}\t{type(exc).__name__}: {exc}")
    DEFAULT_TRANSPORT.clear()
    DEFAULT_TRANSPORT.close()


def main():
    by_name = {site.name: site for site in read_sites(Path("sites.json"))}
    inspect_site_pipeline(by_name["把把论坛"])
    inspect_aggregate(by_name["简单拖鞋"])
    inspect_resources(by_name["彩运通"])
    inspect_site_pipeline(by_name["彩运通"])
    inspect_resources(by_name["萌小萌"])
    inspect_site_pipeline(by_name["萌小萌"])
    inspect_browser_wait(by_name["山高水厂"])


if __name__ == "__main__":
    main()

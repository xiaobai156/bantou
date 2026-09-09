from __future__ import annotations

import concurrent.futures
from pathlib import Path

from bantou.application.site_crawl import crawl_site
from bantou.config.sites import read_sites
from bantou.fetching.policy import run_transport_scope

ISSUE = 252
TARGETS = [
    "揭竿而起",
    "把把论坛",
    "简单拖鞋",
    "彩运通",
    "萌小萌",
    "广东八二",
    "山高水厂",
]


def one(index, site):
    return crawl_site(
        index,
        site,
        {ISSUE},
        None,
        20,
        True,
        1,
        site_timeout=60,
    )


def main():
    sites = {site.name: site for site in read_sites(Path("sites.json"))}
    selected = [sites[name] for name in TARGETS]
    print(f"FAILED7_START\tissue={ISSUE}\tsites={len(selected)}")
    results = []
    with run_transport_scope():
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(selected)) as executor:
            future_map = {
                executor.submit(one, index, site): (index, site)
                for index, site in enumerate(selected, 1)
            }
            for future in concurrent.futures.as_completed(future_map):
                index, site = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    print(f"EXCEPTION\t{site.name}\t{type(exc).__name__}: {exc}")
                    continue
                results.append(result)
                if result.matches:
                    match = result.matches[0]
                    print(
                        "SUCCESS\t"
                        + "\t".join(
                            [
                                site.name,
                                match.value,
                                match.source_url or "",
                                match.source_kind or "",
                                match.snippet or "",
                            ]
                        )
                    )
                else:
                    reason = result.error or result.miss_reason or "未知失败"
                    print(f"FAIL\t{site.name}\t{reason}")
                    if result.debug_sample:
                        print(f"DEBUG\t{site.name}\t{result.debug_sample[:1200]}")
                    for item in result.rejection_evidence[:8]:
                        print(f"REJECT\t{site.name}\t{item}")
                    for match in result.direction_evidence[:8]:
                        print(
                            f"DIRECTION\t{site.name}\t{match.issue}期\t{match.value}\t"
                            f"doc={match.document_order}\tpos={match.position}\t"
                            f"kind={match.source_kind}\tsnippet={match.snippet}"
                        )
    success = sum(1 for result in results if result.matches)
    fail = len(selected) - success
    print(f"FAILED7_SUMMARY\tsuccess={success}\tfail={fail}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import concurrent.futures
import time

from bantou.application.site_crawl import crawl_site
from bantou.config.sites import read_sites
from bantou.fetching.policy import run_transport_scope
from bantou.paths import DEFAULT_SITES_FILE

ISSUE = 252
TIMEOUT = 20
SITE_TIMEOUT = 60
RETRIES = 1
WORKERS = 8


def main() -> int:
    sites = sorted(read_sites(DEFAULT_SITES_FILE), key=lambda site: site.line_no)
    results = []
    started = time.perf_counter()
    print(f"DIAGNOSE_START\tissue={ISSUE}\tsites={len(sites)}\tworkers={WORKERS}", flush=True)
    with run_transport_scope():
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(WORKERS, len(sites))) as executor:
            future_map = {
                executor.submit(
                    crawl_site,
                    index,
                    site,
                    {ISSUE},
                    None,
                    TIMEOUT,
                    True,
                    RETRIES,
                    0,
                    site_timeout=SITE_TIMEOUT,
                ): (index, site)
                for index, site in enumerate(sites, start=1)
            }
            completed = 0
            success_count = 0
            failure_count = 0
            for future in concurrent.futures.as_completed(future_map):
                index, site = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    from bantou.domain.models import SiteResult
                    result = SiteResult(index, site, [], f"任务异常：{type(exc).__name__}: {exc}")
                results.append(result)
                completed += 1
                if result.matches:
                    success_count += 1
                else:
                    failure_count += 1
                print(
                    f"PROGRESS\t{completed}/{len(sites)}\tsuccess={success_count}\tfail={failure_count}\t{site.name}",
                    flush=True,
                )

    print("===DIAGNOSE_RESULTS_TSV===")
    print("status\tname\tvalue\treason\turl\tsource_url\tsource_kind")
    success_count = 0
    failure_count = 0
    for result in sorted(results, key=lambda item: item.index):
        if result.matches:
            match = result.matches[0]
            success_count += 1
            print(
                "\t".join(
                    [
                        "SUCCESS",
                        result.site.name,
                        match.value,
                        "",
                        result.site.url,
                        match.source_url or "",
                        match.source_kind or "",
                    ]
                )
            )
        else:
            failure_count += 1
            reason = result.error or result.miss_reason or "未返回指定期结果"
            reason = " ".join(str(reason).split())
            print(
                "\t".join(
                    [
                        "FAIL",
                        result.site.name,
                        "",
                        reason,
                        result.site.url,
                        "",
                        "",
                    ]
                )
            )
    elapsed = time.perf_counter() - started
    print(f"DIAGNOSE_SUMMARY\tissue={ISSUE}\ttotal={len(sites)}\tsuccess={success_count}\tfail={failure_count}\telapsed={elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""Read-only, single-site validation for failed half-head sites.

This entrypoint deliberately reuses the formal parser and workflow gates but
never calls the output or cache layers.  A site must pass here before a repair
is copied into the formal configuration or parser.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bantou.application.site_crawl import crawl_site
from bantou.config.issues import parse_issue_range
from bantou.config.sites import DEFAULT_SITES_FILE, read_sites
from bantou.domain.models import Site, SiteResult
from bantou.fetching.policy import run_transport_scope
from bantou.fetching.transport import canonical_url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="失败站点独立验证：不写TXT、不写缓存、不跑全站")
    parser.add_argument("--issue", required=True, help="指定期数，例如 202 或 200-202")
    parser.add_argument("--site", action="append", default=[], help="正式配置中的站点名称，可重复指定")
    parser.add_argument("--url", action="append", default=[], help="正式配置中的站点URL，可重复指定")
    parser.add_argument("--sites", default=str(DEFAULT_SITES_FILE), help="正式 sites.json")
    parser.add_argument("--timeout", type=int, default=20, help="单请求超时秒数")
    parser.add_argument("--site-timeout", type=int, default=60, help="单站总超时秒数")
    parser.add_argument("--retries", type=int, default=1, help="单站重试次数")
    return parser


def select_sites(all_sites: list[Site], names: list[str], urls: list[str]) -> list[Site]:
    requested_names = {name.strip() for name in names if name.strip()}
    requested_urls = {canonical_url(url) for url in urls if url.strip()}
    if not requested_names and not requested_urls:
        raise ValueError("必须至少指定一个 --site 或 --url")

    selected: list[Site] = []
    matched_names: set[str] = set()
    matched_urls: set[str] = set()
    for site in all_sites:
        site_url = canonical_url(site.url)
        if site.name in requested_names or site_url in requested_urls:
            selected.append(site)
            matched_names.add(site.name)
            matched_urls.add(site_url)

    missing_names = sorted(requested_names - matched_names)
    missing_urls = sorted(requested_urls - matched_urls)
    if missing_names or missing_urls:
        pieces = [*(f"站名={name}" for name in missing_names), *(f"URL={url}" for url in missing_urls)]
        raise ValueError("正式配置未找到验证站点：" + "；".join(pieces))
    return selected


def _matches_all_requested(result: SiteResult, wanted_issues: set[int]) -> bool:
    return (
        not result.error
        and not result.miss_reason
        and {match.issue for match in result.matches} == wanted_issues
    )


def _values_text(result: SiteResult) -> str:
    matches = sorted(result.matches, key=lambda item: item.issue)
    if len(matches) == 1:
        return matches[0].value
    return "；".join(f"{match.issue}期={match.value}" for match in matches)


def print_result(index: int, total: int, site: Site, result: SiteResult, wanted_issues: set[int]) -> bool:
    passed = _matches_all_requested(result, wanted_issues)
    reason = result.error or result.miss_reason or "未返回指定期的完整结果"
    conflict = "存在" if "冲突" in reason or "重复" in reason else "无"

    print(f"\n===== 验证 {index}/{total}：{site.name} =====")
    print(f"网址：{site.url}")
    print("指定期数：" + "、".join(f"{issue}期" for issue in sorted(wanted_issues)))
    print(f"是否抓到指定期数：{'通过' if passed else '未通过'}")
    print(f"实际半头：{_values_text(result) if passed else '未确认'}")
    print(f"top/bottom：{site.pick}（{'通过' if passed else '未通过'}）")
    print(f"锚点：{'通过' if passed else '未通过'}")
    print(f"关键词：{'通过' if passed else '未通过'}")
    print(f"半头字段：{'通过' if passed else '未通过'}")
    print(f"同期冲突或重复半头：{conflict}")
    print(f"失败原因：{'无' if passed else reason}")
    return passed


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.timeout < 1 or args.site_timeout < 1 or args.retries < 0:
            raise ValueError("timeout、site-timeout必须大于0，retries不能小于0")
        issues, _width, _label = parse_issue_range(args.issue)
        wanted_issues = set(issues)
        sites = select_sites(read_sites(Path(args.sites)), args.site, args.url)
    except Exception as exc:
        print(f"独立验证输入错误：{exc}", file=sys.stderr)
        return 2

    passed_count = 0
    with run_transport_scope():
        for index, site in enumerate(sites, start=1):
            result = crawl_site(
                index,
                site,
                wanted_issues,
                None,
                args.timeout,
                True,
                args.retries,
                site_timeout=args.site_timeout,
            )
            if print_result(index, len(sites), site, result, wanted_issues):
                passed_count += 1

    failed_count = len(sites) - passed_count
    print(f"\n独立验证完成：通过 {passed_count}，失败 {failed_count}；未写入正式TXT或缓存")
    return 0 if failed_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

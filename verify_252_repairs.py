from __future__ import annotations

from pathlib import Path

from bantou.application.site_crawl import crawl_site
from bantou.config.sites import read_sites
from bantou.site_profiles.registry import BABA_FORUM_DATA_URL

ISSUE = 252
TARGETS = [
    "揭竿而起",
    "把把论坛",
    "简单拖鞋",
    "彩运通",
    "山高水厂",
    "萌小萌",
    "广东八二",
]
EXPECTED = {
    "揭竿而起": "4头单",
    "彩运通": "2头单",
    "山高水厂": "2头单",
    "萌小萌": "3头双",
    "广东八二": "1头双",
}


def fail_reason(result) -> str:
    return result.error or result.miss_reason or "未知失败"


def run_one(index, site, issue):
    return crawl_site(
        index,
        site,
        {issue},
        None,
        25,
        True,
        0,
        site_timeout=90,
    )


def main() -> None:
    by_name = {site.name: site for site in read_sites(Path("sites.json"))}
    missing = [name for name in TARGETS if name not in by_name]
    if missing:
        raise SystemExit(f"sites.json missing: {missing}")

    successes = {}
    failures = {}
    for index, name in enumerate(TARGETS):
        result = run_one(index, by_name[name], ISSUE)
        if result.error or result.miss_reason or len(result.matches) != 1:
            failures[name] = fail_reason(result)
            print(f"LIVE_FAIL\t{name}\t{failures[name]}")
            continue
        match = result.matches[0]
        successes[name] = match
        print(
            "LIVE_SUCCESS\t"
            + "\t".join(
                [name, match.value, match.source_url, match.source_kind, match.snippet]
            )
        )
        expected = EXPECTED.get(name)
        if expected is not None and match.value != expected:
            raise SystemExit(f"{name} 252 value changed: {match.value} != {expected}")

    required = set(TARGETS) - {"把把论坛"}
    missing_required = sorted(required - successes.keys())
    if missing_required:
        raise SystemExit(
            "required 252 sites still failing: "
            + "; ".join(f"{name}: {failures.get(name, 'unknown')}" for name in missing_required)
        )

    # 把把论坛 currently has no verified 252 row. Prove its declared authority still
    # resolves and parses the most recent known 251 row instead of manufacturing 252.
    baba_251 = run_one(100, by_name["把把论坛"], 251)
    if baba_251.error or baba_251.miss_reason or len(baba_251.matches) != 1:
        raise SystemExit("把把论坛 251 authority regression: " + fail_reason(baba_251))
    match = baba_251.matches[0]
    print(
        "BABA_251_AUTHORITY\t"
        + "\t".join([match.value, match.source_url, match.source_kind, match.snippet])
    )
    if match.value != "3头双" or match.source_url != BABA_FORUM_DATA_URL:
        raise SystemExit(
            f"把把论坛 251 authority mismatch: {match.value} {match.source_url}"
        )

    if "把把论坛" not in successes:
        print("BABA_252_NOT_PUBLISHED\t" + failures.get("把把论坛", "no verified row"))
    else:
        baba = successes["把把论坛"]
        if baba.source_url != BABA_FORUM_DATA_URL:
            raise SystemExit(f"把把论坛 252 wrong authority: {baba.source_url}")

    print(f"LIVE_SUMMARY\t252_success={len(successes)}\t252_fail={len(failures)}")


if __name__ == "__main__":
    main()

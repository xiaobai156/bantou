import json
from pathlib import Path

from bantou.config.sites import read_sites


def test_wuzhuanxingyi_site_display_name_is_renamed():
    project_dir = Path(__file__).resolve().parents[1]
    sites = read_sites(project_dir / "sites.json")
    site = next(site for site in sites if "ocnrhq.du156-vb27w-tmhsed.xyz" in site.url)

    assert site.name == "星移物换"


def test_cache_references_use_the_renamed_site_name():
    project_dir = Path(__file__).resolve().parents[1]
    cache = json.loads(
        (project_dir / "recent_10_cache.json").read_text(encoding="utf-8-sig")
    )
    entries = [*cache.get("sites", []), *cache.get("failures", [])]
    wuzhuanxingyi_entries = [
        entry
        for entry in entries
        if entry.get("url") == "https://ocnrhq.du156-vb27w-tmhsed.xyz:16677/"
    ]

    assert all(entry.get("name") == "星移物换" for entry in wuzhuanxingyi_entries)

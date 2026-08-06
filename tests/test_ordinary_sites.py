import json
from pathlib import Path

from bantou import selection
from bantou.domain import Site


def test_formal_site_lists_contain_only_ordinary_site_config():
    project_dir = Path(__file__).resolve().parents[1]
    for filename in ("sites.json", "sites_16_special_test.json"):
        data = json.loads((project_dir / filename).read_text(encoding="utf-8-sig"))
        assert all("special_number" not in item for item in data)


def test_site_model_has_no_special_ordinal_scan_api():
    site = Site(
        name="普通站",
        url="https://example.test/ordinary",
        pick="top",
        line_no=1,
    )

    assert not hasattr(site, "special_number")
    assert not hasattr(selection, "select_special_requested_matches")

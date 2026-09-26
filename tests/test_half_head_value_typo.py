"""单位字被误写成“天”（如 269期【4天单】）时仍必须给出规范半头值。"""
from bantou.domain.models import Site, SourceDocument
from bantou.parsers import matching

URL = "https://mflmcobome.26222hi.app:2569/htm/bbs/top080.html"
ROWS = "268期:❄️绝杀半头❄️开:兔40错\n【4头双】\n269期:❄️绝杀半头❄️开:00准\n【4天单】\n"


def test_tian_unit_typo_still_yields_canonical_half_head_value():
    site = Site("一本万利秒杀半头", URL, "bottom", 1, "strict_half_head", ("半头",))
    document = SourceDocument(ROWS, source_url=URL, source_kind="browser-text")
    matches = matching.find_matches([document], {269}, site)
    assert [(match.issue, match.value) for match in matches] == [(269, "4头单")]
    assert matches[0].position >= 0

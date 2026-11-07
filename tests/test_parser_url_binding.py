# -*- coding: utf-8 -*-
"""专属解析器必须与自己的 URL 绑定，防止配置写错后静默解析失败。"""
from __future__ import annotations

import json

import pytest

from bantou.config.sites import parse_json_sites
from bantou.site_profiles.registry import (
    CAIYOULUO_LAOAYI_URL,
    CAIYUNTONG_URL,
    GUANGDONG_BAER_URL,
    SHENZHEN_FUTAN_URL,
    WUZHUANXINGYI_URL,
)

BOUND_PARSERS = {
    "caiyouluo_laoayi": CAIYOULUO_LAOAYI_URL,
    "caiyuntong_macau": CAIYUNTONG_URL,
    "guangdong_baer_left_half_head": GUANGDONG_BAER_URL,
    "shenzhen_futan_half_head": SHENZHEN_FUTAN_URL,
    "wuzhuanxingyi_embedded": WUZHUANXINGYI_URL,
}


def _sites_text(parser_id: str, url: str) -> str:
    return json.dumps(
        [
            {
                "name": "测试站",
                "url": url,
                "pick": "bottom",
                "parser": parser_id,
                "anchors": ["半头"],
            }
        ],
        ensure_ascii=False,
    )


@pytest.mark.parametrize("parser_id", sorted(BOUND_PARSERS))
def test_bound_parser_accepts_its_own_url(parser_id):
    sites = parse_json_sites(_sites_text(parser_id, BOUND_PARSERS[parser_id]), "test")
    assert sites[0].parser_id == parser_id
    assert sites[0].url == BOUND_PARSERS[parser_id]


@pytest.mark.parametrize("parser_id", sorted(BOUND_PARSERS))
def test_bound_parser_rejects_foreign_url(parser_id):
    """URL 一换，专属解析会静默返回空；必须在配置校验阶段就拒绝。"""
    with pytest.raises(ValueError, match="解析器与专属 URL 不匹配"):
        parse_json_sites(
            _sites_text(parser_id, "https://example.test/other.html"), "test"
        )

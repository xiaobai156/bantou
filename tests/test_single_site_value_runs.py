# -*- coding: utf-8 -*-
"""单站连续同值：只告警、不否决，阈值 5 期，缺期断开。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from bantou.application import single_period
from bantou.application.period_warnings import (
    RepeatedValueRun,
    collect_repeated_value_runs,
    find_repeated_value_runs,
    format_run,
    overlay_current_results,
    records_by_site_from_payload,
)


def _payload(name: str, records: dict[int, str]) -> dict[str, object]:
    return {
        "sites": [
            {
                "name": name,
                "records": {
                    str(issue): {"value": value, "order": 1, "position": 1}
                    for issue, value in records.items()
                },
            }
        ]
    }


def test_four_consecutive_issues_are_silent():
    records = {issue: "1头单" for issue in range(301, 305)}
    assert find_repeated_value_runs(records) == []


def test_five_consecutive_issues_warn():
    records = {issue: "0头单" for issue in range(305, 310)}
    assert find_repeated_value_runs(records) == [(305, 309, "0头单")]
    run = RepeatedValueRun("把把论坛", 305, 309, "0头单")
    text = format_run(run)
    assert "把把论坛 305期~309期 连续5期均为0头单" in text
    assert "疑似连续同值" in text
    assert "不影响本期结果" in text


def test_six_consecutive_issues_use_severe_wording():
    records = {issue: "0头单" for issue in range(305, 311)}
    run = RepeatedValueRun("把把论坛", 305, 310, "0头单")
    assert find_repeated_value_runs(records) == [(305, 310, "0头单")]
    text = format_run(run)
    assert "连续6期" in text
    assert "拒收级" in text
    assert "仍只告警" in text


def test_missing_issue_breaks_the_run():
    records = {301: "1头单", 302: "1头单", 303: "1头单", 305: "1头单", 306: "1头单"}
    assert find_repeated_value_runs(records) == []


def test_value_change_breaks_the_run():
    records = {301: "1头单", 302: "1头单", 303: "2头单", 304: "1头单", 305: "1头单"}
    assert find_repeated_value_runs(records) == []


def test_sites_do_not_affect_each_other():
    view = {
        "甲": {issue: "1头单" for issue in range(301, 306)},
        "乙": {301: "1头单", 302: "1头单"},
    }
    runs = collect_repeated_value_runs(view)
    assert [(run.name, run.start, run.end) for run in runs] == [("甲", 301, 305)]


def test_older_run_is_still_reported_once():
    view = {
        "甲": {
            301: "2头双", 302: "2头双", 303: "2头双", 304: "2头双", 305: "2头双",
            306: "3头单", 307: "1头双",
        }
    }
    runs = collect_repeated_value_runs(view)
    assert len(runs) == 1 and runs[0].start == 301 and runs[0].length == 5


def test_overlay_current_result_completes_run():
    view = records_by_site_from_payload(_payload("把把论坛", {301: "0头单", 302: "0头单", 303: "0头单", 304: "0头单"}))
    assert collect_repeated_value_runs(view) == []
    match = SimpleNamespace(value="0头单")
    overlay_current_results(view, {"把把论坛": (None, {310: match})})
    runs = collect_repeated_value_runs(view)
    # 304 到 310 之间缺 305-309，不构成连续段
    assert runs == []
    overlay_current_results(
        view, {"把把论坛": (None, {issue: SimpleNamespace(value="0头单") for issue in range(305, 311)})}
    )
    runs = collect_repeated_value_runs(view)
    assert [(run.start, run.end, run.length) for run in runs] == [(301, 310, 10)]


def test_diagnose_finishing_output_prints_warning(monkeypatch, capsys):
    monkeypatch.setattr(
        single_period,
        "read_cache_for_update",
        lambda *args, **kwargs: _payload("把把论坛", {issue: "0头单" for issue in range(305, 311)}),
    )
    args = SimpleNamespace(diagnose=True)
    code = single_period._finalize_run(args, [311], [], "311", [], {}, ["网站名称\t分类\t原因\t网址"])
    output = capsys.readouterr().out
    assert code == 0
    assert "单站连续同值告警" in output
    assert "把把论坛 305期~310期 连续6期均为0头单" in output
    assert "不影响本期结果" in output


def test_normal_finishing_output_prints_warning_and_keeps_results(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(
        single_period,
        "read_cache_for_update",
        lambda *args, **kwargs: _payload("把把论坛", {issue: "0头单" for issue in range(305, 311)}),
    )
    written: dict[object, object] = {}
    monkeypatch.setattr(single_period, "write_transaction", lambda payload: written.update(payload))
    rank_rows = [("把把论坛", "311期", "0头单", "https://example.test/a")]
    args = SimpleNamespace(
        diagnose=False,
        write_backup=False,
        rebuild_cache=False,
        retry_fail=False,
        replace_existing=False,
        resolved_success_path=tmp_path / "311期-半头.txt",
        resolved_fail_path=tmp_path / "311期-半头-失败.txt",
    )
    code = single_period._finalize_run(
        args, [311], [], "311", list(rank_rows), {}, ["网站名称\t分类\t原因\t网址"]
    )
    output = capsys.readouterr().out
    assert code == 0
    assert "把把论坛 305期~310期 连续6期均为0头单" in output
    assert written[args.resolved_success_path] == single_period._success_bytes(rank_rows)


def test_warning_does_not_touch_cache_or_exit_code(monkeypatch, capsys, tmp_path):
    """缓存不可用也只提示，不改变退出码。"""
    def boom(*args, **kwargs):
        raise RuntimeError("cache broken")

    monkeypatch.setattr(single_period, "read_cache_for_update", boom)
    monkeypatch.setattr(single_period, "write_transaction", lambda payload: None)
    args = SimpleNamespace(
        diagnose=False,
        write_backup=False,
        rebuild_cache=False,
        retry_fail=False,
        replace_existing=False,
        resolved_success_path=tmp_path / "311期-半头.txt",
        resolved_fail_path=tmp_path / "311期-半头-失败.txt",
    )
    code = single_period._finalize_run(args, [311], [], "311", [], {}, ["网站名称\t分类\t原因\t网址"])
    captured = capsys.readouterr()
    assert code == 0
    assert "单站连续同值告警跳过" in captured.err
    assert "单站连续同值告警" not in captured.out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

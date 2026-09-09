import pytest

from bantou.outputs.formatting import build_success_output_lines, read_success_data_strict


def test_retry_preserves_unconfigured_rows_without_relaxing_duplicate_checks(tmp_path):
    path = tmp_path / "252期-半头.txt"
    rows = [("旧站", "252期", "1头双", "")]
    path.write_text("\n".join(build_success_output_lines(rows)), encoding="utf-8-sig")
    with pytest.raises(ValueError, match="不在正式配置"):
        read_success_data_strict(path, "252期", [])
    assert read_success_data_strict(path, "252期", [], preserve_unconfigured=True) == rows
    path.write_text("\n".join(build_success_output_lines(rows + rows)), encoding="utf-8-sig")
    with pytest.raises(ValueError, match="站点重复"):
        read_success_data_strict(path, "252期", [], preserve_unconfigured=True)

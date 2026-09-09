from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one final correction, found {count}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


replace_once(
    "bantou/outputs/formatting.py",
    '''    if not path.exists():
        raise ValueError(f"找不到成功结果文件：{path}")
    expected_name = f"{issue_text}-半头.txt"
''',
    '''    if not path.exists():
        # A formal run may have produced only a failure file because every site
        # failed. Retry then starts from an empty success set.
        return []
    expected_name = f"{issue_text}-半头.txt"
''',
)

replace_once(
    "tests/test_audit_round3.py",
    '''def test_strict_success_reader_requires_existing_file(tmp_path):
    with pytest.raises(ValueError, match="找不到成功结果文件"):
        read_success_data_strict(
            tmp_path / "251期-半头.txt", "251期", [site("A")]
        )
''',
    '''def test_strict_success_reader_allows_all_failed_run_without_success_file(tmp_path):
    assert read_success_data_strict(
        tmp_path / "251期-半头.txt", "251期", [site("A")]
    ) == []
''',
)

print("Allowed retry after an all-failed run while retaining strict existing-file validation.")

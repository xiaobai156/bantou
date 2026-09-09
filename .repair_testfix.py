from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"{path}: expected one test correction, found {text.count(old)}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


replace_once(
    "tests/test_audit_repairs.py",
    "monkeypatch.setattr(single_period, '_prepare_cache_update', lambda *args: (args[3], args[4], args[5], {'bad':'partial'}, {'A':'identity conflict'}))",
    "monkeypatch.setattr(single_period, '_prepare_cache_update', lambda *args, **kwargs: (args[3], args[4], args[5], {'bad':'partial'}, {'A':'identity conflict'}))",
)
replace_once(
    "tests/test_audit_repairs.py",
    "monkeypatch.setattr(single_period, '_prepare_cache_update', lambda *a: (a[3], a[4], a[5], None, {}))",
    "monkeypatch.setattr(single_period, '_prepare_cache_update', lambda *a, **kwargs: (a[3], a[4], a[5], None, {}))",
)
replace_once(
    "tests/test_audit_repairs.py",
    """def test_retry_conflicting_existing_success_is_not_cleared(tmp_path):
    good=tmp_path/'251期-半头.txt'
    good.write_text('1头单 A\\n',encoding='utf-8')
    bad=failure_file(tmp_path)
    with pytest.raises(ValueError,match='冲突'):
        single_period._merge_retry_rows('251',[('A','251期','2头双',site().url)],['网站名称\\t分类\\t原因\\t网址'],success_path=good,fail_path=bad,configured_sites=[site()])
    assert good.read_text(encoding='utf-8')=='1头单 A\\n'
    assert bad.exists()
""",
    """def test_retry_conflicting_existing_success_is_not_cleared(tmp_path):
    good=tmp_path/'251期-半头.txt'
    original='1头单 A\\n\\n内容\\t次数\\t排名\\n1头单\\t1\\t1\\n'
    good.write_text(original,encoding='utf-8')
    bad=failure_file(tmp_path)
    with pytest.raises(ValueError,match='冲突'):
        single_period._merge_retry_rows('251',[('A','251期','2头双',site().url)],['网站名称\\t分类\\t原因\\t网址'],success_path=good,fail_path=bad,configured_sites=[site()])
    assert good.read_text(encoding='utf-8')==original
    assert bad.exists()
""",
)
replace_once(
    "tests/test_audit_round3.py",
    """                body = (
                    \"<script>localStorage.setItem('round3','secret');\"
                    \"document.body.textContent='set'</script>\"
                )
""",
    """                body = (
                    \"<body><script>localStorage.setItem('round3','secret');\"
                    \"document.body.textContent='set'</script></body>\"
                )
""",
)
replace_once(
    "tests/test_audit_round3.py",
    """                body = (
                    \"<script>document.body.textContent=\"
                    \"localStorage.getItem('round3')||'empty'</script>\"
                )
""",
    """                body = (
                    \"<body><script>document.body.textContent=\"
                    \"localStorage.getItem('round3')||'empty'</script></body>\"
                )
""",
)

print("Corrected test fixtures exposed by fail-fast validation.")

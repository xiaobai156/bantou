"""Post-apply corrections and additional regression coverage; build-only."""
from pathlib import Path


def replace(path, old, new):
    p = Path(path)
    text = p.read_text(encoding='utf-8-sig')
    if text.count(old) != 1:
        raise RuntimeError(f'{path}: correction context mismatch: {old[:70]!r}')
    p.write_text(text.replace(old, new), encoding='utf-8', newline='\n')


replace('tests/test_audit_repairs.py', 'assert good.read_text()==', "assert good.read_text(encoding='utf-8')==")
replace('tests/test_audit_repairs.py', '[record(i) for i in range(20)]', '[record(i) for i in range(1,21)]')
# A custom failure file must retain the explicit period when rewritten.
replace('bantou/application/single_period.py',
        '        try:\n            write_transaction(\n                {\n                    success_path:',
        '        if fail_path.name != default_fail_name:\n            fail_lines = ["期数\\t" + fail_lines[0]] + [\n                f"{issues[0]}\\t{line}" for line in fail_lines[1:] if line.strip()\n            ]\n        try:\n            write_transaction(\n                {\n                    success_path:')
replace('bantou/application/single_period.py',
        '        from ..paths import DEFAULT_SITES_FILE\n',
        '        from ..paths import DEFAULT_SITES_FILE\n        protected = {DEFAULT_SITES_FILE.resolve(), Path(sites_input).resolve()}\n        if args.resolved_success_path in protected or args.resolved_fail_path in protected:\n            raise ValueError("结果输出不能覆盖站点配置")\n')
with Path('tests/test_audit_repairs.py').open('a', encoding='utf-8') as f:
    f.write('''\n\ndef test_custom_retry_failure_keeps_explicit_issue(tmp_path, monkeypatch):
    bad = failure_file(tmp_path, 'custom.txt', '期数\\t网站名称\\t分类\\t原因\\t网址\\n251\\tA\\t超时\\t超时\\thttps://example.test/a\\n')
    args = finalize_args(tmp_path, retry_fail=True, resolved_fail_path=bad)
    monkeypatch.setattr(single_period, '_prepare_cache_update', lambda *a: (a[3], a[4], a[5], None, {}))
    code = single_period._finalize_run(args, [251], [site()], '251', [], {}, ['网站名称\\t分类\\t原因\\t网址','A\\t超时\\t仍然超时\\thttps://example.test/a'])
    assert code == 0
    assert bad.read_text(encoding='utf-8-sig').startswith('期数\\t')
    assert read_failed_sites(bad, [site()], issue=251) == [site()]
    with pytest.raises(ValueError, match='期数'):
        read_failed_sites(bad, [site()], issue=250)
''')
print('Corrected explicit Windows test encoding and pagination fixture; added custom-retry identity regression.')

# Normalize only reviewed changed text before testing. Production data stays intact.
import json
reviewed = json.loads(Path('.audit_changed.json').read_text(encoding='utf-8'))
reviewed += ['tests/test_audit_repairs.py', 'tests/test_browser_process.py',
             'pyproject.toml', 'docs/audit-repair-20260909.md',
             '.github/workflows/regression.yml']
for name in sorted(set(reviewed)):
    if name in {'sites.json', 'recent_10_cache.json'}:
        raise RuntimeError('Production data must never enter the repair manifest')
    p = Path(name)
    text = p.read_text(encoding='utf-8-sig')
    normalized = '\n'.join(line.rstrip(' \t') for line in text.splitlines()).rstrip('\n') + '\n'
    p.write_text(normalized, encoding='utf-8', newline='\n')
    if p.suffix == '.py':
        compile(normalized, name, 'exec')
# Keep the validation gate strict; expose diagnostics on failure.
replace('.audit_publish.py',
        "    return subprocess.check_output(['git',*args], **kwargs).decode('utf-8').strip()",
        "    try:\n        return subprocess.check_output(['git',*args], **kwargs).decode('utf-8').strip()\n    except subprocess.CalledProcessError as exc:\n        print(exc.output.decode('utf-8', errors='replace'), flush=True)\n        raise")
print('Reviewed text normalized before tests; git diff --check remains mandatory.')

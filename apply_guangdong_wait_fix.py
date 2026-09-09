from pathlib import Path

registry_path = Path("bantou/site_profiles/registry.py")
registry = registry_path.read_text(encoding="utf-8")
old = '    GUANGDONG_BAER_URL: "load",\n'
new = '    GUANGDONG_BAER_URL: "domcontentloaded",\n'
if registry.count(old) != 1:
    raise RuntimeError(f"Guangdong wait entry count={registry.count(old)}")
registry_path.write_text(registry.replace(old, new, 1), encoding="utf-8", newline="\n")

test_path = Path("tests/test_issue252_failed_repairs.py")
tests = test_path.read_text(encoding="utf-8")
addition = '''

def test_guangdong_baer_has_declared_domcontentloaded_wait():
    from bantou.site_profiles import registry
    assert registry.SITE_BROWSER_HTML_WAIT_UNTIL[registry.GUANGDONG_BAER_URL] == "domcontentloaded"
'''
if "test_guangdong_baer_has_declared_domcontentloaded_wait" not in tests:
    test_path.write_text(tests.rstrip() + addition + "\n", encoding="utf-8", newline="\n")

print("Applied Guangdong Baer render wait fix.")

from pathlib import Path

path = Path("tests/test_audit_round3.py")
text = path.read_text(encoding="utf-8")
marker = "def failure_file(tmp_path, name=\"251期-半头-失败.txt\", text=None):"
if marker in text:
    raise RuntimeError("round-three failure fixture already exists")
addition = r'''

def failure_file(tmp_path, name="251期-半头-失败.txt", text=None):
    path = tmp_path / name
    path.write_text(
        text
        or (
            "网站名称\t分类\t原因\t网址\n"
            "A\t访问超时\t超时\thttps://example.test/a\n"
        ),
        encoding="utf-8-sig",
    )
    return path
'''
path.write_text(text.rstrip() + "\n" + addition, encoding="utf-8", newline="\n")
print("Added the local failure-file fixture used by round-three tests.")

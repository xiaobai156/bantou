from __future__ import annotations

import base64
import gzip
from pathlib import Path


parts = sorted(Path(".").glob(".repair.part*"))
if not parts:
    raise RuntimeError("round-three repair bundle is missing")
encoded = "".join(path.read_text(encoding="utf-8").strip() for path in parts)
source = gzip.decompress(base64.b64decode(encoded)).decode("utf-8")

old_context = (
    'replace_once("bantou/fetching/browser_process.py", '
    '"        contexts = {}\\n", "")'
)
new_context = (
    'replace_once("bantou/fetching/browser_process.py", '
    '"    contexts = {}\\n", "")'
)
if source.count(old_context) != 1:
    raise RuntimeError("initial browser-context patch literal is not unique")
source = source.replace(old_context, new_context, 1)

old_tabs = r"['网站名称\t分类\t原因\t网址']"
new_tabs = r"['网站名称\\t分类\\t原因\\t网址']"
if source.count(old_tabs) != 4:
    raise RuntimeError(
        f"expected four escaped-tab fixtures, found {source.count(old_tabs)}"
    )
source = source.replace(old_tabs, new_tabs)
exec(compile(source, ".repair_round3.py", "exec"), {"__name__": "__main__"})

for script_name in (".repair_followup.py", ".repair_testfix.py"):
    path = Path(script_name)
    script = path.read_text(encoding="utf-8")
    exec(compile(script, str(path), "exec"), {"__name__": "__main__"})

print("All reviewed round-three repairs were applied.")

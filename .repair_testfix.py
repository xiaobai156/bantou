from pathlib import Path

for script_name in (".repair_testfix_base.py", ".repair_finalfix.py"):
    path = Path(script_name)
    source = path.read_text(encoding="utf-8")
    exec(compile(source, str(path), "exec"), {"__name__": "__main__"})

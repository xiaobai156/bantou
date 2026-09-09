from pathlib import Path

path = Path(".repair_followup_base.py")
text = path.read_text(encoding="utf-8")
old = """replace_once(
    \"bantou/application/single_period.py\",
    '''        multi_mode=multi_mode,
    )
''',
    '''        multi_mode=multi_mode,
        configured_sites=configured_sites,
    )
''',
)
"""
new = """replace_once(
    \"bantou/application/single_period.py\",
    '''    return _finalize_run(
        args, issues, sites, issues_label, rank_rows, cache_rows, fail_lines,
        multi_mode=multi_mode,
    )
''',
    '''    return _finalize_run(
        args, issues, sites, issues_label, rank_rows, cache_rows, fail_lines,
        multi_mode=multi_mode,
        configured_sites=configured_sites,
    )
''',
)
"""
if text.count(old) != 1:
    raise RuntimeError(f"follow-up wrapper context count={text.count(old)}")
text = text.replace(old, new, 1)
exec(compile(text, str(path), "exec"), {"__name__": "__main__"})

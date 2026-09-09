from pathlib import Path

path = Path("bantou/documents/dynamic/routes.py")
text = path.read_text(encoding="utf-8-sig")
old = 'f"{base}/api/v1/users/{user_id}/forums?per_page=500",'
new = 'f"{base}/api/v1/users/{user_id}/forums?per_page=253",'
if text.count(old) != 1:
    raise RuntimeError("expected exactly one applied forums per_page=500 route")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("aggregate page size adjusted to 253")

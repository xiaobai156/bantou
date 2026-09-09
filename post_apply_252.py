from pathlib import Path

path = Path("bantou/documents/dynamic/routes.py")
text = path.read_text(encoding="utf-8-sig")
needle = 'f"{base}/api/v1/users/{user_id}/forums?per_page=500",'
if text.count(needle) != 1:
    raise RuntimeError("expected exactly one applied forums per_page=500 route")
print("aggregate page size kept at verified 500")

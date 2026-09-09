from pathlib import Path

transport_path = Path("bantou/fetching/transport.py")
text = transport_path.read_text(encoding="utf-8-sig")

old = 'MAX_BODY_BYTES = 16 * 1024 * 1024\n\n\ndef _click_interactive_card'
new = '''MAX_BODY_BYTES = 16 * 1024 * 1024
SIMPLE_DRAG_SHOE_FORUMS_ORIGIN = "wcvwpj.mb4i3-vwk1b-cadppa.work"
SIMPLE_DRAG_SHOE_FORUMS_PATH = "/api/v1/users/1293/forums"
SIMPLE_DRAG_SHOE_MAX_BODY_BYTES = 24 * 1024 * 1024


def _body_limit_for_url(url: str) -> int:
    parsed = urlsplit(url)
    if (
        (parsed.hostname or "").lower() == SIMPLE_DRAG_SHOE_FORUMS_ORIGIN
        and parsed.path == SIMPLE_DRAG_SHOE_FORUMS_PATH
    ):
        return SIMPLE_DRAG_SHOE_MAX_BODY_BYTES
    return MAX_BODY_BYTES


def _click_interactive_card'''
if text.count(old) != 1:
    raise RuntimeError("transport.py: body-limit insertion point mismatch")
text = text.replace(old, new, 1)

old = '''        chain: list[str] = []
        current = url
        try:
'''
new = '''        chain: list[str] = []
        current = url
        body_limit = _body_limit_for_url(url)
        try:
'''
if text.count(old) != 1:
    raise RuntimeError("transport.py: request body-limit assignment point mismatch")
text = text.replace(old, new, 1)

if text.count('int(declared_size) > MAX_BODY_BYTES') != 1:
    raise RuntimeError("transport.py: declared size guard mismatch")
text = text.replace('int(declared_size) > MAX_BODY_BYTES', 'int(declared_size) > body_limit', 1)
if text.count('f"响应正文超过 {MAX_BODY_BYTES} 字节上限"') != 2:
    raise RuntimeError("transport.py: body limit message count mismatch")
text = text.replace('f"响应正文超过 {MAX_BODY_BYTES} 字节上限"', 'f"响应正文超过 {body_limit} 字节上限"')
if text.count('if total > MAX_BODY_BYTES:') != 1:
    raise RuntimeError("transport.py: streamed size guard mismatch")
text = text.replace('if total > MAX_BODY_BYTES:', 'if total > body_limit:', 1)
transport_path.write_text(text, encoding="utf-8")

test_path = Path("tests/test_issue252_repairs.py")
tests = test_path.read_text(encoding="utf-8-sig")
extra = '''

def test_simple_drag_shoe_body_limit_is_targeted():
    from bantou.fetching.transport import (
        MAX_BODY_BYTES,
        SIMPLE_DRAG_SHOE_MAX_BODY_BYTES,
        _body_limit_for_url,
    )

    assert _body_limit_for_url(
        "https://wcvwpj.mb4i3-vwk1b-cadppa.work/api/v1/users/1293/forums?per_page=253"
    ) == SIMPLE_DRAG_SHOE_MAX_BODY_BYTES
    assert SIMPLE_DRAG_SHOE_MAX_BODY_BYTES > MAX_BODY_BYTES
    assert _body_limit_for_url(
        "https://wcvwpj.mb4i3-vwk1b-cadppa.work/api/v1/users/999/forums?per_page=253"
    ) == MAX_BODY_BYTES
    assert _body_limit_for_url("https://example.test/api/v1/users/1293/forums") == MAX_BODY_BYTES
'''
if 'def test_simple_drag_shoe_body_limit_is_targeted():' in tests:
    raise RuntimeError("targeted body limit test already exists")
test_path.write_text(tests + extra, encoding="utf-8")
print("targeted 24 MiB body limit added for simple-drag-shoe aggregate only")

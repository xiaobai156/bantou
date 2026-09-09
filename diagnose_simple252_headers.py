from __future__ import annotations

import requests
from urllib.parse import urlencode

BASE = "https://wcvwpj.mb4i3-vwk1b-cadppa.work/api/v1/users/1293/forums"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Encoding": "identity",
}


def probe(params: dict) -> None:
    url = BASE + "?" + urlencode(params)
    try:
        with requests.get(url, headers=HEADERS, timeout=(8, 15), stream=True) as r:
            print(
                "PROBE\t"
                + str(params)
                + f"\tstatus={r.status_code}"
                + f"\tlength={r.headers.get('Content-Length')}"
                + f"\tencoding={r.headers.get('Content-Encoding')}"
                + f"\ttransfer={r.headers.get('Transfer-Encoding')}"
                + f"\ttype={r.headers.get('Content-Type')}"
            )
    except Exception as exc:
        print(f"ERROR\t{params}\t{type(exc).__name__}: {exc}")


for size in (100, 200, 250, 252, 253, 254, 255, 256, 260, 300, 400, 500):
    probe({"per_page": size})

for params in (
    {"per_page": 10, "year": 2026},
    {"per_page": 10, "year": 2025},
    {"per_page": 10, "draw": 252},
    {"per_page": 10, "year": 2026, "draw": 252},
    {"per_page": 10, "topic": "必杀半头"},
):
    probe(params)
